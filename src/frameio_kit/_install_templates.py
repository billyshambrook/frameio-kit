"""Jinja2 template rendering for the installation UI.

Templates are stored as string constants to avoid external template files.
The TemplateRenderer class uses Jinja2 with autoescape enabled for XSS
protection.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._app import _BrandingConfig
    from ._install_models import HandlerManifest, Installation, InstallationDiff

logger = logging.getLogger(__name__)

_BASE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ config.name }} — Install</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
    <style>
        :root {
            --fk-primary: {{ config.primary_color }};
            --fk-accent: {{ config.accent_color }};
            --fk-bg: #f8fafc;
            --fk-card-bg: #ffffff;
            --fk-text: #1e293b;
            --fk-text-muted: #64748b;
            --fk-border: #e2e8f0;
            --fk-success: #22c55e;
            --fk-error: #ef4444;
        }
        body { background-color: var(--fk-bg); color: var(--fk-text); }
        .fk-btn-primary {
            background-color: var(--fk-primary);
            color: white;
            padding: 0.625rem 1.5rem;
            border-radius: 0.5rem;
            font-weight: 600;
            font-size: 0.875rem;
            border: none;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            transition: filter 0.15s;
        }
        .fk-btn-primary:hover { filter: brightness(0.9); }
        .fk-btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
        .fk-btn-danger {
            background-color: var(--fk-error);
            color: white;
            padding: 0.625rem 1.5rem;
            border-radius: 0.5rem;
            font-weight: 600;
            font-size: 0.875rem;
            border: none;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            transition: filter 0.15s;
        }
        .fk-btn-danger:hover { filter: brightness(0.9); }
        .fk-btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }
        .fk-link { color: var(--fk-primary); }
        .fk-link:hover { text-decoration: underline; }
        .fk-header-accent { border-bottom: 3px solid var(--fk-primary); }
        .fk-badge {
            display: inline-block;
            padding: 0.125rem 0.5rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 500;
        }
        .htmx-indicator { display: none; }
        .htmx-request .htmx-indicator { display: inline-flex; }
        .htmx-request .htmx-hide-on-request { display: none; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .animate-spin { animation: spin 1s linear infinite; }
        {% if config.custom_css %}{{ config.custom_css | safe }}{% endif %}
    </style>
</head>
<body class="min-h-screen flex items-center justify-center p-4">
    <main class="w-full max-w-xl">
        <div class="bg-white rounded-2xl shadow-lg overflow-hidden">
            <!-- Header -->
            <header class="fk-header-accent p-6 pb-4">
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-3">
                        {% if config.logo_url %}
                        <img src="{{ config.logo_url }}" alt="{{ config.name }} logo" class="h-10 w-10 rounded-lg object-contain">
                        {% endif %}
                        <h1 class="text-xl font-bold">{{ config.name }}</h1>
                    </div>
                    {% if authenticated %}
                    <form method="post" action="{{ install_path }}/logout">
                        <button type="submit" class="text-sm text-gray-400 hover:text-gray-600">Logout</button>
                    </form>
                    {% endif %}
                </div>
                {% if config.description %}
                <p class="mt-2 text-sm" style="color: var(--fk-text-muted);">{{ config.description }}</p>
                {% endif %}
            </header>

            <!-- Content -->
            <div class="p-6 space-y-6">
                {{ content | safe }}
            </div>

            <!-- Footer -->
            {% if config.show_powered_by %}
            <footer class="px-6 py-4 border-t text-center text-xs" style="color: var(--fk-text-muted); border-color: var(--fk-border);">
                Powered by <a href="https://github.com/billyshambrook/frameio-kit" class="fk-link" target="_blank" rel="noopener">frameio-kit</a>
            </footer>
            {% endif %}
        </div>
    </main>
</body>
</html>
"""

