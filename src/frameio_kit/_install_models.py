"""Data models for the app installation system.

This module defines the data structures used for tracking installations,
including installation records, installed actions, and installed webhooks.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class InstalledAction(BaseModel):
    """Represents a custom action that has been installed in a workspace.

    Attributes:
        action_id: Frame.io custom action ID.
        event_type: The event type for this action (e.g., "my_app.transcribe").
        name: Display name for the action.
        description: Description of what the action does.
        secret: Signing secret for this action (encrypted at rest).
        created_at: Timestamp when the action was created.
    """

    action_id: str
    event_type: str
    name: str
    description: str
    secret: str
    created_at: datetime = Field(default_factory=datetime.now)


class InstalledWebhook(BaseModel):
    """Represents a webhook that has been installed in a workspace.

    Attributes:
        webhook_id: Frame.io webhook ID.
        event_types: List of event types this webhook listens to.
        name: Name/description of the webhook.
        secret: Signing secret for this webhook (encrypted at rest).
        created_at: Timestamp when the webhook was created.
    """

    webhook_id: str
    event_types: list[str]
    name: str
    secret: str
    created_at: datetime = Field(default_factory=datetime.now)


class InstallationRecord(BaseModel):
    """Complete record of an installation in a workspace.

    This is stored in encrypted storage with key: `install:{workspace_id}`

    Attributes:
        workspace_id: Frame.io workspace ID where app is installed.
        account_id: Frame.io account ID associated with the workspace.
        user_id: ID of the user who performed the installation.
        installed_at: Timestamp when installation was first created.
        updated_at: Timestamp when installation was last updated.
        status: Current status of the installation.
        actions: List of installed custom actions.
        webhooks: List of installed webhooks.
        manifest_version: Hash of the app manifest at install time.
    """

    workspace_id: str
    account_id: str
    user_id: str
    installed_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    status: Literal["active", "error", "uninstalled"] = "active"
    actions: list[InstalledAction] = Field(default_factory=list)
    webhooks: list[InstalledWebhook] = Field(default_factory=list)
    manifest_version: str = ""


class UserInstallationIndex(BaseModel):
    """Quick lookup index of a user's installations.

    Stored with key: `install:index:{user_id}`

    Attributes:
        user_id: Frame.io user ID who installed the app.
        workspace_ids: List of workspace IDs where this user installed the app.
        updated_at: Timestamp when index was last updated.
    """

    user_id: str
    workspace_ids: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=datetime.now)


class InstallationConfig(BaseModel):
    """Configuration for app installation feature.

    Attributes:
        enabled: Whether installation feature is enabled.
        app_name: Display name for the app.
        app_description: Description of what the app does.
        app_icon_url: Optional URL to app icon/logo.
        include_actions: Optional list of action event_types to install. None means all.
        include_webhooks: Optional list of webhook event_types to install. None means all.
    """

    model_config = {"arbitrary_types_allowed": True}

    enabled: bool = True
    app_name: str
    app_description: str
    app_icon_url: str | None = None
    include_actions: list[str] | None = None
    include_webhooks: list[str] | None = None


class InstallationResult(BaseModel):
    """Result of an installation operation.

    Attributes:
        success: Whether the operation succeeded overall.
        workspace_results: Dict mapping workspace_id to success status.
        errors: Dict mapping workspace_id to error messages (if any).
    """

    success: bool
    workspace_results: dict[str, bool] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)
