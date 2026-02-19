"""Pydantic models for parsing incoming Frame.io webhook and action events.

This module provides the data structures that your application's event handlers
will receive. When Frame.io sends a POST request to your endpoint, the `App`
will automatically parse the JSON payload into one of these Pydantic models.
This ensures that the data your handler receives is validated and fully typed,
allowing for robust and predictable code with excellent editor support.

The models are structured with a `_BaseEvent` to hold common fields, and two
specific subclasses (`WebhookEvent`, `ActionEvent`) to handle structural
differences in the payloads, while convenience properties like `account_id` and
`resource_id` provide a consistent access pattern in your code.
"""

from typing import Any, Literal

from pydantic import BaseModel, computed_field, model_validator


ResourceType = Literal["file", "folder", "version_stack"]
"""The possible types for a Frame.io resource."""


class Resource(BaseModel):
    """Represents the primary resource that an event pertains to.

    Attributes:
        id: The unique identifier (UUID) of the resource.
        type: The type of the resource (e.g., 'file', 'folder').
    """

    id: str
    type: ResourceType


class Project(BaseModel):
    """Represents the project context in which an event occurred.

    Attributes:
        id: The unique identifier (UUID) of the project.
    """

    id: str


class User(BaseModel):
    """Represents the user who initiated the event.

    Attributes:
        id: The unique identifier (UUID) of the user.
    """

    id: str


class Workspace(BaseModel):
    """Represents the workspace (formerly Team) in which an event occurred.

    Attributes:
        id: The unique identifier (UUID) of the workspace.
    """

    id: str


class Account(BaseModel):
    """Represents the account context, used in standard webhook payloads.

    Attributes:
        id: The unique identifier (UUID) of the account.
    """

    id: str


class _BaseEvent(BaseModel):
    """A base model containing fields common to all event types.

    This class is not intended to be instantiated directly but provides a
    consistent foundation for both `WebhookEvent` and `ActionEvent`.

    Attributes:
        project: The project context for the event.
        type: The specific event type string (e.g., 'file.ready').
        user: The user who triggered the event.
        workspace: The workspace where the event occurred.
        timestamp: The Unix timestamp (in seconds) when the event was generated
            by Frame.io. This value is extracted from the X-Frameio-Request-Timestamp
            header.
    """

    project: Project
    type: str
    user: User
    workspace: Workspace
    timestamp: int

    @computed_field
    @property
    def user_id(self) -> str:
        """A convenience property to directly access the user's ID.

        Returns:
            The unique identifier (UUID) of the user.
        """
        return self.user.id

    @computed_field
    @property
    def project_id(self) -> str:
        """A convenience property to directly access the project's ID.

        Returns:
            The unique identifier (UUID) of the project.
        """
        return self.project.id

    @computed_field
    @property
    def workspace_id(self) -> str:
        """A convenience property to directly access the workspace's ID.

        Returns:
            The unique identifier (UUID) of the workspace.
        """
        return self.workspace.id


class WebhookEvent(_BaseEvent):
    """A standard webhook event payload from Frame.io.

    This model is used for handlers registered with `@app.on_webhook`.

    Attributes:
        account: The account context object for the event.
        resource: The resource (e.g., file, folder) that the event is about.
    """

    account: Account
    resource: Resource

    @computed_field
    @property
    def account_id(self) -> str:
        """A convenience property to directly access the account's ID.

        Returns:
            The unique identifier (UUID) of the account.
        """
        return self.account.id

    @computed_field
    @property
    def resource_id(self) -> str:
        """A convenience property to directly access the resource's ID.

        Returns:
            The unique identifier (UUID) of the event's primary resource.
        """
        return self.resource.id


class ActionEvent(_BaseEvent):
    """A custom action event payload, including user-submitted form data.

    This model is used for handlers registered with `@app.on_action`. It differs
    from `WebhookEvent` by having a top-level `account_id` and including specific
    fields related to the action's lifecycle.

    Attributes:
        account_id: The ID of the account where the event originated.
        action_id: The ID of the custom action that was triggered.
        interaction_id: A unique ID for a sequence of interactions, used to
            correlate steps in a multi-step custom action (e.g., a form
            submission).
        resources: A list of resources targeted by this action. Multi-asset
            custom actions can target up to 100 assets in a single request.
        data: A dictionary containing submitted form data. This will be `None`
            for the initial trigger of an action before a form is displayed.
            When a form is submitted, the keys of this dictionary will match
            the `name` of each form field.
    """

    account_id: str
    action_id: str
    interaction_id: str
    resources: list[Resource]
    data: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_resource_to_resources(cls, data: Any) -> Any:
        """Normalize legacy singular ``resource`` payload to ``resources`` list."""
        if isinstance(data, dict) and "resource" in data and "resources" not in data:
            data = {**data, "resources": [data.pop("resource")]}
        return data

    @computed_field
    @property
    def resource_ids(self) -> list[str]:
        """A convenience property to directly access all resource IDs.

        Returns:
            A list of unique identifiers (UUIDs) of the targeted resources.
        """
        return [r.id for r in self.resources]

    @computed_field
    @property
    def account(self) -> Account:
        """A convenience property to access the account as an Account object.

        This provides consistency with WebhookEvent, allowing access to the
        account ID via `event.account.id` for both event types.

        Returns:
            An Account object containing the account ID.
        """
        return Account(id=self.account_id)


AnyEvent = ActionEvent | WebhookEvent
"""Union type representing any event that can be processed by the app."""
