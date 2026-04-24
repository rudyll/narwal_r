"""Button entities for Narwal vacuum — dock operations and maintenance."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Coroutine
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NarwalConfigEntry
from .coordinator import NarwalCoordinator
from .entity import NarwalEntity
from .narwal_client import NarwalClient


@dataclass(frozen=True, kw_only=True)
class NarwalButtonDescription(ButtonEntityDescription):
    """Describes a Narwal button entity."""

    press_fn: Callable[[NarwalClient], Coroutine[Any, Any, Any]]


BUTTON_DESCRIPTIONS: tuple[NarwalButtonDescription, ...] = (
    NarwalButtonDescription(
        key="locate",
        translation_key="locate",
        icon="mdi:map-marker",
        press_fn=lambda client: client.locate(),
    ),
    NarwalButtonDescription(
        key="wash_mop",
        translation_key="wash_mop",
        icon="mdi:water",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda client: client.wash_mop(),
    ),
    NarwalButtonDescription(
        key="dry_mop",
        translation_key="dry_mop",
        icon="mdi:hair-dryer",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda client: client.dry_mop(),
    ),
    NarwalButtonDescription(
        key="empty_dustbin",
        translation_key="empty_dustbin",
        icon="mdi:delete-empty",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda client: client.empty_dustbin(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Narwal button entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        NarwalButton(coordinator, description) for description in BUTTON_DESCRIPTIONS
    )


class NarwalButton(NarwalEntity, ButtonEntity):
    """A Narwal button entity."""

    entity_description: NarwalButtonDescription

    def __init__(
        self, coordinator: NarwalCoordinator, description: NarwalButtonDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        device_id = coordinator.config_entry.data["device_id"]
        self._attr_unique_id = f"{device_id}_{description.key}"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.entity_description.press_fn(self.coordinator.client)
