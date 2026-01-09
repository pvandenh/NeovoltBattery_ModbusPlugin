"""Switch platform for Neovolt Solar Inverter."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEVICE_ROLE_FOLLOWER,
    DISPATCH_MODE_POWER_WITH_SOC,
    DISPATCH_RESET_VALUES,
    DOMAIN,
    MAX_SOC_PERCENT,
    MAX_SOC_REGISTER,
    MIN_SOC_PERCENT,
    MIN_SOC_REGISTER,
    MODBUS_OFFSET,
    SOC_CONVERSION_FACTOR,
)

_LOGGER = logging.getLogger(__name__)


def safe_get_entity_float(hass: HomeAssistant, entity_id: str, default: float) -> float:
    """
    Safely retrieve a float value from a Home Assistant entity.

    Args:
        hass: Home Assistant instance
        entity_id: Entity ID to retrieve
        default: Default value if entity unavailable or invalid

    Returns:
        Float value from entity state, or default if unavailable/invalid
    """
    try:
        entity = hass.states.get(entity_id)
        if not entity:
            _LOGGER.debug(f"Entity {entity_id} not found, using default: {default}")
            return default

        state = entity.state
        if state in ("unknown", "unavailable", "None", None):
            _LOGGER.debug(f"Entity {entity_id} state is {state}, using default: {default}")
            return default

        value = float(state)
        return value

    except (ValueError, TypeError) as e:
        _LOGGER.warning(
            f"Failed to convert entity {entity_id} state to float: {e}. Using default: {default}"
        )
        return default
    except Exception as e:
        _LOGGER.error(
            f"Unexpected error retrieving entity {entity_id}: {e}. Using default: {default}"
        )
        return default


def soc_percent_to_register(soc_percent: float) -> int:
    """
    Convert SOC percentage (0-100%) to register value (0-255) with bounds checking.

    Args:
        soc_percent: State of charge as percentage (0-100)

    Returns:
        Register value (0-255)

    Raises:
        ValueError: If SOC percentage is out of valid range
    """
    if not MIN_SOC_PERCENT <= soc_percent <= MAX_SOC_PERCENT:
        raise ValueError(
            f"SOC percentage {soc_percent}% is out of valid range "
            f"({MIN_SOC_PERCENT}-{MAX_SOC_PERCENT}%)"
        )

    # Convert to register value
    register_value = int(soc_percent / SOC_CONVERSION_FACTOR)

    # Clamp to valid register range as safety measure
    register_value = max(MIN_SOC_REGISTER, min(MAX_SOC_REGISTER, register_value))

    return register_value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neovolt switches."""
    device_role = hass.data[DOMAIN][entry.entry_id]["device_role"]

    # Skip control entities for follower devices
    if device_role == DEVICE_ROLE_FOLLOWER:
        return

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    device_name = hass.data[DOMAIN][entry.entry_id]["device_name"]

    switches = [
        NeovoltForceChargeSwitch(coordinator, device_info, device_name, client, hass),
        NeovoltForceDischargeSwitch(coordinator, device_info, device_name, client, hass),
        NeovoltPreventSolarChargingSwitch(coordinator, device_info, device_name, client, hass),
    ]

    async_add_entities(switches)


