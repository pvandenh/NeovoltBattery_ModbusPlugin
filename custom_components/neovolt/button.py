"""Button platform for Neovolt Solar Inverter."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DISPATCH_RESET_VALUES, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neovolt buttons."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    
    buttons = [
        NeovoltDispatchResetButton(coordinator, device_info, client, hass),
        NeovoltStopChargingButton(coordinator, device_info, client, hass),
        NeovoltStopDischargingButton(coordinator, device_info, client, hass),
    ]
    
    async_add_entities(buttons)


class NeovoltDispatchResetButton(CoordinatorEntity, ButtonEntity):
    """Dispatch reset button - stops all force charge/discharge."""

    def __init__(self, coordinator, device_info, client, hass):
        """Initialize the button."""
        super().__init__(coordinator)
        self._client = client
        self._hass = hass
        self._attr_name = "Neovolt Inverter Dispatch Reset"
        self._attr_unique_id = "neovolt_inverter_dispatch_reset"
        self._attr_icon = "mdi:restart"
        self._attr_device_info = device_info

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            _LOGGER.info("Resetting dispatch (stopping all force charge/discharge)")
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, DISPATCH_RESET_VALUES
            )
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to reset dispatch: {e}")


class NeovoltStopChargingButton(CoordinatorEntity, ButtonEntity):
    """Stop charging button - quick way to stop force charging."""

    def __init__(self, coordinator, device_info, client, hass):
        """Initialize the button."""
        super().__init__(coordinator)
        self._client = client
        self._hass = hass
        self._attr_name = "Neovolt Inverter Stop Charging"
        self._attr_unique_id = "neovolt_inverter_stop_charging"
        self._attr_icon = "mdi:battery-charging-off"
        self._attr_device_info = device_info

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            _LOGGER.info("Stopping force charging")
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, DISPATCH_RESET_VALUES
            )
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to stop charging: {e}")


class NeovoltStopDischargingButton(CoordinatorEntity, ButtonEntity):
    """Stop discharging button - quick way to stop force discharging."""

    def __init__(self, coordinator, device_info, client, hass):
        """Initialize the button."""
        super().__init__(coordinator)
        self._client = client
        self._hass = hass
        self._attr_name = "Neovolt Inverter Stop Discharging"
        self._attr_unique_id = "neovolt_inverter_stop_discharging"
        self._attr_icon = "mdi:battery-off"
        self._attr_device_info = device_info

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            _LOGGER.info("Stopping force discharging")
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, DISPATCH_RESET_VALUES
            )
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to stop discharging: {e}")