"""Base entity for Narwal vacuum integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import NarwalCoordinator


class NarwalEntity(CoordinatorEntity[NarwalCoordinator]):
    """Base class for Narwal entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NarwalCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info, including live firmware version."""
        device_id = self.coordinator.config_entry.data["device_id"]
        return DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            sw_version=self.coordinator.client.state.firmware_version or None,
            name=self.coordinator.config_entry.title,
        )

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self.coordinator.last_update_success
