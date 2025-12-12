"""The Neovolt integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_DEVICE_NAME, CONF_DEVICE_ROLE, DEVICE_ROLE_HOST, DOMAIN
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
    new_data = {**entry.data}
    if CONF_DEVICE_NAME not in entry.data:
        new_data[CONF_DEVICE_NAME] = "inverter"
        _LOGGER.info("Migrated existing entry to device_name='inverter'")

    # Migrate existing entries without device_role (default to host)
    if CONF_DEVICE_ROLE not in entry.data:
        new_data[CONF_DEVICE_ROLE] = DEVICE_ROLE_HOST
        _LOGGER.info("Migrated existing entry to device_role='host'")

    # Apply migrations if any
    if new_data != entry.data:
        hass.config_entries.async_update_entry(entry, data=new_data)

    device_name = entry.data.get(CONF_DEVICE_NAME, "inverter")
    device_role = entry.data.get(CONF_DEVICE_ROLE, DEVICE_ROLE_HOST)

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

    # Store coordinator, device info, client, device_name, and device_role
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "device_info": device_info,
        "client": coordinator.client,
        "device_name": device_name,
        "device_role": device_role,
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