_UNAUTHENTICATED_CONTENT = """\
<!-- What will be installed -->
<section class="rounded-lg border p-4" style="border-color: var(--fk-border);">
    <h2 class="text-sm font-semibold mb-3">This app will install:</h2>
    {% if manifest.webhook_events %}
    <div class="mb-3">
        <h3 class="text-xs font-semibold uppercase tracking-wide mb-1" style="color: var(--fk-text-muted);">Webhooks</h3>
        <p class="text-sm">{{ manifest.webhook_events | join(' · ') }}</p>
    </div>
    {% endif %}
    {% if manifest.actions %}
    <div>
        <h3 class="text-xs font-semibold uppercase tracking-wide mb-1" style="color: var(--fk-text-muted);">Custom Actions</h3>
        {% for action in manifest.actions %}
        <p class="text-sm"><strong>{{ action.name }}</strong> — {{ action.description }}</p>
        {% endfor %}
    </div>
    {% endif %}
</section>

<div class="text-center">
    <p class="text-sm mb-4" style="color: var(--fk-text-muted);">To install, sign in with your Adobe account.</p>
    <a href="{{ install_path }}/login" class="fk-btn-primary inline-block">Login with Adobe</a>
</div>
"""

_AUTHENTICATED_CONTENT = """\
<!-- Account selection -->
<div class="space-y-3">
    <div>
        <label for="account_id" class="block text-sm font-medium mb-1">Account</label>
        <select id="account_id" name="account_id"
                class="w-full rounded-lg border px-3 py-2 text-sm"
                style="border-color: var(--fk-border);"
                hx-get="{{ install_path }}/workspaces"
                hx-target="#workspace-container"
                hx-indicator="#ws-loading">
            <option value="">Select an account...</option>
            {% for account in accounts %}
            <option value="{{ account.id }}">{{ account.display_name }}</option>
            {% endfor %}
        </select>
    </div>
    <div>
        <label for="workspace_id" class="block text-sm font-medium mb-1">Workspace</label>
        <div id="workspace-container">
            <select id="workspace_id" name="workspace_id" disabled
                    class="w-full rounded-lg border px-3 py-2 text-sm opacity-50"
                    style="border-color: var(--fk-border);">
                <option value="">Select an account first...</option>
            </select>
        </div>
        <div id="ws-loading" class="htmx-indicator mt-1">
            <svg class="animate-spin h-4 w-4 inline" style="color: var(--fk-primary);" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
            </svg>
            <span class="text-xs" style="color: var(--fk-text-muted);">Loading workspaces...</span>
        </div>
    </div>
</div>

<!-- Status panel -->
<div id="status-panel"></div>

<!-- Result panel -->
<div id="result-panel"></div>
"""

_WORKSPACES_FRAGMENT = """\
<select id="workspace_id" name="workspace_id"
        class="w-full rounded-lg border px-3 py-2 text-sm"
        style="border-color: var(--fk-border);"
        hx-get="{{ install_path }}/status"
        hx-target="#status-panel"
        hx-include="[name='account_id']"
        hx-indicator="#status-loading">
    <option value="">Select a workspace...</option>
    {% for workspace in workspaces %}
    <option value="{{ workspace.id }}">{{ workspace.name }}</option>
    {% endfor %}
</select>
<div id="status-loading" class="htmx-indicator mt-1">
    <svg class="animate-spin h-4 w-4 inline" style="color: var(--fk-primary);" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
    </svg>
    <span class="text-xs" style="color: var(--fk-text-muted);">Loading status...</span>
</div>
"""

