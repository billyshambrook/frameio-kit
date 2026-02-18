"""Shared application state container and FastAPI dependency factory.

Provides a frozen dataclass that holds all app-scoped configuration
and a factory function that produces a FastAPI ``Depends`` callable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, TypeVar

if TYPE_CHECKING:
    from ._app import _BrandingConfig
    from ._auth_templates import AuthTemplateRenderer
    from ._install_manager import InstallationManager
    from ._install_templates import TemplateRenderer
    from ._oauth import AdobeOAuthClient, OAuthConfig, StateSerializer, TokenManager


@dataclass(frozen=True)
class _AppState:
    """Immutable container for app-scoped state shared across route handlers."""

    branding: _BrandingConfig
    oauth_config: OAuthConfig | None = None
    oauth_client: AdobeOAuthClient | None = None
    state_serializer: StateSerializer | None = None
    token_manager: TokenManager | None = None
    auth_renderer: AuthTemplateRenderer | None = None
    install_manager: InstallationManager | None = None
    template_renderer: TemplateRenderer | None = None
    install_session_ttl: int = 1800
    install_fields: tuple = ()
    base_url: str | None = None
    webhook_handlers: dict[str, Any] | None = None
    action_handlers: dict[str, Any] | None = None


_T = TypeVar("_T")


def _require(val: _T | None) -> _T:
    """Narrow an optional state field, raising if ``None``.

    Used by route handlers to assert that a required piece of app state
    is configured before use.
    """
    if val is None:
        raise RuntimeError("Required state field is not configured")
    return val


def _state_dependency(state: _AppState) -> Callable[[], _AppState]:
    """Create a FastAPI dependency that returns the given state instance.

    Args:
        state: The frozen state container.

    Returns:
        A no-arg callable suitable for use with ``Depends()``.
    """

    def get_state() -> _AppState:
        return state

    return get_state
