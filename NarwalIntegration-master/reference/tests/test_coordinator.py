"""Tests for NarwalCoordinator resilience -- failure buffering and push reset.

Verifies the coordinator returns stale data on transient failures, raises
UpdateFailed after the threshold, and resets counters on success/push.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# Install HA stubs before any custom_components import
import tests.ha_stubs  # noqa: E402

tests.ha_stubs.install()

from custom_components.narwal.coordinator import NarwalCoordinator  # noqa: E402
from custom_components.narwal.narwal_client import NarwalConnectionError, NarwalState  # noqa: E402

UpdateFailed = sys.modules["homeassistant.helpers.update_coordinator"].UpdateFailed


class TestCoordinatorResilience:
    """Tests for NarwalCoordinator failure buffering and availability."""

    def _make_coordinator(self) -> NarwalCoordinator:
        """Create a NarwalCoordinator with mocked hass and entry."""
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.data = {
            "host": "10.0.0.100",
            "port": 9002,
            "device_id": "test_device",
            "product_key": "QoEsI5qYXO",
        }

        coordinator = NarwalCoordinator.__new__(NarwalCoordinator)
        # Initialize the attributes that __init__ sets, bypassing
        # DataUpdateCoordinator.__init__ which needs a real hass.
        coordinator.hass = mock_hass
        coordinator.config_entry = mock_entry
        coordinator.client = MagicMock()
        coordinator.client.state = NarwalState()
        coordinator._consecutive_failures = 0
        coordinator._max_failures = 5
        coordinator._fast_poll_remaining = 0
        coordinator._listen_task = None
        coordinator._map_fetch_pending = False
        coordinator._last_display_map_resub = 0.0
        coordinator._prev_working_status = MagicMock()
        coordinator.update_interval = None
        # Prevent background task warnings
        mock_entry.async_create_background_task = MagicMock()
        return coordinator

    async def test_stale_data_on_first_failure(self) -> None:
        """_async_update_data returns stale state on first poll failure."""
        coordinator = self._make_coordinator()
        type(coordinator.client).connected = PropertyMock(return_value=False)

        result = await coordinator._async_update_data()

        assert result is coordinator.client.state
        assert coordinator._consecutive_failures == 1

    async def test_stale_data_on_consecutive_failures_below_threshold(self) -> None:
        """_async_update_data returns stale state for failures 1-4."""
        coordinator = self._make_coordinator()
        type(coordinator.client).connected = PropertyMock(return_value=False)

        for i in range(4):
            result = await coordinator._async_update_data()
            assert result is coordinator.client.state
            assert coordinator._consecutive_failures == i + 1

    async def test_update_failed_after_max_failures(self) -> None:
        """_async_update_data raises UpdateFailed after 5 consecutive failures."""
        coordinator = self._make_coordinator()
        type(coordinator.client).connected = PropertyMock(return_value=False)

        # Burn through 4 failures (stale data returned)
        for _ in range(4):
            await coordinator._async_update_data()

        # 5th failure raises UpdateFailed
        with pytest.raises(UpdateFailed, match="5 consecutive polls"):
            await coordinator._async_update_data()

        assert coordinator._consecutive_failures == 5

    async def test_success_resets_failure_counter(self) -> None:
        """_async_update_data resets _consecutive_failures to 0 on success."""
        coordinator = self._make_coordinator()

        # Simulate 3 failures first
        type(coordinator.client).connected = PropertyMock(return_value=False)
        for _ in range(3):
            await coordinator._async_update_data()
        assert coordinator._consecutive_failures == 3

        # Now succeed
        type(coordinator.client).connected = PropertyMock(return_value=True)
        coordinator.client.get_status = AsyncMock()

        result = await coordinator._async_update_data()

        assert coordinator._consecutive_failures == 0
        assert result is coordinator.client.state

    async def test_push_update_resets_failure_counter(self) -> None:
        """_on_state_update resets _consecutive_failures to 0."""
        coordinator = self._make_coordinator()
        coordinator._consecutive_failures = 3

        # Mock methods called by _on_state_update
        coordinator.async_set_updated_data = MagicMock()
        coordinator._prev_working_status = MagicMock()

        state = NarwalState()
        coordinator._on_state_update(state)

        assert coordinator._consecutive_failures == 0

    async def test_poll_does_not_call_connect(self) -> None:
        """_async_update_data does NOT call client.connect() when disconnected."""
        coordinator = self._make_coordinator()
        type(coordinator.client).connected = PropertyMock(return_value=False)
        coordinator.client.connect = AsyncMock()

        # Run a few poll failures
        for _ in range(3):
            await coordinator._async_update_data()

        coordinator.client.connect.assert_not_awaited()

    async def test_connected_but_get_status_fails(self) -> None:
        """_async_update_data buffers failure when connected but get_status raises."""
        coordinator = self._make_coordinator()
        type(coordinator.client).connected = PropertyMock(return_value=True)
        coordinator.client.get_status = AsyncMock(
            side_effect=NarwalConnectionError("recv timeout")
        )

        result = await coordinator._async_update_data()

        assert result is coordinator.client.state
        assert coordinator._consecutive_failures == 1
