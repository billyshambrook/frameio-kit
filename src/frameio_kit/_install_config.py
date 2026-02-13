"""Configuration model for the app installation system.

This module defines the configuration that controls the branded installation
UI and installation behavior.
"""

from pydantic import BaseModel


class InstallConfig(BaseModel):
    """Configuration for the self-service app installation system.

    Controls the branded installation UI and installation behavior. When provided
    to the ``App`` constructor, the installation system is automatically enabled
    and a self-service ``/install`` page becomes available.

    Attributes:
        app_name: Display name shown in the install UI header.
        app_description: Description shown on the landing page explaining what
            the app does.
        logo_url: URL to the partner logo image displayed in the install UI.
        primary_color: Hex color code for primary branding (buttons, links).
        accent_color: Hex color code for accent/secondary highlights.
        custom_css: Raw CSS string injected into the install page templates.
            This is developer-controlled and injected in a ``<style>`` block.
        show_powered_by: Whether to show "Powered by frameio-kit" in the footer.
        base_url: Explicit public URL for the app. If not set, the URL is
            inferred from incoming requests. Set this when behind a reverse
            proxy or when the public URL differs from what the app sees.
        session_ttl: Install session TTL in seconds. After this time, the
            admin must re-authenticate. Defaults to 30 minutes.

    Example:
        ```python
        from frameio_kit import App, OAuthConfig, InstallConfig

        app = App(
            oauth=OAuthConfig(
                client_id="...",
                client_secret="...",
            ),
            install=InstallConfig(
                app_name="Transcription Bot",
                app_description="Automatically transcribes videos.",
                logo_url="https://myapp.com/logo.png",
                primary_color="#6366f1",
            ),
        )
        ```
    """

    app_name: str
    app_description: str = ""
    logo_url: str | None = None
    primary_color: str = "#6366f1"
    accent_color: str = "#8b5cf6"
    custom_css: str | None = None
    show_powered_by: bool = True
    base_url: str | None = None
    session_ttl: int = 1800
