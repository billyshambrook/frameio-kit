"""Template rendering for OAuth authentication callback pages.

Uses Python str.format() for templating (no Jinja2 dependency required).
All user-supplied strings are HTML-escaped for XSS protection.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._app import _BrandingConfig

_BASE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — {app_name}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        :root {{
            --fk-primary: {primary_color};
            --fk-accent: {accent_color};
            --fk-bg: #f8fafc;
            --fk-card-bg: #ffffff;
            --fk-text: #1e293b;
            --fk-text-muted: #64748b;
            --fk-border: #e2e8f0;
            --fk-success: #22c55e;
            --fk-error: #ef4444;
        }}
        body {{ background-color: var(--fk-bg); color: var(--fk-text); }}
        .fk-header-accent {{ border-bottom: 3px solid var(--fk-primary); }}
        {custom_css}
    </style>
</head>
<body class="min-h-screen flex items-center justify-center p-4">
    <main class="w-full max-w-xl">
        <div class="bg-white rounded-2xl shadow-lg overflow-hidden">
            <header class="fk-header-accent p-6 pb-4">
                <div class="flex items-center gap-3">
                    {logo_html}
                    <h1 class="text-xl font-bold">{app_name}</h1>
                </div>
            </header>
            <div class="p-6 space-y-6">
                {content}
            </div>
            {footer}
        </div>
    </main>
</body>
</html>
"""

_SUCCESS_CONTENT = """\
<div class="text-center py-4">
    <div class="mx-auto w-16 h-16 rounded-full flex items-center justify-center mb-4" style="background-color: #f0fdf4;">
        <svg class="h-8 w-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/>
        </svg>
    </div>
    <h2 class="text-lg font-semibold mb-2" style="color: var(--fk-text);">Authentication Successful!</h2>
    <p class="text-sm mb-4" style="color: var(--fk-text-muted);">You have successfully signed in. This window will close automatically.</p>
    <p class="text-xs" style="color: var(--fk-text-muted);">Closing in <span id="countdown">3</span> seconds...</p>
    <script>
        let seconds = 3;
        const el = document.getElementById('countdown');
        const timer = setInterval(() => {{
            seconds--;
            el.textContent = seconds;
            if (seconds <= 0) {{
                clearInterval(timer);
                window.close();
            }}
        }}, 1000);
    </script>
</div>
"""

_ERROR_CONTENT = """\
<div class="text-center py-4">
    <div class="mx-auto w-16 h-16 rounded-full flex items-center justify-center mb-4" style="background-color: #fef2f2;">
        <svg class="h-8 w-8 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
        </svg>
    </div>
    <h2 class="text-lg font-semibold mb-2" style="color: var(--fk-error);">{title}</h2>
    <p class="text-sm mb-4" style="color: var(--fk-text-muted);">{message}</p>
    <p class="text-xs" style="color: var(--fk-text-muted);">Please close this window and try again.</p>
</div>
"""

_FOOTER = """\
<footer class="px-6 py-4 border-t text-center text-xs" style="color: var(--fk-text-muted); border-color: var(--fk-border);">
    Powered by <a href="https://github.com/billyshambrook/frameio-kit" style="color: var(--fk-primary);" target="_blank" rel="noopener">frameio-kit</a>
</footer>
"""


class AuthTemplateRenderer:
    """Renders branded OAuth callback pages using str.format().

    All user-supplied values are HTML-escaped for XSS protection.
    """

    def __init__(self, branding: _BrandingConfig) -> None:
        self._branding = branding

    def _base_vars(self, title: str) -> dict[str, str]:
        b = self._branding
        logo_html = ""
        if b.logo_url:
            logo_html = (
                f'<img src="{html.escape(b.logo_url)}" alt="{html.escape(b.name)} logo" '
                f'class="h-10 w-10 rounded-lg object-contain">'
            )
        footer = _FOOTER if b.show_powered_by else ""
        return {
            "title": html.escape(title),
            "app_name": html.escape(b.name),
            "primary_color": html.escape(b.primary_color),
            "accent_color": html.escape(b.accent_color),
            "custom_css": b.custom_css or "",
            "logo_html": logo_html,
            "footer": footer,
        }

    def render_success(self) -> str:
        """Render the authentication success page."""
        base = self._base_vars("Authentication Successful")
        base["content"] = _SUCCESS_CONTENT
        return _BASE_TEMPLATE.format(**base)

    def render_error(self, title: str, message: str) -> str:
        """Render an authentication error page."""
        content = _ERROR_CONTENT.format(
            title=html.escape(title),
            message=html.escape(message),
        )
        base = self._base_vars(title)
        base["content"] = content
        return _BASE_TEMPLATE.format(**base)