class NeovoltForceChargeSwitch(CoordinatorEntity, SwitchEntity):
    """Force charge switch."""

    def __init__(self, coordinator, device_info, device_name, client, hass):
        """Initialize the switch."""
        super().__init__(coordinator)
        self._client = client
        self._hass = hass
        self._device_name = device_name
        self._attr_name = f"Neovolt {device_name} Force Charging"
        self._attr_unique_id = f"neovolt_{device_name}_force_charging"
        self._attr_icon = "mdi:battery-charging"
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Return True if coordinator has valid cached data."""
        return self.coordinator.has_valid_data

    @property
    def is_on(self):
        """Return if switch is on."""
        data = self.coordinator.data
        return data.get("dispatch_start") == 1 and data.get("dispatch_power", 0) < 0

    async def async_turn_on(self, **kwargs):
        """Turn on force charging."""
        try:
            # Get charging power from number entity (default: 3.0 kW)
            power = safe_get_entity_float(
                self._hass,
                f"number.neovolt_{self._device_name}_force_charging_power",
                3.0
            )
            power_watts = int(power * 1000)

            # Get duration from number entity (default: 120 minutes)
            duration = int(safe_get_entity_float(
                self._hass,
                f"number.neovolt_{self._device_name}_force_charging_duration",
                120.0
            ))
            duration_seconds = duration * 60

            # Get SOC target from number entity (default: 100%)
            soc_target = int(safe_get_entity_float(
                self._hass,
                f"number.neovolt_{self._device_name}_charging_soc_target",
                100.0
            ))
            soc_value = soc_percent_to_register(soc_target)

            # Prepare dispatch registers
            values = [
                1,                              # Dispatch start
                0,                              # Power high byte
                MODBUS_OFFSET - power_watts,    # Power low byte (negative for charging)
                0,                              # Reactive power high
                MODBUS_OFFSET,                  # Reactive power low (no reactive power)
                DISPATCH_MODE_POWER_WITH_SOC,   # Mode: SOC control
                soc_value,                      # SOC target
                0,                              # Time high byte
                duration_seconds,               # Time low byte (safety timeout)
            ]

            _LOGGER.info(f"Starting force charging: {power}kW, target SOC {soc_target}%, timeout {duration}min")

            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, values
            )
            # Optimistic update - show ON state immediately
            self.coordinator.set_optimistic_value("dispatch_start", 1)
            self.coordinator.set_optimistic_value("dispatch_power", -power_watts)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to enable force charging: {e}")

    async def async_turn_off(self, **kwargs):
        """Turn off force charging."""
        try:
            _LOGGER.info("Stopping force charging")
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, DISPATCH_RESET_VALUES
            )
            # Optimistic update - show OFF state immediately
            self.coordinator.set_optimistic_value("dispatch_start", 0)
            self.coordinator.set_optimistic_value("dispatch_power", 0)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to disable force charging: {e}")


class NeovoltForceDischargeSwitch(CoordinatorEntity, SwitchEntity):
    """Force discharge switch."""

    def __init__(self, coordinator, device_info, device_name, client, hass):
        """Initialize the switch."""
        super().__init__(coordinator)
        self._client = client
        self._hass = hass
        self._device_name = device_name
        self._attr_name = f"Neovolt {device_name} Force Discharging"
        self._attr_unique_id = f"neovolt_{device_name}_force_discharging"
        self._attr_icon = "mdi:battery-arrow-down"
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Return True if coordinator has valid cached data."""
        return self.coordinator.has_valid_data

    @property
    def is_on(self):
        """Return if switch is on."""
        data = self.coordinator.data
        return data.get("dispatch_start") == 1 and data.get("dispatch_power", 0) > 0

    async def async_turn_on(self, **kwargs):
        """Turn on force discharging."""
        try:
            # Get discharging power from number entity (default: 3.0 kW)
            power = safe_get_entity_float(
                self._hass,
                f"number.neovolt_{self._device_name}_force_discharging_power",
                3.0
            )
            power_watts = int(power * 1000)

            # Get duration from number entity (default: 120 minutes)
            duration = int(safe_get_entity_float(
                self._hass,
                f"number.neovolt_{self._device_name}_force_discharging_duration",
                120.0
            ))
            duration_seconds = duration * 60

            # Get SOC cutoff from number entity (default: 20%)
            soc_cutoff = int(safe_get_entity_float(
                self._hass,
                f"number.neovolt_{self._device_name}_discharging_soc_cutoff",
                20.0
            ))
            soc_value = soc_percent_to_register(soc_cutoff)

            values = [
                1,                              # Dispatch start
                0,                              # Power high byte
                MODBUS_OFFSET + power_watts,    # Power low byte (positive for discharging)
                0,                              # Reactive power high
                MODBUS_OFFSET,                  # Reactive power low (no reactive power)
                DISPATCH_MODE_POWER_WITH_SOC,   # Mode: SOC control
                soc_value,                      # SOC cutoff
                0,                              # Time high byte
                duration_seconds,               # Time low byte (safety timeout)
            ]

            _LOGGER.info(f"Starting force discharging: {power}kW, cutoff SOC {soc_cutoff}%, timeout {duration}min")

            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, values
            )
            # Optimistic update - show ON state immediately
            self.coordinator.set_optimistic_value("dispatch_start", 1)
            self.coordinator.set_optimistic_value("dispatch_power", power_watts)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to enable force discharging: {e}")

    async def async_turn_off(self, **kwargs):
        """Turn off force discharging."""
        try:
            _LOGGER.info("Stopping force discharging")
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, DISPATCH_RESET_VALUES
            )
            # Optimistic update - show OFF state immediately
            self.coordinator.set_optimistic_value("dispatch_start", 0)
            self.coordinator.set_optimistic_value("dispatch_power", 0)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to disable force discharging: {e}")


