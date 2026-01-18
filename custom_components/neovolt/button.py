"""Button platform for Neovolt Solar Inverter."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_ROLE_FOLLOWER, DISPATCH_RESET_VALUES, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neovolt buttons."""
    device_role = hass.data[DOMAIN][entry.entry_id]["device_role"]

    # Skip control entities for follower devices
    if device_role == DEVICE_ROLE_FOLLOWER:
        return

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    device_name = hass.data[DOMAIN][entry.entry_id]["device_name"]

    buttons = [
        NeovoltStopForceChargeDischargeButton(coordinator, device_info, device_name, client, hass),
    ]

    async_add_entities(buttons)


class NeovoltStopForceChargeDischargeButton(CoordinatorEntity, ButtonEntity):
    """Stop Force Charge/Discharge button - stops all force charge/discharge operations."""

    def __init__(self, coordinator, device_info, device_name, client, hass):
        """Initialize the button."""
        super().__init__(coordinator)
        self._client = client
        self._hass = hass
        self._attr_name = f"Neovolt {device_name} Stop Force Charge/Discharge"
        self._attr_unique_id = f"neovolt_{device_name}_stop_force_charge_discharge"
        self._attr_icon = "mdi:stop-circle"
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Return True if coordinator has valid cached data."""
        return self.coordinator.has_valid_data

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            _LOGGER.info("Stopping all force charge/discharge operations")
            
            # Stop dynamic export manager if running
            if hasattr(self.coordinator, 'dynamic_export_manager'):
                try:
                    await self.coordinator.dynamic_export_manager.stop()
                    _LOGGER.info("Stopped Dynamic Export manager")
                except Exception as e:
                    _LOGGER.debug(f"Dynamic Export manager not running or already stopped: {e}")
            
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, DISPATCH_RESET_VALUES
            )
            # Optimistic update - show stopped state immediately
            self.coordinator.set_optimistic_value("dispatch_start", 0)
            self.coordinator.set_optimistic_value("dispatch_power", 0)
            self.coordinator.set_optimistic_value("dispatch_mode", 0)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to stop force charge/discharge: {e}")