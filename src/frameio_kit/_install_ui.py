"""UI rendering functions for the installation flow.

This module provides HTML rendering for the installation landing page,
workspace selection, and result pages.
"""

from typing import Any

from ._install_models import InstallationRecord
from ._manifest import AppManifest


def render_install_page(manifest: AppManifest, base_url: str) -> str:
    """Render the installation landing page.

    Args:
        manifest: App manifest to display.
        base_url: Base URL for OAuth flow.

    Returns:
        HTML string for the landing page.
    """
    actions_html = ""
    if manifest.actions:
        actions_html = "<h3>Custom Actions</h3><ul>"
        for action in manifest.actions:
            actions_html += f"<li><strong>{action.name}</strong>: {action.description}</li>"
        actions_html += "</ul>"

    webhooks_html = ""
    if manifest.webhooks:
        webhooks_html = "<h3>Webhook Events</h3><ul>"
        for webhook in manifest.webhooks:
            events = ", ".join(webhook.event_types)
            webhooks_html += f"<li>{webhook.description} ({events})</li>"
        webhooks_html += "</ul>"

    icon_html = ""
    if manifest.icon_url:
        icon_html = f'<img src="{manifest.icon_url}" alt="{manifest.name}" style="max-width: 100px; margin-bottom: 1rem;">'

    return f"""
    <html>
    <head>
        <title>Install {manifest.name}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 800px;
                margin: 2rem auto;
                padding: 2rem;
                background: #f7fafc;
            }}
            .container {{
                background: white;
                padding: 2rem;
                border-radius: 0.5rem;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }}
            h1 {{ color: #2d3748; margin-top: 0; }}
            h3 {{ color: #4a5568; margin-top: 1.5rem; }}
            p {{ color: #718096; line-height: 1.6; }}
            ul {{ color: #4a5568; }}
            .install-btn {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 1rem 2rem;
                border: none;
                border-radius: 0.5rem;
                font-size: 1.1rem;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                margin-top: 1.5rem;
            }}
            .install-btn:hover {{
                opacity: 0.9;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            {icon_html}
            <h1>Install {manifest.name}</h1>
            <p>{manifest.description}</p>

            <h2>This app will install:</h2>
            {actions_html}
            {webhooks_html}

            <p style="margin-top: 2rem;">
                Click below to sign in with Adobe and select which Frame.io workspaces to install this app to.
            </p>

            <a href="{base_url}/install/oauth/login" class="install-btn">
                Install to Frame.io
            </a>
        </div>
    </body>
    </html>
    """


def render_workspace_selection(workspaces: list[dict[str, Any]], base_url: str) -> str:
    """Render workspace selection page.

    Args:
        workspaces: List of workspace dicts with 'id' and 'name'.
        base_url: Base URL for form submission.

    Returns:
        HTML string for workspace selection.
    """
    workspace_options = ""
    for ws in workspaces:
        workspace_options += f"""
        <div class="workspace-item">
            <input type="checkbox" name="workspace_ids" value="{ws['id']}" id="ws_{ws['id']}">
            <label for="ws_{ws['id']}">{ws['name']}</label>
        </div>
        """

    return f"""
    <html>
    <head>
        <title>Select Workspaces</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 800px;
                margin: 2rem auto;
                padding: 2rem;
                background: #f7fafc;
            }}
            .container {{
                background: white;
                padding: 2rem;
                border-radius: 0.5rem;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }}
            h1 {{ color: #2d3748; margin-top: 0; }}
            p {{ color: #718096; line-height: 1.6; }}
            .workspace-item {{
                padding: 0.75rem;
                border-bottom: 1px solid #e2e8f0;
            }}
            .workspace-item input[type="checkbox"] {{
                margin-right: 0.5rem;
            }}
            .workspace-item label {{
                color: #2d3748;
                font-size: 1rem;
                cursor: pointer;
            }}
            .install-btn {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 1rem 2rem;
                border: none;
                border-radius: 0.5rem;
                font-size: 1.1rem;
                cursor: pointer;
                margin-top: 1.5rem;
            }}
            .install-btn:hover {{
                opacity: 0.9;
            }}
            .install-btn:disabled {{
                opacity: 0.5;
                cursor: not-allowed;
            }}
        </style>
        <script>
            function toggleInstallButton() {{
                const checkboxes = document.querySelectorAll('input[name="workspace_ids"]:checked');
                const button = document.getElementById('install-btn');
                button.disabled = checkboxes.length === 0;
            }}
        </script>
    </head>
    <body>
        <div class="container">
            <h1>Select Workspaces</h1>
            <p>Choose which Frame.io workspaces you want to install this app to:</p>

            <form method="POST" action="{base_url}/install/process">
                {workspace_options}
                <button type="submit" id="install-btn" class="install-btn" disabled onclick="this.disabled=true; this.textContent='Installing...'; this.form.submit();">
                    Install Selected
                </button>
            </form>

            <script>
                // Enable/disable install button based on selections
                document.querySelectorAll('input[name="workspace_ids"]').forEach(cb => {{
                    cb.addEventListener('change', toggleInstallButton);
                }});
            </script>
        </div>
    </body>
    </html>
    """


