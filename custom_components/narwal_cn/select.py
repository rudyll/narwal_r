"""Select entities for Narwal vacuum — mop humidity and cleaning mode."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from collections.abc import Callable, Coroutine
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from homeassistant.exceptions import HomeAssistantError

from . import NarwalConfigEntry
from .coordinator import NarwalCoordinator
from .entity import NarwalEntity
from .narwal_client import NarwalClient, NarwalCommandError, NarwalState, MopHumidity, FanLevel

_LOGGER = logging.getLogger(__name__)

# ── Mop humidity ────────────────────────────────────────────────────────────
MOP_HUMIDITY_OPTIONS = ["dry", "normal", "wet"]
_MOP_HUMIDITY_TO_ENUM = {
    "dry": MopHumidity.DRY,
    "normal": MopHumidity.NORMAL,
    "wet": MopHumidity.WET,
}
_MOP_HUMIDITY_FROM_ENUM = {v: k for k, v in _MOP_HUMIDITY_TO_ENUM.items()}

# ── Cleaning mode ────────────────────────────────────────────────────────────
# NOTE: topic and payload values are pending confirmation via sniff_all_topics.py.
# Run: python3 tools/sniff_all_topics.py --subscribe --out dump.json
#      then switch modes in the App to capture the topic+payload.
CLEANING_MODE_OPTIONS = ["sweep", "mop", "sweep_and_mop", "sweep_then_mop"]
_CLEANING_MODE_VALUES = {
    "sweep": 1,
    "mop": 2,
    "sweep_and_mop": 3,
    "sweep_then_mop": 4,
}
_CLEANING_MODE_FROM_VALUE = {v: k for k, v in _CLEANING_MODE_VALUES.items()}

# ── Suction level ─────────────────────────────────────────────────────────────
SUCTION_LEVEL_OPTIONS = ["quiet", "standard", "strong", "max"]
_SUCTION_TO_FAN_LEVEL = {
    "quiet": FanLevel.QUIET,     # 0
    "standard": FanLevel.NORMAL, # 1
    "strong": FanLevel.STRONG,   # 2
    "max": FanLevel.MAX,         # 3
}
_SUCTION_FROM_FAN_LEVEL = {int(v): k for k, v in _SUCTION_TO_FAN_LEVEL.items()}


@dataclass(frozen=True, kw_only=True)
class NarwalSelectDescription(SelectEntityDescription):
    """Describes a Narwal select entity."""

    options_list: list[str]
    current_fn: Callable[[NarwalState], str | None]
    select_fn: Callable[[NarwalClient, str], Coroutine[Any, Any, Any]]


SELECT_DESCRIPTIONS: tuple[NarwalSelectDescription, ...] = (
    NarwalSelectDescription(
        key="mop_humidity",
        translation_key="mop_humidity",
        icon="mdi:water-percent",
        entity_category=EntityCategory.CONFIG,
        options_list=MOP_HUMIDITY_OPTIONS,
        current_fn=lambda state: _MOP_HUMIDITY_FROM_ENUM.get(state.mop_humidity),
        select_fn=lambda client, opt: client.set_mop_humidity(
            _MOP_HUMIDITY_TO_ENUM[opt]
        ),
    ),
    NarwalSelectDescription(
        key="cleaning_mode",
        translation_key="cleaning_mode",
        icon="mdi:broom",
        entity_category=EntityCategory.CONFIG,
        options_list=CLEANING_MODE_OPTIONS,
        current_fn=lambda state: _CLEANING_MODE_FROM_VALUE.get(state.cleaning_mode),
        select_fn=lambda client, opt: client.set_cleaning_mode(
            _CLEANING_MODE_VALUES[opt]
        ),
    ),
    NarwalSelectDescription(
        key="suction_level",
        translation_key="suction_level",
        icon="mdi:fan",
        entity_category=EntityCategory.CONFIG,
        options_list=SUCTION_LEVEL_OPTIONS,
        current_fn=lambda state: _SUCTION_FROM_FAN_LEVEL.get(state.fan_level),
        select_fn=lambda client, opt: client.set_fan_speed(
            _SUCTION_TO_FAN_LEVEL[opt]
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Narwal select entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        NarwalSelect(coordinator, description) for description in SELECT_DESCRIPTIONS
    )


class NarwalSelect(NarwalEntity, SelectEntity):
    """A Narwal select entity."""

    entity_description: NarwalSelectDescription

    def __init__(
        self, coordinator: NarwalCoordinator, description: NarwalSelectDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        device_id = coordinator.config_entry.data["device_id"]
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_options = description.options_list

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option."""
        state = self.coordinator.data
        if state is None:
            return None
        return self.entity_description.current_fn(state)

    async def async_select_option(self, option: str) -> None:
        """Handle option selection."""
        try:
            await self.entity_description.select_fn(self.coordinator.client, option)
        except NarwalCommandError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()
