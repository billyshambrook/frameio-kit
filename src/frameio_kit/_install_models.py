"""Data models for the app installation system.

This module defines the models used to track installations, handler manifests,
and installation diffs for the self-service installation UI.
"""

from datetime import datetime

from pydantic import BaseModel


class WebhookRecord(BaseModel):
    """Record of a webhook created during installation.

    Attributes:
        webhook_id: Frame.io webhook ID.
        secret: Encrypted signing secret returned at creation time.
        events: List of event types the webhook listens for.
        url: Callback URL the webhook posts to.
    """

    webhook_id: str
    secret: str
    events: list[str]
    url: str


class ActionRecord(BaseModel):
    """Record of a custom action created during installation.

    Attributes:
        action_id: Frame.io custom action ID.
        secret: Encrypted signing secret returned at creation time.
        event_type: The event type string for this action.
        name: Display name of the action.
        description: Description of the action.
        url: Callback URL the action posts to.
    """

    action_id: str
    secret: str
    event_type: str
    name: str
    description: str
    url: str


class Installation(BaseModel):
    """Record of a complete app installation for a workspace.

    Attributes:
        account_id: Frame.io account ID.
        workspace_id: Frame.io workspace ID.
        installed_at: When the installation was first created.
        updated_at: When the installation was last updated.
        installed_by_user_id: User ID of the admin who installed the app.
        webhook: The consolidated webhook record, if any webhook handlers exist.
        actions: List of custom action records, one per action handler.
    """

    account_id: str
    workspace_id: str
    installed_at: datetime
    updated_at: datetime
    installed_by_user_id: str
    webhook: WebhookRecord | None = None
    actions: list[ActionRecord] = []


class ActionManifestEntry(BaseModel):
    """An action entry in the handler manifest.

    Attributes:
        event_type: The event type string for this action.
        name: Display name of the action.
        description: Description of the action.
    """

    event_type: str
    name: str
    description: str


class HandlerManifest(BaseModel):
    """What the app needs installed, derived from registered handlers.

    Built at startup by introspecting ``@app.on_webhook`` and ``@app.on_action``
    decorators.

    Attributes:
        webhook_events: All webhook event types that need to be registered.
        actions: List of action entries that need custom actions created.
    """

    webhook_events: list[str]
    actions: list[ActionManifestEntry]


class InstallationDiff(BaseModel):
    """Structured diff between current manifest and existing installation.

    Used by the status template to display a human-readable diff to the admin
    before they confirm an update.

    Attributes:
        webhook_events_added: New webhook event types to add.
        webhook_events_removed: Webhook event types to remove.
        actions_added: New actions to create.
        actions_removed: Existing actions to delete.
        actions_modified: Actions with changed name or description.
    """

    webhook_events_added: list[str]
    webhook_events_removed: list[str]
    actions_added: list[ActionManifestEntry]
    actions_removed: list[ActionRecord]
    actions_modified: list[ActionManifestEntry]

    @property
    def has_changes(self) -> bool:
        """Whether there are any differences between manifest and installation."""
        return bool(
            self.webhook_events_added
            or self.webhook_events_removed
            or self.actions_added
            or self.actions_removed
            or self.actions_modified
        )
