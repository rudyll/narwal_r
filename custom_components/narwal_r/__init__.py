"""Narwal Flow Robot Vacuum integration for Home Assistant."""

from __future__ import annotations

import logging
from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_MODEL, CONF_PRODUCT_KEY, PLATFORMS
from .coordinator import NarwalCoordinator
from .narwal_client import NarwalConnectionError

_LOGGER = logging.getLogger(__name__)

NarwalConfigEntry: TypeAlias = ConfigEntry[NarwalCoordinator]


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entries to version 2 (add product_key)."""
    if config_entry.version < 2:
        _LOGGER.info(
            "Migrating Narwal config entry from version %d to 2",
            config_entry.version,
        )
        new_data = {**config_entry.data}
        if CONF_PRODUCT_KEY not in new_data:
            new_data[CONF_PRODUCT_KEY] = "QoEsI5qYXO"
        if CONF_MODEL not in new_data:
            new_data[CONF_MODEL] = "Narwal Flow"
        hass.config_entries.async_update_entry(
            config_entry, data=new_data, version=2,
        )
        _LOGGER.info("Migration complete: product_key=%s", new_data[CONF_PRODUCT_KEY])
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NarwalConfigEntry) -> bool:
    """Set up Narwal from a config entry."""
    coordinator = NarwalCoordinator(hass, entry)
    try:
        await coordinator.async_setup()
    except NarwalConnectionError as err:
        raise ConfigEntryNotReady(
            f"Cannot connect to Narwal vacuum at {entry.data['host']}: {err}"
        ) from err

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: NarwalConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        await entry.runtime_data.async_shutdown()

    return unload_ok