class NeovoltPreventSolarChargingSwitch(CoordinatorEntity, SwitchEntity):
    """Prevent solar charging switch - stops battery from charging from solar."""

    def __init__(self, coordinator, device_info, device_name, client, hass):
        """Initialize the switch."""
        super().__init__(coordinator)
        self._client = client
        self._hass = hass
        self._device_name = device_name
        self._attr_name = f"Neovolt {device_name} Prevent Solar Charging"
        self._attr_unique_id = f"neovolt_{device_name}_prevent_solar_charging"
        self._attr_icon = "mdi:battery-lock"
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Return True if coordinator has valid cached data."""
        return self.coordinator.has_valid_data

    @property
    def is_on(self):
        """Return if switch is on."""
        # Check if we're in prevent solar charging mode
        data = self.coordinator.data
        dispatch_start = data.get("dispatch_start", 0)
        dispatch_power = data.get("dispatch_power", 0)

        # We set prevent charging mode to exactly 50W discharge
        # Use exact match to avoid false positives from other discharge modes
        PREVENT_CHARGING_POWER = 50  # Must match value in async_turn_on
        return dispatch_start == 1 and dispatch_power == PREVENT_CHARGING_POWER

    async def async_turn_on(self, **kwargs):
        """Turn on prevent solar charging mode."""
        try:
            # Get duration from number entity (default: 480 minutes = 8 hours)
            duration = int(safe_get_entity_float(
                self._hass,
                f"number.neovolt_{self._device_name}_prevent_solar_charging_duration",
                480.0
            ))
            duration_seconds = min(duration * 60, 65535)  # Cap to 16-bit max (~18 hours)

            # Get current SOC to use as cutoff (prevent discharge below current level)
            current_soc = self.coordinator.data.get("battery_soc", 20)
            soc_cutoff = max(int(current_soc) - 2, 10)  # 2% buffer, minimum 10%
            soc_value = soc_percent_to_register(soc_cutoff)

            # Set a very small discharge power (50W) to prevent charging
            # This effectively tells the inverter to slightly discharge, preventing any charging
            # Hardware constraint: 50W is minimum reliable discharge power for this inverter
            prevent_charging_power = 50  # 50W minimal discharge

            values = [
                1,                                      # Dispatch start
                0,                                      # Power high byte
                MODBUS_OFFSET + prevent_charging_power, # Power low byte (tiny positive = prevent charging)
                0,                                      # Reactive power high
                MODBUS_OFFSET,                          # Reactive power low (no reactive power)
                DISPATCH_MODE_POWER_WITH_SOC,           # Mode: SOC control (stops at cutoff)
                soc_value,                              # SOC cutoff (current - 2%)
                0,                                      # Time high byte
                duration_seconds,                       # Time low byte (duration)
            ]

            _LOGGER.info(f"Enabling prevent solar charging mode for {duration} minutes (SOC cutoff: {soc_cutoff}%)")
            _LOGGER.debug(f"Current battery SOC: {current_soc}%, preventing charge with 50W discharge command")

            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, values
            )
            # Optimistic update - show ON state immediately
            self.coordinator.set_optimistic_value("dispatch_start", 1)
            self.coordinator.set_optimistic_value("dispatch_power", 50)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to enable prevent solar charging: {e}")

    async def async_turn_off(self, **kwargs):
        """Turn off prevent solar charging mode (return to normal operation)."""
        try:
            _LOGGER.info("Disabling prevent solar charging mode (returning to normal operation)")
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, DISPATCH_RESET_VALUES
            )
            # Optimistic update - show OFF state immediately
            self.coordinator.set_optimistic_value("dispatch_start", 0)
            self.coordinator.set_optimistic_value("dispatch_power", 0)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to disable prevent solar charging: {e}")