_STATUS_NOT_INSTALLED = """\
<section class="rounded-lg border p-4" style="border-color: var(--fk-border);"
         hx-trigger="refreshStatus from:body" hx-get="{{ install_path }}/status"
         hx-include="[name='account_id'], [name='workspace_id']"
         hx-target="#status-panel">
    <h2 class="text-sm font-semibold mb-3">Ready to Install</h2>
    <p class="text-sm mb-3" style="color: var(--fk-text-muted);">This will set up:</p>
    {% if manifest.webhook_events %}
    <div class="mb-2">
        <h3 class="text-xs font-semibold uppercase tracking-wide mb-1" style="color: var(--fk-text-muted);">Webhooks</h3>
        <p class="text-sm">{{ manifest.webhook_events | join(' · ') }}</p>
    </div>
    {% endif %}
    {% if manifest.actions %}
    <div class="mb-4">
        <h3 class="text-xs font-semibold uppercase tracking-wide mb-1" style="color: var(--fk-text-muted);">Custom Actions</h3>
        {% for action in manifest.actions %}
        <p class="text-sm"><strong>{{ action.name }}</strong> — {{ action.description }}</p>
        {% endfor %}
    </div>
    {% endif %}
    <form hx-post="{{ install_path }}/execute" hx-target="#result-panel" hx-indicator="#action-loading" hx-swap="innerHTML">
        <input type="hidden" name="account_id" value="{{ account_id }}">
        <input type="hidden" name="workspace_id" value="{{ workspace_id }}">
        <div class="flex items-center gap-2">
            <button type="submit" class="fk-btn-primary htmx-hide-on-request">Install App</button>
            <div id="action-loading" class="htmx-indicator">
                <svg class="animate-spin h-4 w-4" style="color: var(--fk-primary);" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                </svg>
                <span class="text-sm" style="color: var(--fk-text-muted);">Installing...</span>
            </div>
        </div>
    </form>
</section>
"""

_STATUS_INSTALLED = """\
<section class="rounded-lg border p-4" style="border-color: var(--fk-border);"
         hx-trigger="refreshStatus from:body" hx-get="{{ install_path }}/status"
         hx-include="[name='account_id'], [name='workspace_id']"
         hx-target="#status-panel">
    <div class="flex items-center gap-2 mb-1">
        <span class="inline-block w-2 h-2 rounded-full" style="background-color: var(--fk-success);"></span>
        <h2 class="text-sm font-semibold">Installed</h2>
    </div>
    <p class="text-xs mb-3" style="color: var(--fk-text-muted);">Last updated: {{ installation.updated_at.strftime('%b %d, %Y') }}</p>
    {% if installation.webhook %}
    <div class="mb-2">
        <h3 class="text-xs font-semibold uppercase tracking-wide mb-1" style="color: var(--fk-text-muted);">Webhooks</h3>
        <p class="text-sm">{{ installation.webhook.events | join(' · ') }}</p>
    </div>
    {% endif %}
    {% if installation.actions %}
    <div class="mb-4">
        <h3 class="text-xs font-semibold uppercase tracking-wide mb-1" style="color: var(--fk-text-muted);">Custom Actions</h3>
        {% for action in installation.actions %}
        <p class="text-sm"><strong>{{ action.name }}</strong> — {{ action.description }}</p>
        {% endfor %}
    </div>
    {% endif %}
    <div class="flex justify-end">
        <form hx-post="{{ install_path }}/uninstall" hx-target="#result-panel" hx-indicator="#uninstall-loading" hx-swap="innerHTML">
            <input type="hidden" name="account_id" value="{{ account_id }}">
            <input type="hidden" name="workspace_id" value="{{ workspace_id }}">
            <div class="flex items-center gap-2">
                <button type="submit" class="fk-btn-danger htmx-hide-on-request">Uninstall</button>
                <div id="uninstall-loading" class="htmx-indicator">
                    <svg class="animate-spin h-4 w-4" style="color: var(--fk-error);" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                    </svg>
                    <span class="text-sm" style="color: var(--fk-text-muted);">Uninstalling...</span>
                </div>
            </div>
        </form>
    </div>
</section>
"""

