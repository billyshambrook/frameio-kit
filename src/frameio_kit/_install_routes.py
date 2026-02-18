"""Route handlers for the app installation system.

Provides the self-service installation UI with OAuth authentication,
workspace selection, and install/update/uninstall operations via HTMX.
"""

import logging
import secrets
from typing import Callable, TypedDict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from itsdangerous import BadSignature, SignatureExpired

import httpx

from ._install_manager import validate_uuid
from ._install_models import HandlerManifest, InstallField
from ._oauth import _extract_mount_prefix
from ._state import _AppState, _require

logger = logging.getLogger(__name__)


class InstallSession(TypedDict):
    """Session data stored in Storage for an authenticated install user."""

    access_token: str


async def _get_session(request: Request, state: _AppState) -> InstallSession | None:
    """Retrieve and validate the install session from cookie + Storage.

    Returns None if the session is missing, invalid, or expired.
    """

    session_ttl = state.install_session_ttl
    state_serializer = _require(state.state_serializer)
    manager = _require(state.install_manager)
    encryption = manager.encryption

    session_cookie = request.cookies.get("install_session")
    if not session_cookie:
        return None

    # Verify the signed cookie
    try:
        cookie_data = state_serializer.loads(session_cookie, max_age=session_ttl)
    except SignatureExpired, BadSignature:
        return None

    session_key = cookie_data.get("session_key")
    if not session_key:
        return None

    # Look up session in storage
    session_data = await manager.storage.get(f"install_session:{session_key}")
    if session_data is None:
        return None

    # Decrypt access token
    import base64

    try:
        encrypted_token = base64.b64decode(session_data["encrypted_access_token"])
        access_token = encryption.decrypt(encrypted_token).decode()
    except Exception:
        logger.warning("Failed to decrypt install session token")
        return None

    return InstallSession(
        access_token=access_token,
    )


def _install_path(request: Request) -> str:
    """Get the mount-prefix-aware install base path (e.g., "/myapp/install")."""
    return f"{_extract_mount_prefix(request)}/install"


def _is_secure(request: Request) -> bool:
    """Check if the request is over HTTPS, including behind reverse proxies."""
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


def _is_htmx(request: Request) -> bool:
    """Check if the request is an HTMX partial request."""
    return request.headers.get("HX-Request") == "true"


def _get_install_fields(state: _AppState) -> tuple[InstallField, ...]:
    """Get the install fields from app state, defaulting to empty tuple."""
    return state.install_fields or ()


def _get_manifest(state: _AppState) -> HandlerManifest:
    """Build the handler manifest from current handlers."""
    manager = _require(state.install_manager)
    return manager.build_manifest(state.webhook_handlers or {}, state.action_handlers or {})


def _infer_base_url(request: Request, state: _AppState) -> str:
    """Infer the public base URL for webhook/action callbacks."""
    if state.base_url:
        return state.base_url.rstrip("/")

    from ._oauth import infer_install_url

    return infer_install_url(request)


async def _paginate_all(coro_factory, *args, **kwargs) -> list:
    """Paginate through all results from an SDK list endpoint.

    The SDK returns an AsyncPager that supports async iteration and
    handles pagination automatically.

    Args:
        coro_factory: The async method to call (e.g., client.accounts.index).
        *args: Positional args to pass to the method.
        **kwargs: Keyword args to pass to the method.

    Returns:
        Combined list of all data items across pages.
    """
    pager = await coro_factory(*args, **kwargs)
    return [item async for item in pager]


