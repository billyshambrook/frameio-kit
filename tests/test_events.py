"""Tests for event models to ensure proper structure and computed properties."""

import pytest

from frameio_kit import ActionEvent, WebhookEvent


@pytest.fixture
def webhook_event_data():
    """Sample data for a WebhookEvent."""
    return {
        "type": "file.ready",
        "account": {"id": "acc_123"},
        "project": {"id": "proj_123"},
        "resource": {"id": "file_123", "type": "file"},
        "user": {"id": "user_123"},
        "workspace": {"id": "ws_123"},
        "timestamp": 1234567890,
    }


@pytest.fixture
def action_event_data():
    """Sample data for an ActionEvent."""
    return {
        "type": "transcribe.file",
        "account_id": "acc_123",
        "action_id": "act_123",
        "interaction_id": "int_123",
        "project": {"id": "proj_123"},
        "resource": {"id": "file_123", "type": "file"},
        "user": {"id": "user_123"},
        "workspace": {"id": "ws_123"},
        "data": {"language": "en-US"},
        "timestamp": 1234567890,
    }


def test_webhook_event_has_account_property(webhook_event_data):
    """Tests that WebhookEvent has an account property with id."""
    event = WebhookEvent(**webhook_event_data)
    assert hasattr(event, "account")
    assert event.account.id == "acc_123"


def test_webhook_event_has_account_id_property(webhook_event_data):
    """Tests that WebhookEvent has a computed account_id property."""
    event = WebhookEvent(**webhook_event_data)
    assert event.account_id == "acc_123"


def test_action_event_has_account_id_field(action_event_data):
    """Tests that ActionEvent has an account_id string field."""
    event = ActionEvent(**action_event_data)
    assert event.account_id == "acc_123"


def test_action_event_has_account_property(action_event_data):
    """Tests that ActionEvent has a computed account property for consistency."""
    event = ActionEvent(**action_event_data)
    assert hasattr(event, "account")
    assert event.account.id == "acc_123"


def test_both_events_support_account_dot_id_access(webhook_event_data, action_event_data):
    """Tests that both event types support event.account.id access pattern."""
    webhook_event = WebhookEvent(**webhook_event_data)
    action_event = ActionEvent(**action_event_data)

    # Both events should allow accessing account ID via event.account.id
    assert webhook_event.account.id == "acc_123"
    assert action_event.account.id == "acc_123"


def test_action_event_convenience_properties(action_event_data):
    """Tests that ActionEvent inherits all convenience properties from _BaseEvent."""
    event = ActionEvent(**action_event_data)

    # Test all convenience properties
    assert event.resource_id == "file_123"
    assert event.user_id == "user_123"
    assert event.project_id == "proj_123"
    assert event.workspace_id == "ws_123"


def test_webhook_event_convenience_properties(webhook_event_data):
    """Tests that WebhookEvent has all convenience properties."""
    event = WebhookEvent(**webhook_event_data)

    # Test all convenience properties
    assert event.resource_id == "file_123"
    assert event.user_id == "user_123"
    assert event.project_id == "proj_123"
    assert event.workspace_id == "ws_123"
    assert event.account_id == "acc_123"
