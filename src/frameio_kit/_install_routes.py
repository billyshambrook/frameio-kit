"""Starlette route handlers for the app installation system.

Provides the self-service installation UI with OAuth authentication,
workspace selection, and install/update/uninstall operations via HTMX.
"""

import logging
import secrets
from typing import Any, TypedDict

from itsdangerous import BadSignature, SignatureExpired
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from ._install_manager import InstallationManager, validate_uuid
from ._install_models import HandlerManifest

logger = logging.getLogger(__name__)


class InstallSession(TypedDict):
    """Session data stored in Storage for an authenticated install user."""

    access_token: str
    user_id: str


async def _get_session(request: Request) -> InstallSession | None:
    """Retrieve and validate the install session from cookie + Storage.

    Returns None if the session is missing, invalid, or expired.
    """
    from ._encryption import TokenEncryption
    from ._install_config import InstallConfig
    from ._oauth import StateSerializer

    config: InstallConfig = request.app.state.install_config
    state_serializer: StateSerializer = request.app.state.state_serializer
    manager: InstallationManager = request.app.state.install_manager
    encryption: TokenEncryption = manager.encryption

    session_cookie = request.cookies.get("install_session")
    if not session_cookie:
        return None

    # Verify the signed cookie
    try:
        cookie_data = state_serializer.loads(session_cookie, max_age=config.session_ttl)
    except (SignatureExpired, BadSignature):
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
        user_id=session_data["user_id"],
    )


def _is_htmx(request: Request) -> bool:
    """Check if the request is an HTMX partial request."""
    return request.headers.get("HX-Request") == "true"


def _infer_base_url(request: Request, config: Any) -> str:
    """Infer the public base URL for webhook/action callbacks."""
    if config.base_url:
        return config.base_url.rstrip("/")

    from ._oauth import infer_install_url

    return infer_install_url(request)


async def _paginate_all(coro_factory, *args, **kwargs) -> list:
    """Paginate through all results from an SDK list endpoint.

    Args:
        coro_factory: The async method to call (e.g., client.accounts.index).
        *args: Positional args to pass to the method.
        **kwargs: Keyword args to pass to the method.

    Returns:
        Combined list of all data items across pages.
    """
    all_items: list = []
    after = None

    while True:
        if after:
            response = await coro_factory(*args, after=after, page_size=50, **kwargs)
        else:
            response = await coro_factory(*args, page_size=50, **kwargs)

        all_items.extend(response.data)

        if response.links.next is None:
            break

        # Extract 'after' cursor from the next link
        import urllib.parse

        parsed = urllib.parse.urlparse(response.links.next)
        params = urllib.parse.parse_qs(parsed.query)
        after_values = params.get("after")
        if after_values:
            after = after_values[0]
        else:
            break

    return all_items


async def _install_page(request: Request) -> Response:
    """GET /install — Landing page (full HTML)."""
    from ._install_templates import TemplateRenderer

    renderer: TemplateRenderer = request.app.state.template_renderer
    manifest: HandlerManifest = request.app.state.handler_manifest

    session = await _get_session(request)

    if session is None:
        # Unauthenticated landing page
        html = renderer.render_page(authenticated=False, manifest=manifest)
        return HTMLResponse(html)

    # Authenticated — load accounts
    from ._client import Client

    client = Client(token=session["access_token"])
    try:
        accounts = await _paginate_all(client.accounts.index)
    except Exception:
        logger.exception("Failed to load accounts")
        accounts = []
    finally:
        await client.close()

    html = renderer.render_page(authenticated=True, accounts=accounts, manifest=manifest)
    return HTMLResponse(html)


async def _install_login(request: Request) -> Response:
    """GET /install/login — Initiate OAuth for install."""
    from ._oauth import AdobeOAuthClient, StateSerializer

    oauth_client: AdobeOAuthClient = request.app.state.oauth_client
    state_serializer: StateSerializer = request.app.state.state_serializer

    # Build redirect URL for install callback
    base = f"{request.url.scheme}://{request.url.netloc}"
    redirect_url = f"{base}/install/callback"

    # Create signed state token
    state_data = {"redirect_url": redirect_url, "purpose": "install"}
    state = state_serializer.dumps(state_data)

    auth_url = oauth_client.get_authorization_url(state, redirect_url)
    return RedirectResponse(auth_url)


async def _install_callback(request: Request) -> Response:
    """GET /install/callback — Handle OAuth callback, create session."""
    import base64

    from ._install_config import InstallConfig
    from ._oauth import AdobeOAuthClient, StateSerializer

    config: InstallConfig = request.app.state.install_config
    oauth_client: AdobeOAuthClient = request.app.state.oauth_client
    state_serializer: StateSerializer = request.app.state.state_serializer
    manager: InstallationManager = request.app.state.install_manager
    encryption = manager.encryption

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        return HTMLResponse(
            "<h1>Authentication Failed</h1><p>Please close this window and try again.</p>",
            status_code=400,
        )

    if not code or not state:
        return HTMLResponse(
            "<h1>Error</h1><p>Missing code or state parameter.</p>",
            status_code=400,
        )

    try:
        state_data = state_serializer.loads(state)
    except (SignatureExpired, BadSignature):
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
        "user_id": token_data.user_id,
    }

    await manager.storage.put(
        f"install_session:{session_key}",
        session_record,
        ttl=config.session_ttl,
    )

    # Create signed cookie with session key
    cookie_value = state_serializer.dumps({"session_key": session_key})

    response = RedirectResponse("/install", status_code=303)
    response.set_cookie(
        key="install_session",
        value=cookie_value,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/install",
        max_age=config.session_ttl,
    )
    return response


