"""Installation manager for creating and managing app installations.

This module handles the creation, update, and deletion of custom actions
and webhooks via the Frame.io APIs, along with managing installation records.
"""

import secrets
from datetime import datetime
from typing import TYPE_CHECKING

from frameio_experimental.client import AsyncFrameioExperimental
from key_value.aio.protocols import AsyncKeyValue

from ._client import Client
from ._encryption import TokenEncryption
from ._install_models import (
    InstallationRecord,
    InstallationResult,
    InstalledAction,
    InstalledWebhook,
    UserInstallationIndex,
)
from ._manifest import AppManifest

if TYPE_CHECKING:
    from ._app import App


class InstallationManager:
    """Manages app installations across workspaces.

    This class handles:
    - Creating custom actions and webhooks via Frame.io APIs
    - Storing installation records with encrypted secrets
    - Updating existing installations
    - Uninstalling and cleaning up resources

    Attributes:
        app: The App instance this manager is associated with.
        storage: Storage backend for installation records.
        encryption: Encryption for secrets.
        manifest: The app manifest to install.
    """

    def __init__(
        self,
        app: "App",
        storage: AsyncKeyValue,
        encryption: TokenEncryption,
        manifest: AppManifest,
    ) -> None:
        """Initialize installation manager.

        Args:
            app: The App instance.
            storage: Storage backend for installation records.
            encryption: TokenEncryption for securing secrets.
            manifest: The app manifest describing what to install.
        """
        self.app = app
        self.storage = storage
        self.encryption = encryption
        self.manifest = manifest

    def _make_installation_key(self, workspace_id: str) -> str:
        """Create storage key for installation record.

        Args:
            workspace_id: Frame.io workspace ID.

        Returns:
            Storage key string.
        """
        return f"install:{workspace_id}"

    def _make_index_key(self, user_id: str) -> str:
        """Create storage key for user installation index.

        Args:
            user_id: Frame.io user ID.

        Returns:
            Storage key string.
        """
        return f"install:index:{user_id}"

    async def install(
        self,
        user_id: str,
        user_token: str,
        workspace_ids: list[str],
    ) -> InstallationResult:
        """Install app to one or more workspaces.

        Args:
            user_id: Frame.io user ID performing the installation.
            user_token: OAuth access token for API calls.
            workspace_ids: List of workspace IDs to install to.

        Returns:
            InstallationResult with success/failure per workspace.
        """
        result = InstallationResult(success=True, workspace_results={}, errors={})

        # Create clients for API calls
        client = Client(token=user_token)
        exp_client = AsyncFrameioExperimental(api_key=user_token)

        try:
            for workspace_id in workspace_ids:
                try:
                    await self._install_workspace(
                        client=client,
                        exp_client=exp_client,
                        user_id=user_id,
                        workspace_id=workspace_id,
                    )
                    result.workspace_results[workspace_id] = True
                except Exception as e:
                    result.success = False
                    result.workspace_results[workspace_id] = False
                    result.errors[workspace_id] = str(e)

            # Update user installation index
            await self._update_user_index(user_id, workspace_ids, add=True)

        finally:
            await client.close()
            # AsyncFrameioExperimental doesn't have a close method, no need to close

        return result

    async def _install_workspace(
        self,
        client: Client,
        exp_client: AsyncFrameioExperimental,
        user_id: str,
        workspace_id: str,
    ) -> None:
        """Install app to a single workspace.

        Args:
            client: Frame.io API client.
            exp_client: Experimental API client for custom actions.
            user_id: User performing installation.
            workspace_id: Workspace to install to.
        """
        # Get workspace info to find account_id
        workspace = await client.workspaces.show(workspace_id)
        account_id = workspace.data.account_id

        # Check if already installed
        existing = await self.get_installation(workspace_id)
        if existing:
            # Already installed - could update instead
            raise ValueError(f"App already installed in workspace {workspace_id}")

        installation = InstallationRecord(
            workspace_id=workspace_id,
            account_id=account_id,
            user_id=user_id,
            manifest_version=self.manifest.compute_hash(),
        )

        # Install actions
        for action_manifest in self.manifest.actions:
            secret = secrets.token_urlsafe(32)

            # Create action via experimental API
            action = await exp_client.custom_actions.create(
                workspace_id=workspace_id,
                name=action_manifest.name,
                description=action_manifest.description,
                event_type=action_manifest.event_type,
                webhook_url=f"{self.manifest.base_url.rstrip('/')}",
                signing_secret=secret,
            )

            installation.actions.append(
                InstalledAction(
                    action_id=action.data.id,
                    event_type=action_manifest.event_type,
                    name=action_manifest.name,
                    description=action_manifest.description,
                    secret=secret,
                )
            )

        # Install webhooks (one webhook with all event types)
        for webhook_manifest in self.manifest.webhooks:
            secret = secrets.token_urlsafe(32)

            # Create webhook via standard API
            webhook = await client.webhooks.create(
                account_id=account_id,
                workspace_id=workspace_id,
                url=f"{self.manifest.base_url.rstrip('/')}",
                event_types=webhook_manifest.event_types,
                secret=secret,
            )

            installation.webhooks.append(
                InstalledWebhook(
                    webhook_id=webhook.data.id,
                    event_types=webhook_manifest.event_types,
                    name=webhook_manifest.description,
                    secret=secret,
                )
            )

        # Store installation record (encrypted)
        await self._store_installation(installation)

    async def uninstall(
        self,
        user_id: str,
        user_token: str,
        workspace_ids: list[str],
    ) -> InstallationResult:
        """Uninstall app from one or more workspaces.

        Args:
            user_id: Frame.io user ID performing the uninstall.
            user_token: OAuth access token for API calls.
            workspace_ids: List of workspace IDs to uninstall from.

        Returns:
            InstallationResult with success/failure per workspace.
        """
        result = InstallationResult(success=True, workspace_results={}, errors={})

        # Create clients for API calls
        client = Client(token=user_token)
        exp_client = AsyncFrameioExperimental(api_key=user_token)

        try:
            for workspace_id in workspace_ids:
                try:
                    await self._uninstall_workspace(
                        client=client,
                        exp_client=exp_client,
                        workspace_id=workspace_id,
                    )
                    result.workspace_results[workspace_id] = True
                except Exception as e:
                    result.success = False
                    result.workspace_results[workspace_id] = False
                    result.errors[workspace_id] = str(e)

            # Update user installation index
            await self._update_user_index(user_id, workspace_ids, add=False)

        finally:
            await client.close()
            # AsyncFrameioExperimental doesn't have a close method

        return result

    async def _uninstall_workspace(
        self,
        client: Client,
        exp_client: AsyncFrameioExperimental,
        workspace_id: str,
    ) -> None:
        """Uninstall app from a single workspace.

        Args:
            client: Frame.io API client.
            exp_client: Experimental API client.
            workspace_id: Workspace to uninstall from.
        """
        # Get installation record
        installation = await self.get_installation(workspace_id)
        if not installation:
            raise ValueError(f"App not installed in workspace {workspace_id}")

        # Delete all custom actions
        for action in installation.actions:
            try:
                await exp_client.custom_actions.delete(
                    workspace_id=workspace_id,
                    action_id=action.action_id,
                )
            except Exception as e:
                # Log but continue
                print(f"Failed to delete action {action.action_id}: {e}")

        # Delete all webhooks
        for webhook in installation.webhooks:
            try:
                await client.webhooks.delete(
                    account_id=installation.account_id,
                    webhook_id=webhook.webhook_id,
                )
            except Exception as e:
                # Log but continue
                print(f"Failed to delete webhook {webhook.webhook_id}: {e}")

        # Mark as uninstalled and store
        installation.status = "uninstalled"
        installation.updated_at = datetime.now()
        await self._store_installation(installation)

    async def get_installation(self, workspace_id: str) -> InstallationRecord | None:
        """Get installation record for a workspace.

        Args:
            workspace_id: Frame.io workspace ID.

        Returns:
            InstallationRecord if found, None otherwise.
        """
        key = self._make_installation_key(workspace_id)
        data = await self.storage.get(key)

        if data is None:
            return None

        # Decrypt and parse
        encrypted_json = self._unwrap_encrypted_json(data)
        decrypted_json = self.encryption._fernet.decrypt(encrypted_json.encode()).decode()
        return InstallationRecord.model_validate_json(decrypted_json)

    async def list_installations(self, user_id: str) -> list[InstallationRecord]:
        """List all installations for a user.

        Args:
            user_id: Frame.io user ID.

        Returns:
            List of InstallationRecord objects.
        """
        # Get user index
        index_key = self._make_index_key(user_id)
        index_data = await self.storage.get(index_key)

        if index_data is None:
            return []

        index = UserInstallationIndex.model_validate(index_data)

        # Fetch all installations
        installations: list[InstallationRecord] = []
        for workspace_id in index.workspace_ids:
            installation = await self.get_installation(workspace_id)
            if installation and installation.status == "active":
                installations.append(installation)

        return installations

    async def get_secret(self, workspace_id: str, event_type: str) -> str | None:
        """Get secret for a specific event type in a workspace.

        This is used during event verification to look up workspace-specific secrets.

        Args:
            workspace_id: Frame.io workspace ID.
            event_type: Event type (action or webhook).

        Returns:
            Secret string if found, None otherwise.
        """
        installation = await self.get_installation(workspace_id)
        if not installation:
            return None

        # Check actions first
        for action in installation.actions:
            if action.event_type == event_type:
                return action.secret

        # Check webhooks
        for webhook in installation.webhooks:
            if event_type in webhook.event_types:
                return webhook.secret

        return None

    async def _store_installation(self, installation: InstallationRecord) -> None:
        """Store installation record with encryption.

        Args:
            installation: InstallationRecord to store.
        """
        key = self._make_installation_key(installation.workspace_id)

        # Encrypt entire record
        json_data = installation.model_dump_json()
        encrypted = self.encryption._fernet.encrypt(json_data.encode())
        wrapped = self._wrap_encrypted_json(encrypted.decode())

        # Store with no TTL (permanent until explicitly deleted)
        await self.storage.put(key, wrapped)

    async def _update_user_index(
        self,
        user_id: str,
        workspace_ids: list[str],
        add: bool = True,
    ) -> None:
        """Update user installation index.

        Args:
            user_id: Frame.io user ID.
            workspace_ids: Workspace IDs to add or remove.
            add: True to add, False to remove.
        """
        key = self._make_index_key(user_id)
        data = await self.storage.get(key)

        if data is None:
            index = UserInstallationIndex(user_id=user_id)
        else:
            index = UserInstallationIndex.model_validate(data)

        # Update workspace list
        workspace_set = set(index.workspace_ids)
        if add:
            workspace_set.update(workspace_ids)
        else:
            workspace_set.difference_update(workspace_ids)

        index.workspace_ids = sorted(list(workspace_set))
        index.updated_at = datetime.now()

        # Store updated index
        await self.storage.put(key, index.model_dump())

    def _wrap_encrypted_json(self, encrypted_str: str) -> dict[str, str]:
        """Wrap encrypted JSON string for storage.

        Args:
            encrypted_str: Encrypted string.

        Returns:
            Dictionary for storage.
        """
        return {"encrypted_installation": encrypted_str}

    def _unwrap_encrypted_json(self, data: dict[str, str]) -> str:
        """Unwrap encrypted JSON from storage.

        Args:
            data: Dictionary from storage.

        Returns:
            Encrypted string.
        """
        return data["encrypted_installation"]
