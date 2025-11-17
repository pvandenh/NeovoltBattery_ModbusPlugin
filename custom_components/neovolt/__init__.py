"""The Neovolt integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .coordinator import NeovoltDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR, 
    Platform.SWITCH, 
    Platform.NUMBER, 
    Platform.SELECT, 
    Platform.BUTTON
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Neovolt from a config entry."""
    _LOGGER.debug(f"Setting up Neovolt integration with config: {entry.data}")
    
    coordinator = NeovoltDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    # Create device info
    device_info = DeviceInfo(
        identifiers={(DOMAIN, f"{entry.data['host']}_{entry.data['slave_id']}")},
        name="Neovolt Inverter",
        manufacturer="Bytewatt Technology Co., Ltd",
        model="BW-INV-SPB5k",
        sw_version=coordinator.data.get("ems_version"),
        configuration_url=f"http://{entry.data['host']}",
    )

    # Initialize domain data if not exists
    hass.data.setdefault(DOMAIN, {})
    
    # Store both coordinator and device info
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "device_info": device_info,
        "client": coordinator.client,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok