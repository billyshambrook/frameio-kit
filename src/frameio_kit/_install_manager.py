"""Core installation logic for managing webhooks and custom actions.

This module provides the ``InstallationManager`` class which handles the full
lifecycle of app installations: creating, updating, and removing webhooks and
custom actions via the Frame.io API.
"""

import base64
import logging
import re
from collections.abc import Mapping
from datetime import datetime, timezone

from ._client import Client
from ._encryption import TokenEncryption
from ._install_models import (
    ActionManifestEntry,
    ActionRecord,
    HandlerManifest,
    Installation,
    InstallationDiff,
    WebhookRecord,
)
from ._storage import Storage

logger = logging.getLogger(__name__)

UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def validate_uuid(value: str, field_name: str) -> str:
    """Validate that a string is a valid UUID format.

    Args:
        value: The string to validate.
        field_name: Name of the field for error messages.

    Returns:
        The validated string.

    Raises:
        ValueError: If the string is not a valid UUID.
    """
    if not UUID_PATTERN.match(value):
        raise ValueError(f"Invalid {field_name}")
    return value


def _storage_key(account_id: str, workspace_id: str) -> str:
    """Build the storage key for an installation record."""
    return f"install:{account_id}:{workspace_id}"


class InstallationManager:
    """Manages the lifecycle of app installations for workspaces.

    Handles creating, updating, and deleting webhooks and custom actions
    via the Frame.io API, and persists installation records in Storage.

    Attributes:
        storage: Storage backend for installation records.
        encryption: Encryption for signing secrets at rest.
    """

    def __init__(
        self,
        storage: Storage,
        encryption: TokenEncryption,
        app_name: str,
        base_url: str | None = None,
    ) -> None:
        self.storage = storage
        self.encryption = encryption
        self._app_name = app_name
        self._base_url = base_url

    def build_manifest(
        self,
        webhook_handlers: Mapping[str, object],
        action_handlers: Mapping[str, object],
    ) -> HandlerManifest:
        """Build a handler manifest from registered handlers.

        Args:
            webhook_handlers: Dict of event_type -> handler registration.
            action_handlers: Dict of event_type -> handler registration with
                name and description attributes.

        Returns:
            A HandlerManifest describing what needs to be installed.
        """
        webhook_events = sorted(webhook_handlers.keys())
        actions = []
        for event_type, reg in sorted(action_handlers.items()):
            actions.append(
                ActionManifestEntry(
                    event_type=event_type,
                    name=getattr(reg, "name", "") or "",
                    description=getattr(reg, "description", "") or "",
                )
            )
        return HandlerManifest(webhook_events=webhook_events, actions=actions)

    async def get_installation(self, account_id: str, workspace_id: str) -> Installation | None:
        """Retrieve an existing installation record from Storage.

        Args:
            account_id: Frame.io account ID.
            workspace_id: Frame.io workspace ID.

        Returns:
            The Installation record, or None if not installed.
        """
        key = _storage_key(account_id, workspace_id)
        data = await self.storage.get(key)
        if data is None:
            return None

        # Decrypt secrets in the stored data
        installation = Installation.model_validate(data)
        if installation.webhook:
            installation.webhook = installation.webhook.model_copy(
                update={"secret": self._decrypt_secret(installation.webhook.secret)}
            )
        decrypted_actions = []
        for action in installation.actions:
            decrypted_actions.append(action.model_copy(update={"secret": self._decrypt_secret(action.secret)}))
        installation.actions = decrypted_actions

        return installation

    async def install(
        self,
        token: str,
        account_id: str,
        workspace_id: str,
        base_url: str,
        manifest: HandlerManifest,
    ) -> Installation:
        """Create a new installation for a workspace.

        Creates webhooks and custom actions via the Frame.io API using the
        installing user's OAuth access token.

        Args:
            token: OAuth access token of the installing user.
            account_id: Frame.io account ID.
            workspace_id: Frame.io workspace ID.
            base_url: Public callback URL for webhooks/actions.
            manifest: What handlers need to be installed.

        Returns:
            The new Installation record.
        """
        from frameio.webhooks.types import WebhookCreateParamsData
        from frameio_experimental.custom_actions.types import ActionCreateParamsData

        client = Client(token=token, base_url=self._base_url)
        try:
            now = datetime.now(tz=timezone.utc)
            webhook_record: WebhookRecord | None = None
            action_records: list[ActionRecord] = []

            # Create consolidated webhook if there are webhook events
            if manifest.webhook_events:
                response = await client.webhooks.create(
                    account_id,
                    workspace_id,
                    data=WebhookCreateParamsData(
                        name=f"{self._app_name} Webhook",
                        url=base_url,
                        events=manifest.webhook_events,
                    ),
                )
                webhook_record = WebhookRecord(
                    webhook_id=response.data.id,
                    secret=response.data.secret,
                    events=list(manifest.webhook_events),
                    url=base_url,
                )

            # Create individual custom actions
            for action_entry in manifest.actions:
                response = await client.experimental.custom_actions.actions_create(
                    account_id,
                    workspace_id,
                    data=ActionCreateParamsData(
                        name=action_entry.name,
                        description=action_entry.description,
                        event=action_entry.event_type,
                        url=base_url,
                    ),
                )
                action_records.append(
                    ActionRecord(
                        action_id=response.data.id,
                        secret=response.data.secret,
                        event_type=action_entry.event_type,
                        name=action_entry.name,
                        description=action_entry.description,
                        url=base_url,
                    )
                )

            installation = Installation(
                account_id=account_id,
                workspace_id=workspace_id,
                installed_at=now,
                updated_at=now,
                webhook=webhook_record,
                actions=action_records,
            )

            await self._store_installation(installation)
            return installation

        finally:
            await client.close()

    async def update(
        self,
        token: str,
        account_id: str,
        workspace_id: str,
        base_url: str,
        manifest: HandlerManifest,
        existing: Installation,
    ) -> Installation:
        """Update an existing installation to match the current manifest.

        Performs targeted API calls: creates new resources, removes stale ones,
        patches modified ones, and leaves unchanged ones alone.

        Args:
            token: OAuth access token of the installing user.
            account_id: Frame.io account ID.
            workspace_id: Frame.io workspace ID.
            base_url: Public callback URL for webhooks/actions.
            manifest: Current handler manifest.
            existing: The existing Installation record.

        Returns:
            The updated Installation record.
        """
        from frameio.webhooks.types import WebhookCreateParamsData, WebhookUpdateParamsData
        from frameio_experimental.custom_actions.types import ActionCreateParamsData, ActionUpdateParamsData

        client = Client(token=token, base_url=self._base_url)
        try:
            now = datetime.now(tz=timezone.utc)
            webhook_record: WebhookRecord | None = None
            action_records: list[ActionRecord] = []

            # --- WEBHOOK DIFF ---
            manifest_events = set(manifest.webhook_events)
            existing_events = set(existing.webhook.events) if existing.webhook else set()

            if manifest_events and existing.webhook:
                if manifest_events != existing_events:
                    # PATCH existing webhook with updated events
                    await client.webhooks.update(
                        account_id,
                        existing.webhook.webhook_id,
                        data=WebhookUpdateParamsData(events=sorted(manifest_events)),
                    )
                    webhook_record = existing.webhook.model_copy(update={"events": sorted(manifest_events)})
                else:
                    # Unchanged
                    webhook_record = existing.webhook
            elif manifest_events and not existing.webhook:
                # CREATE new webhook
                response = await client.webhooks.create(
                    account_id,
                    workspace_id,
                    data=WebhookCreateParamsData(
                        name=f"{self._app_name} Webhook",
                        url=base_url,
                        events=sorted(manifest_events),
                    ),
                )
                webhook_record = WebhookRecord(
                    webhook_id=response.data.id,
                    secret=response.data.secret,
                    events=sorted(manifest_events),
                    url=base_url,
                )
            elif not manifest_events and existing.webhook:
                # DELETE existing webhook
                await client.webhooks.delete(account_id, existing.webhook.webhook_id)
                webhook_record = None
            # else: no manifest events and no existing webhook = nothing to do

            # --- ACTIONS DIFF ---
            existing_actions_by_event = {a.event_type: a for a in existing.actions}
            manifest_actions_by_event = {a.event_type: a for a in manifest.actions}

            for entry in manifest.actions:
                existing_action = existing_actions_by_event.get(entry.event_type)
                if existing_action is None:
                    # NEW action - CREATE
                    response = await client.experimental.custom_actions.actions_create(
                        account_id,
                        workspace_id,
                        data=ActionCreateParamsData(
                            name=entry.name,
                            description=entry.description,
                            event=entry.event_type,
                            url=base_url,
                        ),
                    )
                    action_records.append(
                        ActionRecord(
                            action_id=response.data.id,
                            secret=response.data.secret,
                            event_type=entry.event_type,
                            name=entry.name,
                            description=entry.description,
                            url=base_url,
                        )
                    )
                elif existing_action.name != entry.name or existing_action.description != entry.description:
                    # MODIFIED action - PATCH (keeps same secret)
                    await client.experimental.custom_actions.actions_update(
                        account_id,
                        existing_action.action_id,
                        data=ActionUpdateParamsData(
                            name=entry.name,
                            description=entry.description,
                        ),
                    )
                    action_records.append(
                        existing_action.model_copy(update={"name": entry.name, "description": entry.description})
                    )
                else:
                    # UNCHANGED - keep existing record
                    action_records.append(existing_action)

            # REMOVED actions - DELETE
            for event_type, existing_action in existing_actions_by_event.items():
                if event_type not in manifest_actions_by_event:
                    await client.experimental.custom_actions.actions_delete(account_id, existing_action.action_id)

            installation = existing.model_copy(
                update={
                    "updated_at": now,
                    "webhook": webhook_record,
                    "actions": action_records,
                },
            )

            await self._store_installation(installation)
            return installation

        finally:
            await client.close()

    async def uninstall(
        self,
        token: str,
        account_id: str,
        workspace_id: str,
        existing: Installation,
    ) -> None:
        """Remove all webhooks and custom actions for a workspace.

        Args:
            token: OAuth access token of the installing user.
            account_id: Frame.io account ID.
            workspace_id: Frame.io workspace ID.
            existing: The existing Installation record to remove.
        """
        client = Client(token=token, base_url=self._base_url)
        try:
            # Delete webhook
            if existing.webhook:
                await client.webhooks.delete(account_id, existing.webhook.webhook_id)

            # Delete all custom actions
            for action in existing.actions:
                await client.experimental.custom_actions.actions_delete(account_id, action.action_id)

            # Remove from storage
            key = _storage_key(account_id, workspace_id)
            await self.storage.delete(key)

        finally:
            await client.close()

    def needs_update(self, manifest: HandlerManifest, existing: Installation) -> bool:
        """Check if the installation needs updating.

        Args:
            manifest: Current handler manifest.
            existing: Existing installation record.

        Returns:
            True if there are differences requiring an update.
        """
        return self.compute_diff(manifest, existing).has_changes

    def compute_diff(self, manifest: HandlerManifest, existing: Installation) -> InstallationDiff:
        """Compute the diff between current manifest and existing installation.

        Args:
            manifest: Current handler manifest.
            existing: Existing installation record.

        Returns:
            Structured diff for UI display.
        """
        # Webhook events diff
        manifest_events = set(manifest.webhook_events)
        existing_events = set(existing.webhook.events) if existing.webhook else set()
        events_added = sorted(manifest_events - existing_events)
        events_removed = sorted(existing_events - manifest_events)

        # Actions diff (keyed by event_type)
        existing_actions_by_event = {a.event_type: a for a in existing.actions}
        manifest_actions_by_event = {a.event_type: a for a in manifest.actions}

        actions_added: list[ActionManifestEntry] = []
        actions_removed: list[ActionRecord] = []
        actions_modified: list[ActionManifestEntry] = []

        for entry in manifest.actions:
            existing_action = existing_actions_by_event.get(entry.event_type)
            if existing_action is None:
                actions_added.append(entry)
            elif existing_action.name != entry.name or existing_action.description != entry.description:
                actions_modified.append(entry)

        for event_type, existing_action in existing_actions_by_event.items():
            if event_type not in manifest_actions_by_event:
                actions_removed.append(existing_action)

        return InstallationDiff(
            webhook_events_added=events_added,
            webhook_events_removed=events_removed,
            actions_added=actions_added,
            actions_removed=actions_removed,
            actions_modified=actions_modified,
        )

    def _encrypt_secret(self, secret: str) -> str:
        """Encrypt a signing secret for storage."""
        encrypted = self.encryption.encrypt(secret.encode())
        return base64.b64encode(encrypted).decode("utf-8")

    def _decrypt_secret(self, encrypted_secret: str) -> str:
        """Decrypt a signing secret from storage."""
        encrypted = base64.b64decode(encrypted_secret)
        return self.encryption.decrypt(encrypted).decode()

    async def _store_installation(self, installation: Installation) -> None:
        """Encrypt secrets and store installation record."""
        # Create a copy with encrypted secrets for storage
        encrypted_webhook: WebhookRecord | None = None
        if installation.webhook:
            encrypted_webhook = installation.webhook.model_copy(
                update={"secret": self._encrypt_secret(installation.webhook.secret)}
            )

        encrypted_actions = []
        for action in installation.actions:
            encrypted_actions.append(action.model_copy(update={"secret": self._encrypt_secret(action.secret)}))

        encrypted_installation = installation.model_copy(
            update={"webhook": encrypted_webhook, "actions": encrypted_actions}
        )

        key = _storage_key(installation.account_id, installation.workspace_id)
        await self.storage.put(key, encrypted_installation.model_dump(mode="json"))
