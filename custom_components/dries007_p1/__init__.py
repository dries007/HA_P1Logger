"""The P1 Logger integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import p1logger
from . import const

PLATFORMS: list[Platform] = [Platform.SENSOR]

type P1LoggerConfigEntry = ConfigEntry[p1logger.P1Logger]


async def async_setup_entry(hass: HomeAssistant, entry: P1LoggerConfigEntry) -> bool:
    """Set up P1 Logger from a config entry."""
    entry.runtime_data = p1logger.P1Logger(hass, entry.data[const.CFG_SERIAL_PORT])
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: P1LoggerConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
