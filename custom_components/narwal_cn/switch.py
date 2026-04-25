"""Switch entities for Narwal vacuum — carpet detection, AI features, child lock."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from collections.abc import Callable, Coroutine
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from homeassistant.exceptions import HomeAssistantError

from . import NarwalConfigEntry
from .coordinator import NarwalCoordinator
from .entity import NarwalEntity
from .narwal_client import NarwalClient, NarwalCommandError, NarwalState

_LOGGER = logging.getLogger(__name__)

# NOTE: All topics in this file are pending confirmation via sniff_all_topics.py.
# Run the sniffer while toggling each feature in the App to capture the exact
# topic and payload format.  Update narwal_client/const.py and client.py
# accordingly once confirmed.


@dataclass(frozen=True, kw_only=True)
class NarwalSwitchDescription(SwitchEntityDescription):
    """Describes a Narwal switch entity."""

    is_on_fn: Callable[[NarwalState], bool | None]
    turn_on_fn: Callable[[NarwalClient], Coroutine[Any, Any, Any]]
    turn_off_fn: Callable[[NarwalClient], Coroutine[Any, Any, Any]]


SWITCH_DESCRIPTIONS: tuple[NarwalSwitchDescription, ...] = (
    NarwalSwitchDescription(
        key="carpet_detection",
        translation_key="carpet_detection",
        icon="mdi:rug",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda state: state.carpet_detection,
        turn_on_fn=lambda client: client.set_carpet_detection(True),
        turn_off_fn=lambda client: client.set_carpet_detection(False),
    ),
    NarwalSwitchDescription(
        key="carpet_priority",
        translation_key="carpet_priority",
        icon="mdi:rug",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda state: state.carpet_priority,
        turn_on_fn=lambda client: client.set_carpet_priority(True),
        turn_off_fn=lambda client: client.set_carpet_priority(False),
    ),
    NarwalSwitchDescription(
        key="carpet_deep_clean",
        translation_key="carpet_deep_clean",
        icon="mdi:rug",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda state: state.carpet_deep_clean,
        turn_on_fn=lambda client: client.set_carpet_deep_clean(True),
        turn_off_fn=lambda client: client.set_carpet_deep_clean(False),
    ),
    NarwalSwitchDescription(
        key="deep_corner_clean",
        translation_key="deep_corner_clean",
        icon="mdi:broom",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda state: state.deep_corner_clean,
        turn_on_fn=lambda client: client.set_deep_corner_clean(True),
        turn_off_fn=lambda client: client.set_deep_corner_clean(False),
    ),
    NarwalSwitchDescription(
        key="ai_dirt_detection",
        translation_key="ai_dirt_detection",
        icon="mdi:robot-vacuum",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda state: state.ai_dirt_detection,
        turn_on_fn=lambda client: client.set_ai_dirt_detection(True),
        turn_off_fn=lambda client: client.set_ai_dirt_detection(False),
    ),
    NarwalSwitchDescription(
        key="ai_defecation_detection",
        translation_key="ai_defecation_detection",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda state: state.ai_defecation_detection,
        turn_on_fn=lambda client: client.set_ai_defecation_detection(True),
        turn_off_fn=lambda client: client.set_ai_defecation_detection(False),
    ),
    NarwalSwitchDescription(
        key="pet_dirt_detection",
        translation_key="pet_dirt_detection",
        icon="mdi:paw",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda state: state.pet_dirt_detection,
        turn_on_fn=lambda client: client.set_pet_dirt_detection(True),
        turn_off_fn=lambda client: client.set_pet_dirt_detection(False),
    ),
    NarwalSwitchDescription(
        key="child_lock",
        translation_key="child_lock",
        icon="mdi:lock",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda state: state.child_lock,
        turn_on_fn=lambda client: client.set_child_lock(True),
        turn_off_fn=lambda client: client.set_child_lock(False),
    ),
    NarwalSwitchDescription(
        key="dnd_mode",
        translation_key="dnd_mode",
        icon="mdi:bell-sleep",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda state: state.dnd_mode,
        turn_on_fn=lambda client: client.set_dnd_mode(True),
        turn_off_fn=lambda client: client.set_dnd_mode(False),
    ),
    NarwalSwitchDescription(
        key="altitude_mode",
        translation_key="altitude_mode",
        icon="mdi:mountain",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda state: state.altitude_mode,
        turn_on_fn=lambda client: client.set_altitude_mode(True),
        turn_off_fn=lambda client: client.set_altitude_mode(False),
    ),
    NarwalSwitchDescription(
        key="auto_power_off",
        translation_key="auto_power_off",
        icon="mdi:power-sleep",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda state: state.auto_power_off,
        turn_on_fn=lambda client: client.set_auto_power_off(True),
        turn_off_fn=lambda client: client.set_auto_power_off(False),
    ),
    NarwalSwitchDescription(
        key="hot_water_wash",
        translation_key="hot_water_wash",
        icon="mdi:water-thermometer",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda state: state.hot_water_wash,
        turn_on_fn=lambda client: client.set_hot_water_wash(True),
        turn_off_fn=lambda client: client.set_hot_water_wash(False),
    ),
    NarwalSwitchDescription(
        key="antibacterial_mode",
        translation_key="antibacterial_mode",
        icon="mdi:shield-bug",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda state: state.antibacterial_mode,
        turn_on_fn=lambda client: client.set_antibacterial_mode(True),
        turn_off_fn=lambda client: client.set_antibacterial_mode(False),
    ),
    NarwalSwitchDescription(
        key="auto_dust",
        translation_key="auto_dust",
        icon="mdi:vacuum",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda state: state.auto_dust,
        turn_on_fn=lambda client: client.set_auto_dust(True),
        turn_off_fn=lambda client: client.set_auto_dust(False),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Narwal switch entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        NarwalSwitch(coordinator, description) for description in SWITCH_DESCRIPTIONS
    )


class NarwalSwitch(NarwalEntity, SwitchEntity):
    """A Narwal switch entity."""

    entity_description: NarwalSwitchDescription

    def __init__(
        self, coordinator: NarwalCoordinator, description: NarwalSwitchDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        device_id = coordinator.config_entry.data["device_id"]
        self._attr_unique_id = f"{device_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return True if the switch is on."""
        state = self.coordinator.data
        if state is None:
            return None
        return self.entity_description.is_on_fn(state)

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            await self.entity_description.turn_on_fn(self.coordinator.client)
        except NarwalCommandError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self.entity_description.turn_off_fn(self.coordinator.client)
        except NarwalCommandError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()
