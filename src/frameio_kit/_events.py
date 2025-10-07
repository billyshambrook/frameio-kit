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

from pydantic import BaseModel, computed_field


class Resource(BaseModel):
    """Represents the primary resource that an event pertains to.

    Attributes:
        id: The unique identifier (UUID) of the resource.
        type: The type of the resource (e.g., 'file', 'folder').
    """

    id: str
    type: Literal["file", "folder", "version_stack"]


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
        resource: The resource (e.g., file, folder) that the event is about.
        type: The specific event type string (e.g., 'file.ready').
        user: The user who triggered the event.
        workspace: The workspace where the event occurred.
    """

    project: Project
    resource: Resource
    type: str
    user: User
    workspace: Workspace

    @computed_field
    @property
    def resource_id(self) -> str:
        """A convenience property to directly access the resource's ID.

        Returns:
            The unique identifier (UUID) of the event's primary resource.
        """
        return self.resource.id

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
    """

    account: Account

    @computed_field
    @property
    def account_id(self) -> str:
        """A convenience property to directly access the account's ID.

        Returns:
            The unique identifier (UUID) of the account.
        """
        return self.account.id


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
        data: A dictionary containing submitted form data. This will be `None`
            for the initial trigger of an action before a form is displayed.
            When a form is submitted, the keys of this dictionary will match
            the `name` of each form field.
    """

    account_id: str
    action_id: str
    interaction_id: str
    data: dict[str, Any] | None = None


AnyEvent = ActionEvent | WebhookEvent
"""Union type representing any event that can be processed by the app."""
