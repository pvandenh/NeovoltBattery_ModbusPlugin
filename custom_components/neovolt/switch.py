"""Switch platform for Neovolt Solar Inverter."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
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
    """Set up Neovolt switches."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    
    switches = [
        NeovoltForceChargeSwitch(coordinator, device_info, client, hass),
        NeovoltForceDischargeSwitch(coordinator, device_info, client, hass),
    ]
    
    async_add_entities(switches)


class NeovoltForceChargeSwitch(CoordinatorEntity, SwitchEntity):
    """Force charge switch."""

    def __init__(self, coordinator, device_info, client, hass):
        """Initialize the switch."""
        super().__init__(coordinator)
        self._client = client
        self._hass = hass
        self._attr_name = "Neovolt Inverter Force Charging"
        self._attr_unique_id = "neovolt_inverter_force_charging"
        self._attr_icon = "mdi:battery-charging"
        self._attr_device_info = device_info

    @property
    def is_on(self):
        """Return if switch is on."""
        data = self.coordinator.data
        return data.get("dispatch_start") == 1 and data.get("dispatch_power", 0) < 0

    async def async_turn_on(self, **kwargs):
        """Turn on force charging."""
        try:
            # Get charging power from number entity if available
            power_entity = self._hass.states.get("number.neovolt_inverter_force_charging_power")
            power = float(power_entity.state) if power_entity else 3.0
            power_watts = int(power * 1000)
            
            # Get duration from number entity if available
            duration_entity = self._hass.states.get("number.neovolt_inverter_force_charging_duration")
            duration = int(float(duration_entity.state)) if duration_entity else 120
            duration_seconds = duration * 60
            
            # Get SOC target from number entity if available
            soc_entity = self._hass.states.get("number.neovolt_inverter_charging_soc_target")
            soc_target = int(float(soc_entity.state)) if soc_entity else 100
            soc_value = int(soc_target / 0.392157)  # Convert percentage to raw value
            
            # Prepare dispatch registers
            # Register 0x0880: Start (0=stop, 1=start)
            # Register 0x0881-0x0882: Active power (32000 - watts for charging, 32000 + watts for discharging)
            # Register 0x0883-0x0884: Reactive power (always 32000 for no reactive power)
            # Register 0x0885: Mode (0=power control, 1=time control, 2=SOC control)
            # Register 0x0886: SOC target/cutoff
            # Register 0x0887-0x0888: Duration in seconds
            
            values = [
                1,                      # Dispatch start
                0,                      # Power high byte
                32000 - power_watts,    # Power low byte (negative for charging)
                0,                      # Reactive power high
                32000,                  # Reactive power low (no reactive power)
                2,                      # Mode: SOC control
                soc_value,              # SOC target
                0,                      # Time high byte
                duration_seconds,       # Time low byte (safety timeout)
            ]
            
            _LOGGER.info(f"Starting force charging: {power}kW, target SOC {soc_target}%, timeout {duration}min")
            
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, values
            )
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to enable force charging: {e}")

    async def async_turn_off(self, **kwargs):
        """Turn off force charging."""
        try:
            _LOGGER.info("Stopping force charging")
            values = [0, 0, 32000, 0, 32000, 0, 0, 0, 90]
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, values
            )
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to disable force charging: {e}")


class NeovoltForceDischargeSwitch(CoordinatorEntity, SwitchEntity):
    """Force discharge switch."""

    def __init__(self, coordinator, device_info, client, hass):
        """Initialize the switch."""
        super().__init__(coordinator)
        self._client = client
        self._hass = hass
        self._attr_name = "Neovolt Inverter Force Discharging"
        self._attr_unique_id = "neovolt_inverter_force_discharging"
        self._attr_icon = "mdi:battery-arrow-down"
        self._attr_device_info = device_info

    @property
    def is_on(self):
        """Return if switch is on."""
        data = self.coordinator.data
        return data.get("dispatch_start") == 1 and data.get("dispatch_power", 0) > 0

    async def async_turn_on(self, **kwargs):
        """Turn on force discharging."""
        try:
            # Get discharging power from number entity if available
            power_entity = self._hass.states.get("number.neovolt_inverter_force_discharging_power")
            power = float(power_entity.state) if power_entity else 3.0
            power_watts = int(power * 1000)
            
            # Get duration from number entity if available
            duration_entity = self._hass.states.get("number.neovolt_inverter_force_discharging_duration")
            duration = int(float(duration_entity.state)) if duration_entity else 120
            duration_seconds = duration * 60
            
            # Get SOC cutoff from number entity if available
            soc_entity = self._hass.states.get("number.neovolt_inverter_discharging_soc_cutoff")
            soc_cutoff = int(float(soc_entity.state)) if soc_entity else 20
            soc_value = int(soc_cutoff / 0.392157)  # Convert percentage to raw value
            
            values = [
                1,                      # Dispatch start
                0,                      # Power high byte
                32000 + power_watts,    # Power low byte (positive for discharging)
                0,                      # Reactive power high
                32000,                  # Reactive power low (no reactive power)
                2,                      # Mode: SOC control
                soc_value,              # SOC cutoff
                0,                      # Time high byte
                duration_seconds,       # Time low byte (safety timeout)
            ]
            
            _LOGGER.info(f"Starting force discharging: {power}kW, cutoff SOC {soc_cutoff}%, timeout {duration}min")
            
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, values
            )
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to enable force discharging: {e}")

    async def async_turn_off(self, **kwargs):
        """Turn off force discharging."""
        try:
            _LOGGER.info("Stopping force discharging")
            values = [0, 0, 32000, 0, 32000, 0, 0, 0, 90]
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, values
            )
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to disable force discharging: {e}")