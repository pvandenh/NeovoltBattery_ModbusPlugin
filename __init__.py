"""The Neovolt integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    CONF_DEVICE_NAME,
    CONF_DEVICE_ROLE,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    DEVICE_ROLE_HOST,
    DOMAIN,
    CONF_MIN_POLL_INTERVAL,
    CONF_MAX_POLL_INTERVAL,
    CONF_CONSECUTIVE_FAILURE_THRESHOLD,
    CONF_STALENESS_THRESHOLD,
    DEFAULT_MIN_POLL_INTERVAL,
    DEFAULT_MAX_POLL_INTERVAL,
    DEFAULT_CONSECUTIVE_FAILURES,
    DEFAULT_STALENESS_THRESHOLD,
    DEFAULT_MAX_CHARGE_POWER,
    DEFAULT_MAX_DISCHARGE_POWER,
    STORAGE_LAST_RESET_DATE,
    STORAGE_MIDNIGHT_BASELINE,
    STORAGE_LAST_KNOWN_TOTAL,
    STORAGE_DAILY_PRESERVED,
)
from .coordinator import NeovoltDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
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

    # Migrate existing entries without polling configuration
    if CONF_MIN_POLL_INTERVAL not in entry.data:
        new_data[CONF_MIN_POLL_INTERVAL] = DEFAULT_MIN_POLL_INTERVAL
        new_data[CONF_MAX_POLL_INTERVAL] = DEFAULT_MAX_POLL_INTERVAL
        new_data[CONF_CONSECUTIVE_FAILURE_THRESHOLD] = DEFAULT_CONSECUTIVE_FAILURES
        new_data[CONF_STALENESS_THRESHOLD] = DEFAULT_STALENESS_THRESHOLD
        _LOGGER.info("Migrated existing entry with default polling configuration")

    # Migrate existing entries without power configuration
    if CONF_MAX_CHARGE_POWER not in entry.data:
        new_data[CONF_MAX_CHARGE_POWER] = DEFAULT_MAX_CHARGE_POWER
        new_data[CONF_MAX_DISCHARGE_POWER] = DEFAULT_MAX_DISCHARGE_POWER
        _LOGGER.info("Migrated existing entry with default power configuration")

    # Apply migrations if any
    if new_data != entry.data:
        hass.config_entries.async_update_entry(entry, data=new_data)

    # Read from new_data to ensure we have migrated values
    device_name = new_data.get(CONF_DEVICE_NAME, "inverter")
    device_role = new_data.get(CONF_DEVICE_ROLE, DEVICE_ROLE_HOST)

    coordinator = NeovoltDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    # Create device info with device name
    device_info = DeviceInfo(
        identifiers={(DOMAIN, f"{entry.data['host']}_{entry.data['slave_id']}")},
        name=f"Neovolt {device_name}",
        manufacturer="Bytewatt Technology Co., Ltd",
        model="Neovolt Hybrid Inverter",
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
        # Close Modbus connection before cleanup (with safety check)
        if entry.entry_id in hass.data.get(DOMAIN, {}):
            # Stop dynamic export manager if running
            coordinator = hass.data[DOMAIN][entry.entry_id].get("coordinator")
            if coordinator and hasattr(coordinator, 'dynamic_export_manager'):
                try:
                    await coordinator.dynamic_export_manager.stop()
                    _LOGGER.info("Stopped Dynamic Export manager during unload")
                except Exception as e:
                    _LOGGER.debug(f"Error stopping Dynamic Export manager (ignored): {e}")
            
            # Close Modbus connection
            client = hass.data[DOMAIN][entry.entry_id].get("client")
            if client:
                await hass.async_add_executor_job(client.close)
                _LOGGER.debug("Closed Modbus connection for Neovolt integration")
            hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update - only reload for configuration changes, not runtime data."""
    # Runtime data keys that should NOT trigger a reload
    # These are updated by the coordinator during normal operation
    RUNTIME_KEYS = {
        STORAGE_LAST_RESET_DATE,
        STORAGE_MIDNIGHT_BASELINE,
        STORAGE_LAST_KNOWN_TOTAL,
        STORAGE_DAILY_PRESERVED,
    }
    
    # Get current options
    options = entry.options or {}
    
    # If we have options, check if only runtime keys were updated
    if options:
        # Get all keys that are NOT runtime keys (i.e., actual config keys)
        config_keys = set(options.keys()) - RUNTIME_KEYS
        
        # If no config keys exist (only runtime keys), skip reload
        if not config_keys:
            _LOGGER.debug(
                "Persistent data updated (runtime keys only), skipping integration reload"
            )
            return
    
    # Configuration keys were changed - reload integration
    _LOGGER.info("Configuration changed, reloading Neovolt integration")
    await hass.config_entries.async_reload(entry.entry_id)