_STATUS_UPDATE_AVAILABLE = """\
<section class="rounded-lg border p-4" style="border-color: var(--fk-border);"
         hx-trigger="refreshStatus from:body" hx-get="{{ install_path }}/status"
         hx-include="[name='account_id'], [name='workspace_id']"
         hx-target="#status-panel">
    <div class="flex items-center gap-2 mb-1">
        <span class="inline-block w-2 h-2 rounded-full" style="background-color: var(--fk-primary);"></span>
        <h2 class="text-sm font-semibold">Installed — Update Available</h2>
    </div>
    <p class="text-xs mb-3" style="color: var(--fk-text-muted);">Last updated: {{ installation.updated_at.strftime('%b %d, %Y') }}</p>

    <!-- Diff summary -->
    <div class="rounded border p-3 mb-4 text-sm font-mono space-y-1" style="border-color: var(--fk-border); background-color: var(--fk-bg);">
        {% for event in diff.webhook_events_added %}
        <p class="text-green-600">+ Webhook: {{ event }}</p>
        {% endfor %}
        {% for event in diff.webhook_events_removed %}
        <p class="text-red-500">- Webhook: {{ event }}</p>
        {% endfor %}
        {% for action in diff.actions_added %}
        <p class="text-green-600">+ Action: {{ action.name }}</p>
        {% endfor %}
        {% for action in diff.actions_removed %}
        <p class="text-red-500">- Action: {{ action.name }} (removed)</p>
        {% endfor %}
        {% for action in diff.actions_modified %}
        <p class="text-amber-600">~ Action: {{ action.name }} (updated)</p>
        {% endfor %}
    </div>

    <div class="flex items-center justify-between">
        <form hx-post="{{ install_path }}/execute" hx-target="#result-panel" hx-indicator="#update-loading" hx-swap="innerHTML">
            <input type="hidden" name="account_id" value="{{ account_id }}">
            <input type="hidden" name="workspace_id" value="{{ workspace_id }}">
            <div class="flex items-center gap-2">
                <button type="submit" class="fk-btn-primary htmx-hide-on-request">Update App</button>
                <div id="update-loading" class="htmx-indicator">
                    <svg class="animate-spin h-4 w-4" style="color: var(--fk-primary);" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                    </svg>
                    <span class="text-sm" style="color: var(--fk-text-muted);">Updating...</span>
                </div>
            </div>
        </form>
        <form hx-post="{{ install_path }}/uninstall" hx-target="#result-panel" hx-indicator="#uninstall-loading2" hx-swap="innerHTML">
            <input type="hidden" name="account_id" value="{{ account_id }}">
            <input type="hidden" name="workspace_id" value="{{ workspace_id }}">
            <div class="flex items-center gap-2">
                <button type="submit" class="fk-btn-danger htmx-hide-on-request">Uninstall</button>
                <div id="uninstall-loading2" class="htmx-indicator">
                    <svg class="animate-spin h-4 w-4" style="color: var(--fk-error);" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                    </svg>
                    <span class="text-sm" style="color: var(--fk-text-muted);">Uninstalling...</span>
                </div>
            </div>
        </form>
    </div>
</section>
"""

_RESULT_SUCCESS = """\
<section class="rounded-lg border p-4" style="border-color: var(--fk-success); background-color: #f0fdf4;">
    <div class="flex items-center gap-2 mb-2">
        <svg class="h-5 w-5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/>
        </svg>
        <h2 class="text-sm font-semibold text-green-800">{{ title }}</h2>
    </div>
    <p class="text-sm text-green-700">{{ details }}</p>
</section>
"""

_RESULT_ERROR = """\
<section class="rounded-lg border p-4" style="border-color: var(--fk-error); background-color: #fef2f2;">
    <div class="flex items-center gap-2 mb-2">
        <svg class="h-5 w-5 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
        </svg>
        <h2 class="text-sm font-semibold text-red-800">{{ title }}</h2>
    </div>
    <p class="text-sm text-red-700">{{ error }}</p>
</section>
"""


