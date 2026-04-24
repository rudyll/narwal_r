"""Tests for Narwal config flow -- covers HACS default listing requirements.

Mocks the homeassistant framework via ha_stubs so config_flow.py can be
imported and tested without a full HA installation.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Install HA stubs before any custom_components import
import tests.ha_stubs  # noqa: E402

tests.ha_stubs.install()

from custom_components.narwal.config_flow import NarwalConfigFlow  # noqa: E402
from custom_components.narwal.narwal_client import NarwalConnectionError  # noqa: E402

AbortFlow = sys.modules["homeassistant.data_entry_flow"].AbortFlow


class TestNarwalConfigFlow:
    """Tests for NarwalConfigFlow.async_step_user branching logic."""

    def _make_flow(self) -> NarwalConfigFlow:
        """Create a NarwalConfigFlow with stubbed base-class methods."""
        flow = NarwalConfigFlow.__new__(NarwalConfigFlow)
        flow.async_show_form = MagicMock(return_value={"type": "form"})
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        return flow

    async def test_show_form_when_no_input(self) -> None:
        """async_step_user with no input returns a form with step_id='user'."""
        flow = self._make_flow()
        await flow.async_step_user(user_input=None)

        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["step_id"] == "user"

    async def test_successful_setup_creates_entry(self) -> None:
        """async_step_user with valid input creates a config entry."""
        flow = self._make_flow()

        mock_client = AsyncMock()
        mock_client.topic_prefix = "/QoEsI5qYXO"
        mock_device_info = MagicMock()
        mock_device_info.device_id = "test_device_123"
        mock_client.get_device_info.return_value = mock_device_info

        with patch(
            "custom_components.narwal.config_flow.NarwalClient",
            return_value=mock_client,
        ):
            await flow.async_step_user(
                user_input={
                    "host": "10.0.0.100",
                    "port": 9002,
                    "model": "Narwal Flow",
                },
            )

        mock_client.connect.assert_awaited_once()
        mock_client.discover_device_id.assert_awaited_once()
        mock_client.get_device_info.assert_awaited_once()
        flow.async_set_unique_id.assert_awaited_once_with("test_device_123")
        flow._abort_if_unique_id_configured.assert_called_once()
        flow.async_create_entry.assert_called_once()
        entry_kwargs = flow.async_create_entry.call_args.kwargs
        assert entry_kwargs["data"]["host"] == "10.0.0.100"
        assert entry_kwargs["data"]["port"] == 9002
        assert entry_kwargs["data"]["device_id"] == "test_device_123"
        assert entry_kwargs["data"]["product_key"] == "QoEsI5qYXO"
        assert entry_kwargs["data"]["model"] == "Narwal Flow"
        mock_client.disconnect.assert_awaited_once()

    async def test_connection_error_shows_form_with_error(self) -> None:
        """async_step_user with connection failure returns form with cannot_connect."""
        flow = self._make_flow()

        mock_client = AsyncMock()
        mock_client.connect.side_effect = NarwalConnectionError("timeout")

        with patch(
            "custom_components.narwal.config_flow.NarwalClient",
            return_value=mock_client,
        ):
            await flow.async_step_user(
                user_input={
                    "host": "10.0.0.200",
                    "port": 9002,
                    "model": "Narwal Flow",
                },
            )

        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["errors"] == {"base": "cannot_connect"}
        mock_client.disconnect.assert_awaited_once()

    async def test_duplicate_device_aborts(self) -> None:
        """async_step_user with duplicate unique_id aborts with already_configured."""
        flow = self._make_flow()

        mock_client = AsyncMock()
        mock_client.topic_prefix = "/QoEsI5qYXO"
        mock_device_info = MagicMock()
        mock_device_info.device_id = "duplicate_device"
        mock_client.get_device_info.return_value = mock_device_info

        flow._abort_if_unique_id_configured.side_effect = AbortFlow(
            "already_configured"
        )

        with patch(
            "custom_components.narwal.config_flow.NarwalClient",
            return_value=mock_client,
        ):
            with pytest.raises(AbortFlow, match="already_configured"):
                await flow.async_step_user(
                    user_input={
                        "host": "10.0.0.100",
                        "port": 9002,
                        "model": "Narwal Flow",
                    },
                )

        flow.async_set_unique_id.assert_awaited_once_with("duplicate_device")
        mock_client.disconnect.assert_awaited_once()

    async def test_auto_detect_model_uses_resolved_key(self) -> None:
        """async_step_user with auto-detect uses the resolved product key."""
        flow = self._make_flow()

        mock_client = AsyncMock()
        mock_client.topic_prefix = "/DrzDKQ0MU8"
        mock_device_info = MagicMock()
        mock_device_info.device_id = "auto_device_456"
        mock_client.get_device_info.return_value = mock_device_info

        with patch(
            "custom_components.narwal.config_flow.NarwalClient",
            return_value=mock_client,
        ):
            await flow.async_step_user(
                user_input={
                    "host": "10.0.0.50",
                    "port": 9002,
                    "model": "Other / Auto-detect",
                },
            )

        flow.async_create_entry.assert_called_once()
        entry_kwargs = flow.async_create_entry.call_args.kwargs
        assert entry_kwargs["data"]["product_key"] == "DrzDKQ0MU8"
        assert "Narwal DrzDKQ0MU8" in entry_kwargs["title"]
