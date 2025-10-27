"""Installation manager for creating and managing app installations.

This module handles the creation, update, and deletion of custom actions
and webhooks via the Frame.io APIs, along with managing installation records.
"""

import logging
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

logger = logging.getLogger(__name__)


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
        manifest: AppManifest | None = None,
    ) -> None:
        """Initialize installation manager.

        Args:
            app: The App instance.
            storage: Storage backend for installation records.
            encryption: TokenEncryption for securing secrets.
            manifest: The app manifest describing what to install. If None,
                will be generated lazily from registered handlers.
        """
        self.app = app
        self.storage = storage
        self.encryption = encryption
        self._manifest = manifest

    @property
    def manifest(self) -> AppManifest:
        """Get the app manifest, generating it lazily if needed.

        This ensures the manifest is generated after all decorators have been
        executed and handlers have been registered.

        Returns:
            The app manifest with all registered actions and webhooks.
        """
        if self._manifest is None:
            from ._manifest import AppManifest

            # Generate manifest from currently registered handlers
            self._manifest = AppManifest.from_app(
                app=self.app,
                app_name=self.app._installation_config.app_name,
                app_description=self.app._installation_config.app_description,
                base_url=self.app._oauth_config.base_url,
                icon_url=self.app._installation_config.app_icon_url,
                include_actions=self.app._installation_config.include_actions,
                include_webhooks=self.app._installation_config.include_webhooks,
            )
        return self._manifest

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
        force_update: bool = False,
    ) -> InstallationResult:
        """Install or update app in one or more workspaces.

        Args:
            user_id: Frame.io user ID performing the installation.
            user_token: OAuth access token for API calls.
            workspace_ids: List of workspace IDs to install to.
            force_update: If True, reinstall even if already installed.

        Returns:
            InstallationResult with success/failure per workspace.
        """
        result = InstallationResult(success=True, workspace_results={}, errors={})

        # Create clients for API calls
        client = Client(token=user_token)
        exp_client = AsyncFrameioExperimental(token=user_token, api_version="experimental")

        try:
            for workspace_id in workspace_ids:
                try:
                    await self._install_workspace(
                        client=client,
                        exp_client=exp_client,
                        user_id=user_id,
                        workspace_id=workspace_id,
                        force_update=force_update,
                    )
                    result.workspace_results[workspace_id] = True
                except Exception as e:
                    logger.error(
                        "Installation error for workspace %s: %s",
                        workspace_id,
                        str(e),
                        exc_info=True,
                    )
                    result.success = False
                    result.workspace_results[workspace_id] = False
                    result.errors[workspace_id] = str(e)

            # Update user installation index for successful installations
            successful_workspaces = [ws_id for ws_id, success in result.workspace_results.items() if success]
            if successful_workspaces:
                await self._update_user_index(user_id, successful_workspaces, add=True)

        finally:
            await client.close()
            # AsyncFrameioExperimental doesn't have a close method

        return result

    async def _install_workspace(
        self,
        client: Client,
        exp_client: AsyncFrameioExperimental,
        user_id: str,
        workspace_id: str,
        force_update: bool = False,
    ) -> None:
        """Install or update app in a single workspace.

        Args:
            client: Frame.io API client.
            exp_client: Experimental API client for custom actions.
            user_id: User performing installation.
            workspace_id: Workspace to install to.
            force_update: If True, reinstall even if already installed and up to date.
        """
        logger.info("Installing app to workspace %s", workspace_id)

        # Get account_id by listing all accounts and finding the workspace
        account_id = None
        accounts = await client.accounts.index()
        for account in accounts.data:
            workspaces = await client.workspaces.index(account_id=account.id)
            for ws in workspaces.data:
                if ws.id == workspace_id:
                    account_id = account.id
                    break
            if account_id:
                break

        if not account_id:
            raise ValueError(f"Could not find account for workspace {workspace_id}")

        # Check if already installed
        existing = await self.get_installation(workspace_id)
        current_version = self.manifest.compute_hash()

        if existing and existing.status == "active":
            # Already installed - check if update needed
            if existing.manifest_version == current_version and not force_update:
                logger.info("App already up to date in workspace %s", workspace_id)
                return

            # Update needed - uninstall old version first
            logger.info("Updating installation in workspace %s", workspace_id)
            await self._uninstall_workspace(client, exp_client, workspace_id)

        installation = InstallationRecord(
            workspace_id=workspace_id,
            account_id=account_id,
            user_id=user_id,
            manifest_version=current_version,
        )

        # Install actions
        logger.info("Installing %d custom actions", len(self.manifest.actions))
        for action_manifest in self.manifest.actions:
            try:
                # Create action via experimental API
                from frameio_experimental.custom_actions.types import ActionCreateParamsData

                action = await exp_client.custom_actions.actions_create(
                    account_id=account_id,
                    workspace_id=workspace_id,
                    data=ActionCreateParamsData(
                        name=action_manifest.name,
                        description=action_manifest.description,
                        event=action_manifest.event_type,
                        url=self.manifest.base_url.rstrip("/"),
                    ),
                )

                # Frame.io generates the secret server-side
                action_secret = getattr(action.data, "signing_secret", None) or getattr(action.data, "secret", None) or ""

                if not action_secret:
                    logger.warning("No secret returned for action %s", action_manifest.event_type)

                installation.actions.append(
                    InstalledAction(
                        action_id=action.data.id,
                        event_type=action_manifest.event_type,
                        name=action_manifest.name,
                        description=action_manifest.description,
                        secret=action_secret,
                    )
                )
                logger.debug("Created action %s (ID: %s)", action_manifest.name, action.data.id)
            except Exception as e:
                logger.warning(
                    "Failed to create action %s: %s (Custom actions may not be enabled for this account)",
                    action_manifest.name,
                    str(e),
                )
                # Continue with webhook installation even if actions fail

        # Install webhooks (one webhook with all event types)
        logger.info("Installing %d webhooks", len(self.manifest.webhooks))
        for webhook_manifest in self.manifest.webhooks:
            # Create webhook via standard API
            from frameio.webhooks.types import WebhookCreateParamsData

            webhook = await client.webhooks.create(
                account_id=account_id,
                workspace_id=workspace_id,
                data=WebhookCreateParamsData(
                    name=webhook_manifest.description,
                    url=self.manifest.base_url.rstrip("/"),
                    events=webhook_manifest.event_types,
                ),
            )

            # Frame.io generates the secret server-side
            webhook_secret = getattr(webhook.data, "secret", None) or getattr(webhook.data, "signing_secret", None) or ""

            if not webhook_secret:
                logger.warning("No secret returned for webhook")

            installation.webhooks.append(
                InstalledWebhook(
                    webhook_id=webhook.data.id,
                    event_types=webhook_manifest.event_types,
                    name=webhook_manifest.description,
                    secret=webhook_secret,
                )
            )
            logger.debug("Created webhook (ID: %s)", webhook.data.id)

        # Store installation record (encrypted)
        await self._store_installation(installation)
        logger.info("Successfully installed app to workspace %s", workspace_id)

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
        exp_client = AsyncFrameioExperimental(token=user_token, api_version="experimental")

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

        Tracks all deletion failures and only removes the installation record
        if all resources were successfully deleted. If any deletions fail,
        updates the installation status to "error" for manual cleanup.

        Args:
            client: Frame.io API client.
            exp_client: Experimental API client.
            workspace_id: Workspace to uninstall from.

        Raises:
            ValueError: If app is not installed in the workspace.
            RuntimeError: If resource deletion failures occurred.
        """
        # Get installation record
        installation = await self.get_installation(workspace_id)
        if not installation or installation.status == "uninstalled":
            raise ValueError(f"App not installed in workspace {workspace_id}")

        logger.info("Uninstalling app from workspace %s", workspace_id)

        # Track all deletion failures
        failed_deletions: list[tuple[str, str, str]] = []

        # Delete all custom actions
        for action in installation.actions:
            try:
                await exp_client.custom_actions.actions_delete(
                    account_id=installation.account_id,
                    action_id=action.action_id,
                )
                logger.debug("Deleted action %s", action.action_id)
            except Exception as e:
                # Track failure for reporting
                error_msg = str(e)
                failed_deletions.append(("action", action.action_id, error_msg))
                logger.warning("Failed to delete action %s: %s", action.action_id, error_msg)

        # Delete all webhooks
        for webhook in installation.webhooks:
            try:
                await client.webhooks.delete(
                    account_id=installation.account_id,
                    webhook_id=webhook.webhook_id,
                )
                logger.debug("Deleted webhook %s", webhook.webhook_id)
            except Exception as e:
                # Track failure for reporting
                error_msg = str(e)
                failed_deletions.append(("webhook", webhook.webhook_id, error_msg))
                logger.warning("Failed to delete webhook %s: %s", webhook.webhook_id, error_msg)

        # Handle deletion results
        if failed_deletions:
            # Some resources couldn't be deleted - update status to error
            installation.status = "error"
            installation.updated_at = datetime.now()
            await self._store_installation(installation)

            # Provide detailed error message
            failure_summary = "; ".join(
                f"{res_type} {res_id}: {error}" for res_type, res_id, error in failed_deletions
            )
            logger.error(
                "Failed to delete %d resources from workspace %s: %s",
                len(failed_deletions),
                workspace_id,
                failure_summary,
            )
            raise RuntimeError(
                f"Failed to delete {len(failed_deletions)} resources. "
                f"Installation marked as error. Manual cleanup may be required."
            )

        # All resources deleted successfully - remove installation record
        key = self._make_installation_key(workspace_id)
        await self.storage.delete(key)
        logger.info("Successfully uninstalled app from workspace %s", workspace_id)

    async def get_installation(self, workspace_id: str) -> InstallationRecord | None:
        """Get installation record for a workspace.

        Args:
            workspace_id: Frame.io workspace ID.

        Returns:
            InstallationRecord if found, None otherwise.
        """
        key = self._make_installation_key(workspace_id)
        encrypted_data = await self.storage.get(key)

        if encrypted_data is None:
            return None

        # Decrypt and parse
        decrypted_json = self.encryption.decrypt_string(encrypted_data)
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
        encrypted = self.encryption.encrypt_string(json_data)

        # Store with no TTL (permanent until explicitly deleted)
        await self.storage.put(key, encrypted)

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

        # Store updated index (use mode='json' to serialize datetime properly)
        await self.storage.put(key, index.model_dump(mode="json"))