def create_install_routes(get_state: Callable[[], _AppState]) -> APIRouter:
    """Create installation system routes.

    Args:
        get_state: A callable (suitable for ``Depends()``) that returns the
            shared ``_AppState`` instance.

    Returns:
        An ``APIRouter`` with the installation UI routes.
    """
    router = APIRouter()

    @router.get("/install")
    async def _install_page(request: Request, state: _AppState = Depends(get_state)) -> Response:
        """GET /install — Landing page (full HTML)."""

        renderer = _require(state.template_renderer)
        manifest = _get_manifest(state)

        session = await _get_session(request, state)

        install_base = _install_path(request)

        if session is None:
            # Unauthenticated landing page
            html = renderer.render_page(authenticated=False, manifest=manifest, install_path=install_base)
            return HTMLResponse(html)

        # Authenticated — load accounts
        from ._client import Client

        manager = _require(state.install_manager)
        client = Client(token=session["access_token"], base_url=manager._base_url)
        try:
            accounts = await _paginate_all(client.accounts.index)
        except Exception:
            logger.exception("Failed to load accounts")
            accounts = []
        finally:
            await client.close()

        # Filter to allowed accounts when an allowlist is configured
        if manager._allowed_accounts is not None:
            accounts = [a for a in accounts if a.id in manager._allowed_accounts]

        html = renderer.render_page(authenticated=True, accounts=accounts, manifest=manifest, install_path=install_base)
        return HTMLResponse(html)

    @router.get("/install/login")
    async def _install_login(request: Request, state: _AppState = Depends(get_state)) -> Response:
        """GET /install/login — Initiate OAuth for install."""
        from ._oauth import infer_install_url

        oauth_client = _require(state.oauth_client)
        state_serializer = _require(state.state_serializer)

        # Build redirect URL for install callback
        redirect_url = infer_install_url(request, "/install/callback")

        # Create signed state token
        state_data = {"redirect_url": redirect_url, "purpose": "install"}
        signed_state = state_serializer.dumps(state_data)

        auth_url = oauth_client.get_authorization_url(signed_state, redirect_url)
        return RedirectResponse(auth_url)

    @router.get("/install/callback")
    async def _install_callback(request: Request, state: _AppState = Depends(get_state)) -> Response:
        """GET /install/callback — Handle OAuth callback, create session."""
        import base64

        session_ttl = state.install_session_ttl
        oauth_client = _require(state.oauth_client)
        state_serializer = _require(state.state_serializer)
        manager = _require(state.install_manager)
        encryption = manager.encryption

        code = request.query_params.get("code")
        state_param = request.query_params.get("state")
        error = request.query_params.get("error")

        if error:
            from html import escape

            error_description = escape(request.query_params.get("error_description", "Unknown error"))
            return HTMLResponse(
                f"<h1>Authentication Failed</h1><p>{error_description}</p>",
                status_code=400,
            )

        if not code or not state_param:
            return HTMLResponse(
                "<h1>Error</h1><p>Missing code or state parameter.</p>",
                status_code=400,
            )

        try:
            state_data = state_serializer.loads(state_param)
        except SignatureExpired, BadSignature:
            return HTMLResponse(
                "<h1>Invalid or Expired State</h1><p>Please try again.</p>",
                status_code=400,
            )

        redirect_url = state_data.get("redirect_url")
        if not redirect_url:
            return HTMLResponse(
                "<h1>Invalid State</h1><p>Missing redirect URL.</p>",
                status_code=400,
            )

        try:
            token_data = await oauth_client.exchange_code(code, redirect_url)
        except Exception:
            logger.exception("Install OAuth token exchange failed")
            return HTMLResponse(
                "<h1>Authentication Failed</h1><p>Token exchange failed. Please try again.</p>",
                status_code=500,
            )

        # Create session in storage
        session_key = secrets.token_urlsafe(32)

        # Encrypt the access token before storing
        encrypted_token = encryption.encrypt(token_data.access_token.encode())
        session_record = {
            "encrypted_access_token": base64.b64encode(encrypted_token).decode("utf-8"),
        }

        await manager.storage.put(
            f"install_session:{session_key}",
            session_record,
            ttl=session_ttl,
        )

        # Create signed cookie with session key
        cookie_value = state_serializer.dumps({"session_key": session_key})
        install_base = _install_path(request)

        response = RedirectResponse(install_base, status_code=303)
        response.set_cookie(
            key="install_session",
            value=cookie_value,
            httponly=True,
            secure=_is_secure(request),
            samesite="lax",
            path=install_base,
            max_age=session_ttl,
        )
        return response

    @router.get("/install/workspaces")
    async def _install_workspaces(request: Request, state: _AppState = Depends(get_state)) -> Response:
        """GET /install/workspaces — HTMX: load workspace dropdown."""

        renderer = _require(state.template_renderer)

        session = await _get_session(request, state)
        if session is None:
            install_base = _install_path(request)
            if _is_htmx(request):
                return Response(headers={"HX-Redirect": install_base}, status_code=200)
            return RedirectResponse(install_base)

        account_id = request.query_params.get("account_id", "")
        if not account_id:
            return HTMLResponse(
                '<select disabled class="w-full rounded-lg border px-3 py-2 text-sm opacity-50">'
                "<option>Select an account first...</option></select>"
            )

        try:
            validate_uuid(account_id, "account_id")
        except ValueError:
            return HTMLResponse("<p class='text-sm text-red-500'>Invalid account ID.</p>", status_code=400)

        from ._client import Client

        manager = _require(state.install_manager)

        if not manager.is_account_allowed(account_id):
            return HTMLResponse("<p class='text-sm text-red-500'>Account not allowed.</p>", status_code=403)
        client = Client(token=session["access_token"], base_url=manager._base_url)
        try:
            workspaces = await _paginate_all(client.workspaces.index, account_id)
        except Exception:
            logger.exception("Failed to load workspaces")
            return HTMLResponse("<p class='text-sm text-red-500'>Failed to load workspaces.</p>", status_code=500)
        finally:
            await client.close()

        html = renderer.render_workspaces_fragment(workspaces=workspaces, install_path=_install_path(request))
        return HTMLResponse(html)

    @router.get("/install/status")
    async def _install_status(request: Request, state: _AppState = Depends(get_state)) -> Response:
        """GET /install/status — HTMX: get workspace installation status."""

        renderer = _require(state.template_renderer)
        manager = _require(state.install_manager)
        manifest = _get_manifest(state)

        session = await _get_session(request, state)
        if session is None:
            install_base = _install_path(request)
            if _is_htmx(request):
                return Response(headers={"HX-Redirect": install_base}, status_code=200)
            return RedirectResponse(install_base)

        account_id = request.query_params.get("account_id", "")
        workspace_id = request.query_params.get("workspace_id", "")

        if not account_id or not workspace_id:
            return HTMLResponse("")

        try:
            validate_uuid(account_id, "account_id")
            validate_uuid(workspace_id, "workspace_id")
        except ValueError:
            return HTMLResponse("<p class='text-sm text-red-500'>Invalid parameters.</p>", status_code=400)

        installation = await manager.get_installation(account_id, workspace_id)
        diff = manager.compute_diff(manifest, installation) if installation else None

        html = renderer.render_status_fragment(
            account_id=account_id,
            workspace_id=workspace_id,
            installation=installation,
            manifest=manifest,
            diff=diff,
            install_fields=_get_install_fields(state),
            install_path=_install_path(request),
        )
        return HTMLResponse(html)

    @router.post("/install/execute")
    async def _install_execute(request: Request, state: _AppState = Depends(get_state)) -> Response:
        """POST /install/execute — HTMX: perform install or update."""

        renderer = _require(state.template_renderer)
        manager = _require(state.install_manager)
        manifest = _get_manifest(state)

        session = await _get_session(request, state)
        if session is None:
            install_base = _install_path(request)
            if _is_htmx(request):
                return Response(headers={"HX-Redirect": install_base}, status_code=200)
            return RedirectResponse(install_base)

        form = await request.form()
        account_id = str(form.get("account_id", ""))
        workspace_id = str(form.get("workspace_id", ""))

        try:
            validate_uuid(account_id, "account_id")
            validate_uuid(workspace_id, "workspace_id")
        except ValueError:
            html = renderer.render_result_fragment(
                success=False, title="Invalid Parameters", error="Invalid account or workspace ID."
            )
            return HTMLResponse(html, status_code=400)

        if not manager.is_account_allowed(account_id):
            html = renderer.render_result_fragment(
                success=False, title="Not Allowed", error="This account is not permitted to install this app."
            )
            return HTMLResponse(html, status_code=403)

        # Check for existing installation early so validation can account for it
        existing = await manager.get_installation(account_id, workspace_id)

        # Extract config from form fields
        install_fields = _get_install_fields(state)
        config: dict[str, str] | None = None
        if install_fields:
            config = {}
            missing: list[str] = []
            for field in install_fields:
                value = str(form.get(f"config_{field.name}", ""))
                if field.required and not value:
                    # On updates, allow empty sensitive fields (they preserve existing values)
                    if existing and field.is_sensitive and existing.config and field.name in existing.config:
                        pass
                    else:
                        missing.append(field.label)
                config[field.name] = value
            if missing:
                html = renderer.render_result_fragment(
                    success=False,
                    title="Missing Required Fields",
                    error=f"Please fill in: {', '.join(missing)}",
                )
                return HTMLResponse(html, status_code=400)

        base_url = _infer_base_url(request, state)

        try:
            if existing is None:
                # Fresh install
                installation = await manager.install(
                    token=session["access_token"],
                    account_id=account_id,
                    workspace_id=workspace_id,
                    base_url=base_url,
                    manifest=manifest,
                    config=config,
                )
                webhook_count = 1 if installation.webhook else 0
                event_count = len(installation.webhook.events) if installation.webhook else 0
                action_count = len(installation.actions)
                details_parts = []
                if webhook_count:
                    details_parts.append(f"{webhook_count} webhook ({event_count} events)")
                if action_count:
                    details_parts.append(f"{action_count} custom action{'s' if action_count != 1 else ''}")
                details = f"Created: {', '.join(details_parts)}. Your workspace is now connected."

                html = renderer.render_result_fragment(success=True, title="Successfully installed!", details=details)
            else:
                # Update existing
                await manager.update(
                    token=session["access_token"],
                    account_id=account_id,
                    workspace_id=workspace_id,
                    base_url=base_url,
                    manifest=manifest,
                    existing=existing,
                    config=config,
                )
                html = renderer.render_result_fragment(
                    success=True,
                    title="Successfully updated!",
                    details="Installation has been updated to match current configuration.",
                )

            response = HTMLResponse(html)
            response.headers["HX-Trigger"] = "refreshStatus"
            return response

        except Exception as e:
            logger.exception("Installation failed")
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (401, 403):
                error_msg = "You need workspace admin access to install this app."
            else:
                error_msg = "An unexpected error occurred. Please try again."

            html = renderer.render_result_fragment(success=False, title="Installation failed", error=error_msg)
            return HTMLResponse(html, status_code=500)

    @router.post("/install/uninstall")
    async def _install_uninstall(request: Request, state: _AppState = Depends(get_state)) -> Response:
        """POST /install/uninstall — HTMX: perform uninstall."""

        renderer = _require(state.template_renderer)
        manager = _require(state.install_manager)

        session = await _get_session(request, state)
        if session is None:
            install_base = _install_path(request)
            if _is_htmx(request):
                return Response(headers={"HX-Redirect": install_base}, status_code=200)
            return RedirectResponse(install_base)

        form = await request.form()
        account_id = str(form.get("account_id", ""))
        workspace_id = str(form.get("workspace_id", ""))

        try:
            validate_uuid(account_id, "account_id")
            validate_uuid(workspace_id, "workspace_id")
        except ValueError:
            html = renderer.render_result_fragment(
                success=False, title="Invalid Parameters", error="Invalid account or workspace ID."
            )
            return HTMLResponse(html, status_code=400)

        if not manager.is_account_allowed(account_id):
            html = renderer.render_result_fragment(
                success=False, title="Not Allowed", error="This account is not permitted to install this app."
            )
            return HTMLResponse(html, status_code=403)

        try:
            existing = await manager.get_installation(account_id, workspace_id)
            if existing is None:
                html = renderer.render_result_fragment(
                    success=False, title="Not Installed", error="No installation found for this workspace."
                )
                return HTMLResponse(html, status_code=404)

            await manager.uninstall(
                token=session["access_token"],
                account_id=account_id,
                workspace_id=workspace_id,
                existing=existing,
            )

            html = renderer.render_result_fragment(
                success=True,
                title="Successfully uninstalled!",
                details="All webhooks and custom actions have been removed.",
            )
            response = HTMLResponse(html)
            response.headers["HX-Trigger"] = "refreshStatus"
            return response

        except Exception as e:
            logger.exception("Uninstall failed")
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (401, 403):
                error_msg = "You need workspace admin access to uninstall this app."
            else:
                error_msg = "An unexpected error occurred. Please try again."

            html = renderer.render_result_fragment(success=False, title="Uninstall failed", error=error_msg)
            return HTMLResponse(html, status_code=500)

    @router.post("/install/logout")
    async def _install_logout(request: Request, state: _AppState = Depends(get_state)) -> Response:
        """POST /install/logout — Clear session and redirect to landing page."""
        manager = _require(state.install_manager)

        # Delete session from storage if it exists
        session_cookie = request.cookies.get("install_session")
        if session_cookie:
            session_ttl = state.install_session_ttl
            state_serializer = _require(state.state_serializer)

            try:
                cookie_data = state_serializer.loads(session_cookie, max_age=session_ttl)
                session_key = cookie_data.get("session_key")
                if session_key:
                    await manager.storage.delete(f"install_session:{session_key}")
            except SignatureExpired, BadSignature:
                pass

        install_base = _install_path(request)
        response = RedirectResponse(url=install_base, status_code=303)
        response.delete_cookie(key="install_session", path=install_base)
        return response

    return router