def render_success_page(results: dict[str, bool], errors: dict[str, str]) -> str:
    """Render installation success/error page.

    Args:
        results: Dict mapping workspace_id to success status.
        errors: Dict mapping workspace_id to error messages.

    Returns:
        HTML string for results page.
    """
    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)

    results_html = ""
    if success_count > 0:
        results_html += "<h3>✅ Successfully Installed:</h3><ul>"
        for ws_id, success in results.items():
            if success:
                results_html += f"<li>Workspace: {ws_id}</li>"
        results_html += "</ul>"

    if errors:
        results_html += "<h3>❌ Failed:</h3><ul>"
        for ws_id, error in errors.items():
            results_html += f"<li>Workspace {ws_id}: {error}</li>"
        results_html += "</ul>"

    return f"""
    <html>
    <head>
        <title>Installation Complete</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 800px;
                margin: 2rem auto;
                padding: 2rem;
                background: #f7fafc;
            }}
            .container {{
                background: white;
                padding: 2rem;
                border-radius: 0.5rem;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }}
            h1 {{ color: #2d3748; margin-top: 0; }}
            h3 {{ color: #4a5568; margin-top: 1.5rem; }}
            p {{ color: #718096; line-height: 1.6; }}
            ul {{ color: #4a5568; }}
            .emoji {{ font-size: 3rem; margin-bottom: 1rem; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="emoji">{'✅' if success_count == total_count else '⚠️'}</div>
            <h1>Installation {'Complete' if success_count == total_count else 'Partially Complete'}</h1>
            <p>Installed to {success_count} out of {total_count} workspace(s).</p>

            {results_html}

            <p style="margin-top: 2rem;">
                You can now return to Frame.io and use the installed custom actions.
            </p>
        </div>
    </body>
    </html>
    """


def render_manage_page(installations: list[InstallationRecord], base_url: str) -> str:
    """Render manage installations page.

    Args:
        installations: List of InstallationRecord objects.
        base_url: Base URL for actions.

    Returns:
        HTML string for manage page.
    """
    if not installations:
        return f"""
        <html>
        <head>
            <title>Manage Installations</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    max-width: 800px;
                    margin: 2rem auto;
                    padding: 2rem;
                    background: #f7fafc;
                }}
                .container {{
                    background: white;
                    padding: 2rem;
                    border-radius: 0.5rem;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                    text-align: center;
                }}
                h1 {{ color: #2d3748; }}
                p {{ color: #718096; line-height: 1.6; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>No Installations Found</h1>
                <p>You haven't installed this app to any workspaces yet.</p>
                <a href="{base_url}/install" style="color: #667eea;">Install Now</a>
            </div>
        </body>
        </html>
        """

    installations_html = ""
    for installation in installations:
        action_count = len(installation.actions)
        webhook_count = len(installation.webhooks)
        installations_html += f"""
        <div class="installation-item">
            <div>
                <strong>Workspace:</strong> {installation.workspace_id}<br>
                <strong>Installed:</strong> {installation.installed_at.strftime('%Y-%m-%d %H:%M')}<br>
                <strong>Actions:</strong> {action_count} | <strong>Webhooks:</strong> {webhook_count}
            </div>
            <form method="POST" action="{base_url}/install/uninstall" style="display: inline;">
                <input type="hidden" name="workspace_id" value="{installation.workspace_id}">
                <button type="submit" class="uninstall-btn" onclick="return confirm('Are you sure you want to uninstall from this workspace?');">
                    Uninstall
                </button>
            </form>
        </div>
        """

    return f"""
    <html>
    <head>
        <title>Manage Installations</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 800px;
                margin: 2rem auto;
                padding: 2rem;
                background: #f7fafc;
            }}
            .container {{
                background: white;
                padding: 2rem;
                border-radius: 0.5rem;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }}
            h1 {{ color: #2d3748; margin-top: 0; }}
            .installation-item {{
                padding: 1rem;
                border: 1px solid #e2e8f0;
                border-radius: 0.375rem;
                margin-bottom: 1rem;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .uninstall-btn {{
                background: #e53e3e;
                color: white;
                padding: 0.5rem 1rem;
                border: none;
                border-radius: 0.375rem;
                cursor: pointer;
            }}
            .uninstall-btn:hover {{
                background: #c53030;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Manage Installations</h1>
            {installations_html}
        </div>
    </body>
    </html>
    """
