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

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            _LOGGER.info("Stopping all force charge/discharge operations")
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, DISPATCH_RESET_VALUES
            )
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to stop force charge/discharge: {e}")