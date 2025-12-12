"""Select platform for Neovolt Solar Inverter."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neovolt selects."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    device_name = hass.data[DOMAIN][entry.entry_id]["device_name"]

    selects = [
        NeovoltTimePeriodControlSelect(coordinator, device_info, device_name, client, hass),
    ]

    async_add_entities(selects)


class NeovoltTimePeriodControlSelect(CoordinatorEntity, SelectEntity):
    """Time period control select."""

    _attr_options = [
        "Disable",
        "Enable Charge Time Period Control",
        "Enable Discharge Time Period Control",
        "Enable Time Period Control",
    ]

    def __init__(self, coordinator, device_info, device_name, client, hass):
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._client = client
        self._hass = hass
        self._attr_name = f"Neovolt {device_name} Time Period Control"
        self._attr_unique_id = f"neovolt_{device_name}_time_period_control"
        self._attr_icon = "mdi:clock-time-four-outline"
        self._attr_device_info = device_info

    @property
    def current_option(self):
        """Return the current option."""
        value = self.coordinator.data.get("time_period_control_flag", 0)
        if value < len(self._attr_options):
            return self._attr_options[value]
        return self._attr_options[0]

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        try:
            # Validate option before attempting to use it
            if option not in self._attr_options:
                _LOGGER.error(
                    f"Invalid option '{option}' for time period control. "
                    f"Valid options: {self._attr_options}"
                )
                return

            value = self._attr_options.index(option)
            _LOGGER.info(f"Setting time period control to: {option} (value: {value})")
            await self._hass.async_add_executor_job(
                self._client.write_register, 0x084F, value
            )
            await self.coordinator.async_request_refresh()
        except ValueError as e:
            # This should not happen due to validation above, but handle defensively
            _LOGGER.error(f"Option '{option}' not found in valid options: {e}")
        except Exception as e:
            _LOGGER.error(f"Failed to set time period control to '{option}': {e}")