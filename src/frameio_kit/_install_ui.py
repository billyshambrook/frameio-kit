"""UI rendering functions for the installation flow.

This module provides HTML rendering for the installation landing page,
workspace selection, and result pages.
"""

import html
from typing import Any

from ._install_models import InstallationRecord
from ._manifest import AppManifest


def escape_html(text: str) -> str:
    """Escape HTML special characters to prevent XSS attacks.

    Args:
        text: Text to escape.

    Returns:
        HTML-safe escaped text.
    """
    return html.escape(text, quote=True)


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
        action_cards = ""
        for action in manifest.actions:
            action_cards += f"""
            <div class="capability-card">
                <div class="card-icon">⚡</div>
                <div class="card-content">
                    <h3 class="card-title">{action.name}</h3>
                    <p class="card-description">{action.description}</p>
                </div>
            </div>
            """
        actions_html = f"""
        <h2 class="section-heading">Custom Actions</h2>
        <div class="capabilities-grid">
            {action_cards}
        </div>
        """

    webhooks_html = ""
    if manifest.webhooks:
        event_count = sum(len(webhook.event_types) for webhook in manifest.webhooks)
        event_list = []
        for webhook in manifest.webhooks:
            event_list.extend(webhook.event_types)
        event_preview = ", ".join(event_list[:3])
        if len(event_list) > 3:
            event_preview += f" +{len(event_list) - 3} more"

        webhooks_html = f"""
        <div class="webhooks-note">
            <div class="note-header">
                <svg class="note-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
                <span>Listens to {event_count} webhook event{'s' if event_count != 1 else ''}</span>
            </div>
            <div class="note-detail">{event_preview}</div>
        </div>
        """

    icon_html = ""
    if manifest.icon_url:
        icon_html = f'<img src="{manifest.icon_url}" alt="{manifest.name}" class="app-icon">'

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Install {manifest.name}</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', sans-serif;
                background: linear-gradient(to bottom right, #6366f1, #8b5cf6, #d946ef);
                min-height: 100vh;
                padding: 3rem 1.5rem;
                display: flex;
                align-items: center;
                justify-content: center;
            }}

            .container {{
                background: white;
                max-width: 720px;
                width: 100%;
                border-radius: 1.5rem;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
                overflow: hidden;
            }}

            .hero {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 3rem 2.5rem;
                text-align: center;
                color: white;
            }}

            .app-icon {{
                width: 80px;
                height: 80px;
                border-radius: 1.25rem;
                margin: 0 auto 1.5rem;
                display: block;
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
            }}

            .hero h1 {{
                font-size: 2rem;
                font-weight: 700;
                margin-bottom: 0.75rem;
                letter-spacing: -0.025em;
            }}

            .hero p {{
                font-size: 1.125rem;
                opacity: 0.95;
                line-height: 1.6;
            }}

            .content {{
                padding: 2.5rem;
            }}

            .section-heading {{
                font-size: 0.875rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.1em;
                color: #6b7280;
                margin-bottom: 1.25rem;
            }}

            .capabilities-grid {{
                display: grid;
                gap: 1rem;
            }}

            .capability-card {{
                display: flex;
                gap: 1rem;
                padding: 1.25rem;
                background: #f9fafb;
                border: 1px solid #e5e7eb;
                border-radius: 0.75rem;
                transition: all 0.2s ease;
            }}

            .capability-card:hover {{
                background: #f3f4f6;
                border-color: #d1d5db;
                transform: translateY(-2px);
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            }}

            .card-icon {{
                flex-shrink: 0;
                width: 40px;
                height: 40px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 0.5rem;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.25rem;
            }}

            .card-content {{
                flex: 1;
            }}

            .card-title {{
                font-size: 1rem;
                font-weight: 600;
                color: #111827;
                margin-bottom: 0.25rem;
            }}

            .card-description {{
                font-size: 0.875rem;
                color: #6b7280;
                line-height: 1.5;
            }}

            .webhooks-note {{
                background: #f9fafb;
                border: 1px solid #e5e7eb;
                border-radius: 0.5rem;
                padding: 1rem;
                margin-top: 1.5rem;
            }}

            .note-header {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                font-size: 0.875rem;
                font-weight: 500;
                color: #6b7280;
                margin-bottom: 0.25rem;
            }}

            .note-icon {{
                width: 16px;
                height: 16px;
                flex-shrink: 0;
            }}

            .note-detail {{
                font-size: 0.8125rem;
                color: #9ca3af;
                font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
                padding-left: 1.5rem;
            }}

            .install-section {{
                background: #f9fafb;
                padding: 2rem;
                text-align: center;
                border-top: 1px solid #e5e7eb;
            }}

            .install-description {{
                color: #6b7280;
                font-size: 0.9375rem;
                line-height: 1.6;
                margin-bottom: 1.5rem;
            }}

            .install-btn {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 0.875rem 2rem;
                border-radius: 0.75rem;
                font-size: 1rem;
                font-weight: 600;
                text-decoration: none;
                transition: all 0.2s ease;
                box-shadow: 0 4px 14px rgba(102, 126, 234, 0.4);
            }}

            .install-btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 8px 20px rgba(102, 126, 234, 0.5);
            }}

            .install-btn:active {{
                transform: translateY(0);
            }}

            @media (max-width: 640px) {{
                body {{
                    padding: 1.5rem 1rem;
                }}

                .hero {{
                    padding: 2rem 1.5rem;
                }}

                .hero h1 {{
                    font-size: 1.5rem;
                }}

                .content {{
                    padding: 1.5rem;
                }}

                .install-section {{
                    padding: 1.5rem;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="hero">
                {icon_html}
                <h1>{manifest.name}</h1>
                <p>{manifest.description}</p>
            </div>

            <div class="content">
                {actions_html}
                {webhooks_html}
            </div>

            <div class="install-section">
                <p class="install-description">
                    Sign in with Adobe to select which Frame.io workspaces to install this app to.
                </p>
                <a href="{base_url}/install/oauth/login" class="install-btn">
                    Install to Frame.io
                </a>
            </div>
        </div>
    </body>
    </html>
    """


def render_workspace_selection(
    workspaces: list[dict[str, Any]], base_url: str, session_id: str
) -> str:
    """Render workspace selection page.

    Args:
        workspaces: List of workspace dicts with 'id', 'name', and 'status'.
            status can be: 'not_installed', 'installed', or 'update_available'
        base_url: Base URL for form submission.
        session_id: Session ID for the installation flow.

    Returns:
        HTML string for workspace selection.
    """
    workspace_cards = ""
    all_workspace_ids = []
    has_installed = False

    for ws in workspaces:
        status = ws.get("status", "not_installed")
        all_workspace_ids.append(ws["id"])

        # Pre-check installed or update available workspaces
        is_checked = status in ("installed", "update_available")
        checked_attr = "checked" if is_checked else ""

        if status in ("installed", "update_available"):
            has_installed = True

        # Status badge HTML
        status_badge = ""
        if status == "installed":
            status_badge = '<span class="status-badge status-installed">✓ Installed</span>'
        elif status == "update_available":
            status_badge = '<span class="status-badge status-update">↻ Update Available</span>'

        workspace_name = escape_html(ws["name"])
        workspace_id = escape_html(ws["id"])

        workspace_cards += f"""
        <label class="workspace-card" for="ws_{workspace_id}">
            <input type="checkbox" name="workspace_ids" value="{workspace_id}" id="ws_{workspace_id}" {checked_attr}>
            <div class="workspace-card-content">
                <div class="workspace-icon">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"></path>
                    </svg>
                </div>
                <div class="workspace-info">
                    <div class="workspace-name">{workspace_name}</div>
                    {status_badge}
                </div>
                <div class="checkmark">
                    <svg fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"></path>
                    </svg>
                </div>
            </div>
        </label>
        """

    # Create hidden field with all workspace IDs for server-side comparison
    all_ws_ids_value = ",".join(all_workspace_ids)

    # Info text explaining uninstall behavior
    uninstall_info = ""
    if has_installed:
        uninstall_info = """
        <div class="selection-info uninstall-warning">
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
            </svg>
            <span class="selection-info-text"><strong>Note:</strong> Unchecking an installed workspace will uninstall the app from that workspace.</span>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Select Workspaces</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', sans-serif;
                background: linear-gradient(to bottom right, #6366f1, #8b5cf6, #d946ef);
                min-height: 100vh;
                padding: 3rem 1.5rem;
                display: flex;
                align-items: center;
                justify-content: center;
            }}

            .container {{
                background: white;
                max-width: 720px;
                width: 100%;
                border-radius: 1.5rem;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
                overflow: hidden;
            }}

            .hero {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 3rem 2.5rem;
                text-align: center;
                color: white;
            }}

            .hero h1 {{
                font-size: 2rem;
                font-weight: 700;
                margin-bottom: 0.75rem;
                letter-spacing: -0.025em;
            }}

            .hero p {{
                font-size: 1.125rem;
                opacity: 0.95;
                line-height: 1.6;
            }}

            .content {{
                padding: 2.5rem;
            }}

            .selection-info {{
                background: #f9fafb;
                border: 1px solid #e5e7eb;
                border-radius: 0.75rem;
                padding: 1rem 1.25rem;
                margin-bottom: 1rem;
                display: flex;
                align-items: center;
                gap: 0.75rem;
            }}

            .selection-info svg {{
                width: 20px;
                height: 20px;
                color: #6b7280;
                flex-shrink: 0;
            }}

            .selection-info-text {{
                color: #6b7280;
                font-size: 0.9375rem;
                line-height: 1.5;
            }}

            .uninstall-warning {{
                background: #fef3c7;
                border-color: #fbbf24;
                margin-bottom: 1.5rem;
            }}

            .uninstall-warning svg {{
                color: #d97706;
            }}

            .uninstall-warning .selection-info-text {{
                color: #92400e;
            }}

            .workspaces-grid {{
                display: grid;
                gap: 1rem;
                margin-bottom: 2rem;
            }}

            .workspace-card {{
                position: relative;
                display: block;
                cursor: pointer;
            }}

            .workspace-card input[type="checkbox"] {{
                position: absolute;
                opacity: 0;
                pointer-events: none;
            }}

            .workspace-card-content {{
                display: flex;
                align-items: center;
                gap: 1rem;
                padding: 1.25rem;
                background: #f9fafb;
                border: 2px solid #e5e7eb;
                border-radius: 0.75rem;
                transition: all 0.2s ease;
            }}

            .workspace-card:hover .workspace-card-content {{
                background: #f3f4f6;
                border-color: #d1d5db;
            }}

            .workspace-card input[type="checkbox"]:checked ~ .workspace-card-content {{
                background: #ede9fe;
                border-color: #8b5cf6;
            }}

            .workspace-icon {{
                flex-shrink: 0;
                width: 40px;
                height: 40px;
                background: white;
                border-radius: 0.5rem;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #6b7280;
            }}

            .workspace-icon svg {{
                width: 24px;
                height: 24px;
            }}

            .workspace-card input[type="checkbox"]:checked ~ .workspace-card-content .workspace-icon {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }}

            .workspace-info {{
                flex: 1;
                display: flex;
                flex-direction: column;
                gap: 0.25rem;
            }}

            .workspace-name {{
                font-size: 1rem;
                font-weight: 500;
                color: #111827;
            }}

            .status-badge {{
                font-size: 0.75rem;
                font-weight: 500;
                padding: 0.125rem 0.5rem;
                border-radius: 0.375rem;
                display: inline-block;
                width: fit-content;
            }}

            .status-installed {{
                background: #d1fae5;
                color: #065f46;
            }}

            .status-update {{
                background: #fed7aa;
                color: #92400e;
            }}

            .checkmark {{
                flex-shrink: 0;
                width: 24px;
                height: 24px;
                border-radius: 50%;
                border: 2px solid #d1d5db;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                transition: all 0.2s ease;
            }}

            .checkmark svg {{
                width: 16px;
                height: 16px;
                opacity: 0;
                transition: opacity 0.2s ease;
            }}

            .workspace-card input[type="checkbox"]:checked ~ .workspace-card-content .checkmark {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-color: #667eea;
            }}

            .workspace-card input[type="checkbox"]:checked ~ .workspace-card-content .checkmark svg {{
                opacity: 1;
            }}

            .install-section {{
                background: #f9fafb;
                padding: 2rem;
                text-align: center;
                border-top: 1px solid #e5e7eb;
            }}

            .install-btn {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 0.875rem 2rem;
                border: none;
                border-radius: 0.75rem;
                font-size: 1rem;
                font-weight: 600;
                text-decoration: none;
                cursor: pointer;
                transition: all 0.2s ease;
                box-shadow: 0 4px 14px rgba(102, 126, 234, 0.4);
            }}

            .install-btn:hover:not(:disabled) {{
                transform: translateY(-2px);
                box-shadow: 0 8px 20px rgba(102, 126, 234, 0.5);
            }}

            .install-btn:active:not(:disabled) {{
                transform: translateY(0);
            }}

            .install-btn:disabled {{
                opacity: 0.5;
                cursor: not-allowed;
            }}

            @media (max-width: 640px) {{
                body {{
                    padding: 1.5rem 1rem;
                }}

                .hero {{
                    padding: 2rem 1.5rem;
                }}

                .hero h1 {{
                    font-size: 1.5rem;
                }}

                .content {{
                    padding: 1.5rem;
                }}

                .install-section {{
                    padding: 1.5rem;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="hero">
                <h1>Select Workspaces</h1>
                <p>Choose which Frame.io workspaces to install this app to</p>
            </div>

            <div class="content">
                <div class="selection-info">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    <span class="selection-info-text">Select workspaces to install or uninstall the app</span>
                </div>

                {uninstall_info}

                <form method="POST" action="{base_url}/install/process?session={session_id}">
                    <input type="hidden" name="all_workspace_ids" value="{all_ws_ids_value}">
                    <div class="workspaces-grid">
                        {workspace_cards}
                    </div>

                    <div class="install-section">
                        <button type="submit" id="install-btn" class="install-btn">
                            Apply Changes
                        </button>
                    </div>
                </form>
            </div>
        </div>

        <script>
            // Handle form submission
            document.querySelector('form').addEventListener('submit', function(e) {{
                const button = document.getElementById('install-btn');
                button.disabled = true;
                button.textContent = 'Processing...';
            }});
        </script>
    </body>
    </html>
    """


def render_process_results_page(
    install_results: dict[str, bool],
    install_errors: dict[str, str],
    uninstall_results: dict[str, bool],
    uninstall_errors: dict[str, str],
) -> str:
    """Render installation and uninstallation results page.

    Args:
        install_results: Dict mapping workspace_id to success status for installations.
        install_errors: Dict mapping workspace_id to error messages for installations.
        uninstall_results: Dict mapping workspace_id to success status for uninstalls.
        uninstall_errors: Dict mapping workspace_id to error messages for uninstalls.

    Returns:
        HTML string for results page.
    """
    install_success_count = sum(1 for v in install_results.values() if v)
    install_total_count = len(install_results)
    uninstall_success_count = sum(1 for v in uninstall_results.values() if v)
    uninstall_total_count = len(uninstall_results)

    all_success = (
        (install_success_count == install_total_count or install_total_count == 0)
        and (uninstall_success_count == uninstall_total_count or uninstall_total_count == 0)
    )

    # Build install success items
    install_success_items = ""
    for ws_id, success in install_results.items():
        if success:
            install_success_items += f"""
            <div class="result-card success">
                <div class="result-icon">
                    <svg fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                    </svg>
                </div>
                <div class="result-content">
                    <div class="result-title">Successfully installed</div>
                    <div class="result-detail">Workspace ID: {ws_id}</div>
                </div>
            </div>
            """

    # Build install error items
    install_error_items = ""
    for ws_id, error in install_errors.items():
        install_error_items += f"""
        <div class="result-card error">
            <div class="result-icon">
                <svg fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                </svg>
            </div>
            <div class="result-content">
                <div class="result-title">Installation failed</div>
                <div class="result-detail">Workspace ID: {ws_id}</div>
                <div class="result-error">{error}</div>
            </div>
        </div>
        """

    # Build uninstall success items
    uninstall_success_items = ""
    for ws_id, success in uninstall_results.items():
        if success:
            uninstall_success_items += f"""
            <div class="result-card success">
                <div class="result-icon">
                    <svg fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                    </svg>
                </div>
                <div class="result-content">
                    <div class="result-title">Successfully uninstalled</div>
                    <div class="result-detail">Workspace ID: {ws_id}</div>
                </div>
            </div>
            """

    # Build uninstall error items
    uninstall_error_items = ""
    for ws_id, error in uninstall_errors.items():
        uninstall_error_items += f"""
        <div class="result-card error">
            <div class="result-icon">
                <svg fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                </svg>
            </div>
            <div class="result-content">
                <div class="result-title">Uninstall failed</div>
                <div class="result-detail">Workspace ID: {ws_id}</div>
                <div class="result-error">{error}</div>
            </div>
        </div>
        """

    # Build sections HTML
    install_section = ""
    if install_total_count > 0:
        install_section = f"""
        <div class="results-section">
            <div class="section-label">Installations ({install_success_count}/{install_total_count} successful)</div>
            {install_success_items}
            {install_error_items}
        </div>
        """

    uninstall_section = ""
    if uninstall_total_count > 0:
        uninstall_section = f"""
        <div class="results-section">
            <div class="section-label">Uninstalls ({uninstall_success_count}/{uninstall_total_count} successful)</div>
            {uninstall_success_items}
            {uninstall_error_items}
        </div>
        """

    # Summary message
    summary_parts = []
    if install_total_count > 0:
        summary_parts.append(f"<strong>{install_success_count}/{install_total_count}</strong> installation(s)")
    if uninstall_total_count > 0:
        summary_parts.append(f"<strong>{uninstall_success_count}/{uninstall_total_count}</strong> uninstall(s)")

    summary_text = " and ".join(summary_parts) + " completed successfully" if summary_parts else "No changes made"

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Installation Complete</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', sans-serif;
                background: linear-gradient(to bottom right, #6366f1, #8b5cf6, #d946ef);
                min-height: 100vh;
                padding: 3rem 1.5rem;
                display: flex;
                align-items: center;
                justify-content: center;
            }}

            .container {{
                background: white;
                max-width: 720px;
                width: 100%;
                border-radius: 1.5rem;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
                overflow: hidden;
            }}

            .hero {{
                background: linear-gradient(135deg, {"#10b981 0%, #059669 100%" if all_success else "#f59e0b 0%, #d97706 100%"});
                padding: 3rem 2.5rem;
                text-align: center;
                color: white;
            }}

            .status-icon {{
                width: 80px;
                height: 80px;
                margin: 0 auto 1.5rem;
                background: rgba(255, 255, 255, 0.2);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
            }}

            .status-icon svg {{
                width: 48px;
                height: 48px;
            }}

            .hero h1 {{
                font-size: 2rem;
                font-weight: 700;
                margin-bottom: 0.75rem;
                letter-spacing: -0.025em;
            }}

            .hero p {{
                font-size: 1.125rem;
                opacity: 0.95;
                line-height: 1.6;
            }}

            .content {{
                padding: 2.5rem;
            }}

            .summary {{
                background: #f9fafb;
                border: 1px solid #e5e7eb;
                border-radius: 0.75rem;
                padding: 1.25rem;
                margin-bottom: 2rem;
                text-align: center;
            }}

            .summary-text {{
                color: #6b7280;
                font-size: 0.9375rem;
                line-height: 1.6;
            }}

            .results-section {{
                margin-bottom: 2rem;
            }}

            .section-label {{
                font-size: 0.875rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.1em;
                color: #6b7280;
                margin-bottom: 1rem;
            }}

            .result-card {{
                display: flex;
                gap: 1rem;
                padding: 1.25rem;
                border-radius: 0.75rem;
                margin-bottom: 0.75rem;
            }}

            .result-card:last-child {{
                margin-bottom: 0;
            }}

            .result-card.success {{
                background: #f0fdf4;
                border: 1px solid #bbf7d0;
            }}

            .result-card.error {{
                background: #fef2f2;
                border: 1px solid #fecaca;
            }}

            .result-icon {{
                flex-shrink: 0;
                width: 40px;
                height: 40px;
                border-radius: 0.5rem;
                display: flex;
                align-items: center;
                justify-content: center;
            }}

            .result-card.success .result-icon {{
                background: #10b981;
                color: white;
            }}

            .result-card.error .result-icon {{
                background: #ef4444;
                color: white;
            }}

            .result-icon svg {{
                width: 24px;
                height: 24px;
            }}

            .result-content {{
                flex: 1;
            }}

            .result-title {{
                font-size: 1rem;
                font-weight: 600;
                margin-bottom: 0.25rem;
            }}

            .result-card.success .result-title {{
                color: #065f46;
            }}

            .result-card.error .result-title {{
                color: #991b1b;
            }}

            .result-detail {{
                font-size: 0.875rem;
                color: #6b7280;
                font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
            }}

            .result-error {{
                margin-top: 0.5rem;
                font-size: 0.875rem;
                color: #991b1b;
                line-height: 1.5;
            }}

            .footer {{
                background: #f9fafb;
                padding: 2rem;
                text-align: center;
                border-top: 1px solid #e5e7eb;
            }}

            .footer-text {{
                color: #6b7280;
                font-size: 0.9375rem;
                line-height: 1.6;
            }}

            @media (max-width: 640px) {{
                body {{
                    padding: 1.5rem 1rem;
                }}

                .hero {{
                    padding: 2rem 1.5rem;
                }}

                .hero h1 {{
                    font-size: 1.5rem;
                }}

                .content {{
                    padding: 1.5rem;
                }}

                .footer {{
                    padding: 1.5rem;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="hero">
                <div class="status-icon">
                    <svg fill="currentColor" viewBox="0 0 20 20">
                        {"<path fill-rule='evenodd' d='M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z' clip-rule='evenodd'></path>" if all_success else "<path fill-rule='evenodd' d='M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z' clip-rule='evenodd'></path>"}
                    </svg>
                </div>
                <h1>{"Changes Complete!" if all_success else "Changes Partially Complete"}</h1>
                <p>{"All operations completed successfully" if all_success else "Some operations encountered issues"}</p>
            </div>

            <div class="content">
                <div class="summary">
                    <p class="summary-text">
                        {summary_text}
                    </p>
                </div>

                {install_section}
                {uninstall_section}
            </div>

            <div class="footer">
                <p class="footer-text">
                    {"You can now return to Frame.io and start using your app." if all_success else "Please review any errors above. Successfully installed workspaces are ready to use."}
                </p>
            </div>
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
    all_success = success_count == total_count

    success_items = ""
    for ws_id, success in results.items():
        if success:
            success_items += f"""
            <div class="result-card success">
                <div class="result-icon">
                    <svg fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                    </svg>
                </div>
                <div class="result-content">
                    <div class="result-title">Successfully installed</div>
                    <div class="result-detail">Workspace ID: {ws_id}</div>
                </div>
            </div>
            """

    error_items = ""
    for ws_id, error in errors.items():
        error_items += f"""
        <div class="result-card error">
            <div class="result-icon">
                <svg fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                </svg>
            </div>
            <div class="result-content">
                <div class="result-title">Installation failed</div>
                <div class="result-detail">Workspace ID: {ws_id}</div>
                <div class="result-error">{error}</div>
            </div>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Installation Complete</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', sans-serif;
                background: linear-gradient(to bottom right, #6366f1, #8b5cf6, #d946ef);
                min-height: 100vh;
                padding: 3rem 1.5rem;
                display: flex;
                align-items: center;
                justify-content: center;
            }}

            .container {{
                background: white;
                max-width: 720px;
                width: 100%;
                border-radius: 1.5rem;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
                overflow: hidden;
            }}

            .hero {{
                background: linear-gradient(135deg, {"#10b981 0%, #059669 100%" if all_success else "#f59e0b 0%, #d97706 100%"});
                padding: 3rem 2.5rem;
                text-align: center;
                color: white;
            }}

            .status-icon {{
                width: 80px;
                height: 80px;
                margin: 0 auto 1.5rem;
                background: rgba(255, 255, 255, 0.2);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
            }}

            .status-icon svg {{
                width: 48px;
                height: 48px;
            }}

            .hero h1 {{
                font-size: 2rem;
                font-weight: 700;
                margin-bottom: 0.75rem;
                letter-spacing: -0.025em;
            }}

            .hero p {{
                font-size: 1.125rem;
                opacity: 0.95;
                line-height: 1.6;
            }}

            .content {{
                padding: 2.5rem;
            }}

            .summary {{
                background: #f9fafb;
                border: 1px solid #e5e7eb;
                border-radius: 0.75rem;
                padding: 1.25rem;
                margin-bottom: 2rem;
                text-align: center;
            }}

            .summary-text {{
                color: #6b7280;
                font-size: 0.9375rem;
                line-height: 1.6;
            }}

            .results-section {{
                margin-bottom: 2rem;
            }}

            .section-label {{
                font-size: 0.875rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.1em;
                color: #6b7280;
                margin-bottom: 1rem;
            }}

            .result-card {{
                display: flex;
                gap: 1rem;
                padding: 1.25rem;
                border-radius: 0.75rem;
                margin-bottom: 0.75rem;
            }}

            .result-card:last-child {{
                margin-bottom: 0;
            }}

            .result-card.success {{
                background: #f0fdf4;
                border: 1px solid #bbf7d0;
            }}

            .result-card.error {{
                background: #fef2f2;
                border: 1px solid #fecaca;
            }}

            .result-icon {{
                flex-shrink: 0;
                width: 40px;
                height: 40px;
                border-radius: 0.5rem;
                display: flex;
                align-items: center;
                justify-content: center;
            }}

            .result-card.success .result-icon {{
                background: #10b981;
                color: white;
            }}

            .result-card.error .result-icon {{
                background: #ef4444;
                color: white;
            }}

            .result-icon svg {{
                width: 24px;
                height: 24px;
            }}

            .result-content {{
                flex: 1;
            }}

            .result-title {{
                font-size: 1rem;
                font-weight: 600;
                margin-bottom: 0.25rem;
            }}

            .result-card.success .result-title {{
                color: #065f46;
            }}

            .result-card.error .result-title {{
                color: #991b1b;
            }}

            .result-detail {{
                font-size: 0.875rem;
                color: #6b7280;
                font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
            }}

            .result-error {{
                margin-top: 0.5rem;
                font-size: 0.875rem;
                color: #991b1b;
                line-height: 1.5;
            }}

            .footer {{
                background: #f9fafb;
                padding: 2rem;
                text-align: center;
                border-top: 1px solid #e5e7eb;
            }}

            .footer-text {{
                color: #6b7280;
                font-size: 0.9375rem;
                line-height: 1.6;
            }}

            @media (max-width: 640px) {{
                body {{
                    padding: 1.5rem 1rem;
                }}

                .hero {{
                    padding: 2rem 1.5rem;
                }}

                .hero h1 {{
                    font-size: 1.5rem;
                }}

                .content {{
                    padding: 1.5rem;
                }}

                .footer {{
                    padding: 1.5rem;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="hero">
                <div class="status-icon">
                    <svg fill="currentColor" viewBox="0 0 20 20">
                        {"<path fill-rule='evenodd' d='M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z' clip-rule='evenodd'></path>" if all_success else "<path fill-rule='evenodd' d='M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z' clip-rule='evenodd'></path>"}
                    </svg>
                </div>
                <h1>{"Installation Complete!" if all_success else "Installation Partially Complete"}</h1>
                <p>{"All workspaces have been configured successfully" if all_success else "Some workspaces encountered issues during installation"}</p>
            </div>

            <div class="content">
                <div class="summary">
                    <p class="summary-text">
                        Successfully installed to <strong>{success_count}</strong> out of <strong>{total_count}</strong> workspace{"s" if total_count != 1 else ""}
                    </p>
                </div>

                {f'''
                <div class="results-section">
                    <div class="section-label">Successful Installations</div>
                    {success_items}
                </div>
                ''' if success_items else ''}

                {f'''
                <div class="results-section">
                    <div class="section-label">Failed Installations</div>
                    {error_items}
                </div>
                ''' if error_items else ''}
            </div>

            <div class="footer">
                <p class="footer-text">
                    {"You can now return to Frame.io and start using your custom actions and webhooks." if all_success else "Please review any errors above. Successfully installed workspaces are ready to use in Frame.io."}
                </p>
            </div>
        </div>
    </body>
    </html>
    """


def render_manage_page(installations: list[InstallationRecord], base_url: str, user_id: str | None = None) -> str:
    """Render manage installations page.

    Args:
        installations: List of InstallationRecord objects.
        base_url: Base URL for actions.
        user_id: User ID for uninstall actions.

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
        user_id_field = f'<input type="hidden" name="user_id" value="{installation.user_id}">' if installation.user_id else ""

        installations_html += f"""
        <div class="installation-item">
            <div>
                <strong>Workspace:</strong> {installation.workspace_id}<br>
                <strong>Installed:</strong> {installation.installed_at.strftime("%Y-%m-%d %H:%M")}<br>
                <strong>Actions:</strong> {action_count} | <strong>Webhooks:</strong> {webhook_count}
            </div>
            <form method="POST" action="{base_url}/install/uninstall" style="display: inline;">
                <input type="hidden" name="workspace_id" value="{installation.workspace_id}">
                {user_id_field}
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