class TemplateRenderer:
    """Renders install UI pages and HTMX fragments using Jinja2.

    All templates are stored as string constants in this module. Jinja2 is
    configured with ``autoescape=True`` for XSS protection.
    """

    def __init__(self, branding: _BrandingConfig) -> None:
        try:
            import jinja2
        except ImportError:
            raise ImportError(
                "Jinja2 is required for the installation system. Install it with: pip install frameio-kit[install]"
            )

        self._config = branding
        self._env = jinja2.Environment(autoescape=True)

    def render_page(
        self,
        *,
        authenticated: bool,
        accounts: list[object] | None = None,
        manifest: HandlerManifest | None = None,
        install_path: str = "/install",
    ) -> str:
        """Render the full install page.

        Args:
            authenticated: Whether the user has a valid session.
            accounts: List of Frame.io account objects (if authenticated).
            manifest: Handler manifest (shown to unauthenticated users).
            install_path: Mount-prefix-aware base path for install routes.

        Returns:
            Complete HTML page string.
        """
        if authenticated:
            content_template = self._env.from_string(_AUTHENTICATED_CONTENT)
            content = content_template.render(accounts=accounts or [], install_path=install_path)
        else:
            content_template = self._env.from_string(_UNAUTHENTICATED_CONTENT)
            content = content_template.render(manifest=manifest, install_path=install_path)

        page_template = self._env.from_string(_BASE_TEMPLATE)
        return page_template.render(
            config=self._config,
            authenticated=authenticated,
            content=content,
            install_path=install_path,
        )

    def render_workspaces_fragment(self, *, workspaces: list[object], install_path: str = "/install") -> str:
        """Render the workspace dropdown HTMX fragment.

        Args:
            workspaces: List of Frame.io workspace objects.
            install_path: Mount-prefix-aware base path for install routes.

        Returns:
            HTML fragment for the workspace select element.
        """
        template = self._env.from_string(_WORKSPACES_FRAGMENT)
        return template.render(workspaces=workspaces, install_path=install_path)

    def render_status_fragment(
        self,
        *,
        account_id: str,
        workspace_id: str,
        installation: Installation | None,
        manifest: HandlerManifest,
        diff: InstallationDiff | None = None,
        install_path: str = "/install",
    ) -> str:
        """Render the status panel HTMX fragment.

        Args:
            account_id: Selected account ID.
            workspace_id: Selected workspace ID.
            installation: Existing installation record (or None).
            manifest: Current handler manifest.
            diff: Installation diff (if update available).
            install_path: Mount-prefix-aware base path for install routes.

        Returns:
            HTML fragment for the status panel.
        """
        if installation is None:
            template = self._env.from_string(_STATUS_NOT_INSTALLED)
            return template.render(
                manifest=manifest,
                account_id=account_id,
                workspace_id=workspace_id,
                install_path=install_path,
            )

        if diff and diff.has_changes:
            template = self._env.from_string(_STATUS_UPDATE_AVAILABLE)
            return template.render(
                installation=installation,
                diff=diff,
                account_id=account_id,
                workspace_id=workspace_id,
                install_path=install_path,
            )

        template = self._env.from_string(_STATUS_INSTALLED)
        return template.render(
            installation=installation,
            account_id=account_id,
            workspace_id=workspace_id,
            install_path=install_path,
        )

    def render_result_fragment(
        self,
        *,
        success: bool,
        title: str,
        details: str = "",
        error: str = "",
    ) -> str:
        """Render the result panel HTMX fragment.

        Args:
            success: Whether the operation succeeded.
            title: Result title.
            details: Success details message.
            error: Error message.

        Returns:
            HTML fragment for the result panel.
        """
        if success:
            template = self._env.from_string(_RESULT_SUCCESS)
            return template.render(title=title, details=details)
        else:
            template = self._env.from_string(_RESULT_ERROR)
            return template.render(title=title, error=error)
