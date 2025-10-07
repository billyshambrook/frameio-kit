"""Pydantic models for generating UI responses for Frame.io Custom Actions.

This module provides classes that, when returned from a custom action handler,
are automatically serialized into the JSON format expected by the Frame.io UI.
This allows you to easily display messages or prompt users for more information
with multi-field forms, without having to manually construct the JSON payloads.
"""

from typing import Literal

from pydantic import BaseModel, Field


class _UIResponse(BaseModel):
    """The base model for all UI-generating responses.

    Attributes:
        title: The text displayed as the main heading in the UI modal.
        description: The paragraph of text displayed below the title. Defaults to an empty string.
    """

    title: str
    description: str


class Message(_UIResponse):
    """A simple message modal to display information to the user.

    This is typically used as the final step in a custom action to confirm that
    an operation was successful or to provide information.

    Example:

    ```python
    from frameio_kit import Message

    return Message(title="Success", description="The action was successful.")
    ```
    """


class _BaseField(BaseModel):
    """The base model for all form fields, containing common attributes.

    Attributes:
        label: The user-visible text label displayed above the form field.
        name: The machine-readable key used to identify the field's value when
            the form is submitted. This key will appear in the `data` dictionary
            of the subsequent `ActionEvent`.
    """

    label: str
    name: str


class TextField(_BaseField):
    """A single-line text input field.

    Example:

    ```python
    from frameio_kit import Form, TextField

    return Form(
        title="Comment",
        fields=[TextField(label="Comment", name="comment", value="Enter your feedback...")]
    )
    ```

    Attributes:
        type: The field type, fixed to "text".
        value: An optional default value to pre-populate the field.
    """

    type: Literal["text"] = "text"
    value: str | None = None


class TextareaField(_BaseField):
    """A multi-line text input area, suitable for longer descriptions.

    Example:

    ```python
    from frameio_kit import Form, TextareaField

    return Form(
        title="Comment",
        fields=[TextareaField(label="Comment", name="comment", value="Enter your feedback...")]
    )
    ```

    Attributes:
        type: The field type, fixed to "textarea".
        value: An optional default value to pre-populate the field.
    """

    type: Literal["textarea"] = "textarea"
    value: str | None = None


class SelectOption(_BaseField):
    """Represents a single choice within a `SelectField`.

    Attributes:
        name: The user-visible text for the option in the dropdown list.
        value: The actual value that will be sent back in the `data` payload
            if this option is selected.
    """

    name: str
    value: str


class SelectField(_BaseField):
    """A dropdown menu allowing the user to select one from a list of options.

    Example:

    ```python
    from frameio_kit import Form, SelectField, SelectOption

    PLATFORMS = [
        SelectOption(name="Twitter", value="twitter"),
        SelectOption(name="Instagram", value="instagram"),
    ]

    return Form(
        title="Choose Platform",
        fields=[SelectField(label="Platform", name="platform", options=PLATFORMS)]
    )
    ```

    Attributes:
        type: The field type, fixed to "select".
        options: A list of `SelectOption` objects defining the choices.
        value: An optional default value to pre-select an option. This must
            match the `value` of one of the items in the `options` list.
    """

    type: Literal["select"] = "select"
    options: list[SelectOption]
    value: str | None = None


class CheckboxField(_BaseField):
    """A checkbox input.

    Example:

    ```python
    from frameio_kit import Form, CheckboxField

    return Form(
        title="Confirm Action",
        fields=[CheckboxField(label="Overwrite existing file?", name="overwrite", value=False)]
    )
    ```

    Attributes:
        type: The field type, fixed to "checkbox".
        value: An optional default state for the checkbox (`True` for checked).
    """

    type: Literal["checkbox"] = "checkbox"
    value: bool | None = None


class LinkField(_BaseField):
    """A non-editable field that displays a URL with a "Copy" button.

    This is useful for presenting a user with a link to an external resource
    that was generated as part of the action.

    Example:

    ```python
    from frameio_kit import Form, LinkField

    return Form(
        title="External Link",
        fields=[LinkField(label="External Link", name="external_link", value="https://www.example.com")]
    )
    ```

    Attributes:
        type: The field type, fixed to "link".
        value: The URL to be displayed.
    """

    type: Literal["link"] = "link"
    value: str | None = None


# A Pydantic-compatible union of all possible field types.
FormField = TextField | TextareaField | SelectField | CheckboxField | LinkField


class Form(_UIResponse):
    """A modal with a form to collect input from the user.

    When returned from a handler, this model renders a form in the Frame.io UI.
    Upon submission, Frame.io sends another `ActionEvent` to your endpoint, this
    time populating the `data` attribute with the user's input.

    Attributes:
        fields: A list of one or more form field objects (e.g., `TextField`,
            `SelectField`) to be displayed in the form.
    """

    fields: list[FormField] = Field(..., min_length=1)


AnyResponse = Message | Form | None
"""Union type representing any response that can be returned from handlers."""