async def _install_workspaces(request: Request) -> Response:
    """GET /install/workspaces — HTMX: load workspace dropdown."""
    from ._install_templates import TemplateRenderer

    renderer: TemplateRenderer = request.app.state.template_renderer

    session = await _get_session(request)
    if session is None:
        if _is_htmx(request):
            return Response(headers={"HX-Redirect": "/install"}, status_code=200)
        return RedirectResponse("/install")

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

    client = Client(token=session["access_token"])
    try:
        workspaces = await _paginate_all(client.workspaces.index, account_id)
    except Exception:
        logger.exception("Failed to load workspaces")
        return HTMLResponse("<p class='text-sm text-red-500'>Failed to load workspaces.</p>", status_code=500)
    finally:
        await client.close()

    html = renderer.render_workspaces_fragment(workspaces=workspaces)
    return HTMLResponse(html)


async def _install_status(request: Request) -> Response:
    """GET /install/status — HTMX: get workspace installation status."""
    from ._install_templates import TemplateRenderer

    renderer: TemplateRenderer = request.app.state.template_renderer
    manager: InstallationManager = request.app.state.install_manager
    manifest: HandlerManifest = request.app.state.handler_manifest

    session = await _get_session(request)
    if session is None:
        if _is_htmx(request):
            return Response(headers={"HX-Redirect": "/install"}, status_code=200)
        return RedirectResponse("/install")

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
    )
    return HTMLResponse(html)


async def _install_execute(request: Request) -> Response:
    """POST /install/execute — HTMX: perform install or update."""
    from ._install_config import InstallConfig
    from ._install_templates import TemplateRenderer

    config: InstallConfig = request.app.state.install_config
    renderer: TemplateRenderer = request.app.state.template_renderer
    manager: InstallationManager = request.app.state.install_manager
    manifest: HandlerManifest = request.app.state.handler_manifest

    session = await _get_session(request)
    if session is None:
        if _is_htmx(request):
            return Response(headers={"HX-Redirect": "/install"}, status_code=200)
        return RedirectResponse("/install")

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

    base_url = _infer_base_url(request, config)

    try:
        # Check for existing installation (idempotency)
        existing = await manager.get_installation(account_id, workspace_id)

        if existing is None:
            # Fresh install
            installation = await manager.install(
                token=session["access_token"],
                account_id=account_id,
                workspace_id=workspace_id,
                user_id=session["user_id"],
                base_url=base_url,
                manifest=manifest,
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

            html = renderer.render_result_fragment(
                success=True, title="Successfully installed!", details=details
            )
        else:
            # Update existing
            installation = await manager.update(
                token=session["access_token"],
                account_id=account_id,
                workspace_id=workspace_id,
                base_url=base_url,
                manifest=manifest,
                existing=existing,
            )
            html = renderer.render_result_fragment(
                success=True, title="Successfully updated!", details="Installation has been updated to match current configuration."
            )

        response = HTMLResponse(html)
        response.headers["HX-Trigger"] = "refreshStatus"
        return response

    except Exception as e:
        logger.exception("Installation failed")
        # Check for permission errors
        error_msg = str(e)
        if "403" in error_msg or "401" in error_msg or "Forbidden" in error_msg:
            error_msg = "You need workspace admin access to install this app."
        else:
            error_msg = "An unexpected error occurred. Please try again."

        html = renderer.render_result_fragment(
            success=False, title="Installation failed", error=error_msg
        )
        return HTMLResponse(html, status_code=500)


async def _install_uninstall(request: Request) -> Response:
    """POST /install/uninstall — HTMX: perform uninstall."""
    from ._install_templates import TemplateRenderer

    renderer: TemplateRenderer = request.app.state.template_renderer
    manager: InstallationManager = request.app.state.install_manager

    session = await _get_session(request)
    if session is None:
        if _is_htmx(request):
            return Response(headers={"HX-Redirect": "/install"}, status_code=200)
        return RedirectResponse("/install")

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
            success=True, title="Successfully uninstalled!", details="All webhooks and custom actions have been removed."
        )
        response = HTMLResponse(html)
        response.headers["HX-Trigger"] = "refreshStatus"
        return response

    except Exception as e:
        logger.exception("Uninstall failed")
        error_msg = str(e)
        if "403" in error_msg or "401" in error_msg or "Forbidden" in error_msg:
            error_msg = "You need workspace admin access to uninstall this app."
        else:
            error_msg = "An unexpected error occurred. Please try again."

        html = renderer.render_result_fragment(
            success=False, title="Uninstall failed", error=error_msg
        )
        return HTMLResponse(html, status_code=500)


def create_install_routes() -> list[Route]:
    """Create installation system routes.

    Returns:
        List of Starlette Route objects to mount in the app.
    """
    return [
        Route("/install", _install_page, methods=["GET"]),
        Route("/install/login", _install_login, methods=["GET"]),
        Route("/install/callback", _install_callback, methods=["GET"]),
        Route("/install/workspaces", _install_workspaces, methods=["GET"]),
        Route("/install/status", _install_status, methods=["GET"]),
        Route("/install/execute", _install_execute, methods=["POST"]),
        Route("/install/uninstall", _install_uninstall, methods=["POST"]),
    ]
