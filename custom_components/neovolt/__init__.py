"""The Neovolt integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_DEVICE_NAME, DOMAIN
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

    # Migrate existing entries without device_name (keep "inverter" for backward compatibility)
    if CONF_DEVICE_NAME not in entry.data:
        new_data = {**entry.data, CONF_DEVICE_NAME: "inverter"}
        hass.config_entries.async_update_entry(entry, data=new_data)
        _LOGGER.info(f"Migrated existing entry to device_name='inverter'")

    device_name = entry.data.get(CONF_DEVICE_NAME, "inverter")

    coordinator = NeovoltDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    # Create device info with device name
    device_info = DeviceInfo(
        identifiers={(DOMAIN, f"{entry.data['host']}_{entry.data['slave_id']}")},
        name=f"Neovolt {device_name}",
        manufacturer="Bytewatt Technology Co., Ltd",
        model="Neovolt Hybrid Inverter",
        sw_version=coordinator.data.get("ems_version"),
        configuration_url=f"http://{entry.data['host']}",
    )

    # Initialize domain data if not exists
    hass.data.setdefault(DOMAIN, {})

    # Store coordinator, device info, client, and device_name
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "device_info": device_info,
        "client": coordinator.client,
        "device_name": device_name,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Setup options update listener
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Close Modbus connection before cleanup
        client = hass.data[DOMAIN][entry.entry_id]["client"]
        await hass.async_add_executor_job(client.close)
        _LOGGER.debug("Closed Modbus connection for Neovolt integration")

        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)