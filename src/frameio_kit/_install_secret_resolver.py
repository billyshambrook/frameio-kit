"""Secret resolver that looks up signing secrets from installation records.

When the installation system is configured, this resolver is automatically
set as the app-level secret resolver. It looks up the signing secret for
each incoming event by finding the matching installation record in Storage.
"""

import logging

from ._events import ActionEvent, WebhookEvent
from ._exceptions import InstallationNotFoundError
from ._install_manager import InstallationManager

logger = logging.getLogger(__name__)


class InstallationSecretResolver:
    """Resolves signing secrets from installation records in Storage.

    Implements the ``SecretResolverProtocol`` to provide automatic secret
    resolution for both webhook and action events based on the workspace's
    installation record.

    This resolver is auto-wired when ``install`` is configured on the App.
    """

    def __init__(self, manager: InstallationManager) -> None:
        self._manager = manager

    async def get_webhook_secret(self, event: WebhookEvent) -> str:
        """Resolve the signing secret for a webhook event.

        Looks up the installation for the event's account and workspace,
        then returns the webhook's signing secret.

        Args:
            event: The incoming webhook event.

        Returns:
            The signing secret for signature verification.

        Raises:
            InstallationNotFoundError: If no installation exists for the workspace.
        """
        installation = await self._manager.get_installation(event.account_id, event.workspace_id)
        if installation is None or installation.webhook is None:
            raise InstallationNotFoundError(
                f"No installation found for account {event.account_id}, workspace {event.workspace_id}"
            )
        return installation.webhook.secret

    async def get_action_secret(self, event: ActionEvent) -> str:
        """Resolve the signing secret for an action event.

        Looks up the installation for the event's account and workspace,
        finds the matching action record by event type, and returns its
        signing secret.

        Args:
            event: The incoming action event.

        Returns:
            The signing secret for signature verification.

        Raises:
            InstallationNotFoundError: If no installation or matching action exists.
        """
        installation = await self._manager.get_installation(event.account_id, event.workspace_id)
        if installation is None:
            raise InstallationNotFoundError(
                f"No installation found for account {event.account_id}, workspace {event.workspace_id}"
            )

        for action in installation.actions:
            if action.event_type == event.type:
                return action.secret

        raise InstallationNotFoundError(
            f"No action record found for event type '{event.type}' in workspace {event.workspace_id}"
        )
