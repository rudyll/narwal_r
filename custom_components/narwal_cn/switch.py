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
        key="child_lock",
        translation_key="child_lock",
        icon="mdi:lock",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda state: state.child_lock,
        turn_on_fn=lambda client: client.set_child_lock(True),
        turn_off_fn=lambda client: client.set_child_lock(False),
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
