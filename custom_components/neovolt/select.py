"""Select platform for Neovolt Solar Inverter."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
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
    MIN_SOC_PERCENT,
    MIN_SOC_REGISTER,
    MODBUS_OFFSET,
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
    Convert SOC percentage (0-100%) to register value (0-250) with bounds checking.

    Uses the formula: register_value = soc_percent * 2.5
    (0% -> 0, 40% -> 100, 100% -> 250)

    Args:
        soc_percent: State of charge as percentage (0-100)

    Returns:
        Register value (0-250)

    Raises:
        ValueError: If SOC percentage is out of valid range
    """
    if not MIN_SOC_PERCENT <= soc_percent <= MAX_SOC_PERCENT:
        raise ValueError(
            f"SOC percentage {soc_percent}% is out of valid range "
            f"({MIN_SOC_PERCENT}-{MAX_SOC_PERCENT}%)"
        )

    # Convert to register value using * 2.5 formula (0-100% -> 0-250)
    register_value = int(soc_percent * 2.5)

    # Clamp to valid register range as safety measure (max 250, not 255)
    register_value = max(MIN_SOC_REGISTER, min(250, register_value))

    return register_value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neovolt selects."""
    device_role = hass.data[DOMAIN][entry.entry_id]["device_role"]

    # Skip control entities for follower devices
    if device_role == DEVICE_ROLE_FOLLOWER:
        return

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    device_name = hass.data[DOMAIN][entry.entry_id]["device_name"]

    selects = [
        NeovoltTimePeriodControlSelect(coordinator, device_info, device_name, client, hass),
        NeovoltDispatchModeSelect(coordinator, device_info, device_name, client, hass),
        NeovoltPVSwitchSelect(coordinator, device_info, device_name, client, hass),
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
    def available(self) -> bool:
        """Return True if coordinator has valid cached data."""
        return self.coordinator.has_valid_data

    @property
    def current_option(self):
        """Return the current option."""
        value = self.coordinator.data.get("time_period_control_flag", 0)
        # Bounds check: ensure value is valid index into options
        if isinstance(value, int) and 0 <= value < len(self._attr_options):
            return self._attr_options[value]
        # Invalid value - log warning and return default
        if value != 0:
            _LOGGER.warning(f"Unexpected time_period_control_flag value: {value}, using default")
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
            # Optimistic update - show expected value immediately
            self.coordinator.set_optimistic_value("time_period_control_flag", value)
            await self.coordinator.async_request_refresh()
        except ValueError as e:
            # This should not happen due to validation above, but handle defensively
            _LOGGER.error(f"Option '{option}' not found in valid options: {e}")
        except Exception as e:
            _LOGGER.error(f"Failed to set time period control to '{option}': {e}")


class NeovoltDispatchModeSelect(CoordinatorEntity, SelectEntity):
    """Battery dispatch mode control - single source of truth for dispatch state."""

    _attr_options = [
        "Normal",
        "Force Charge",
        "Force Discharge",
        "No Battery Charge",
    ]

    def __init__(self, coordinator, device_info, device_name, client, hass):
        """Initialize the dispatch mode select entity."""
        super().__init__(coordinator)
        self._client = client
        self._hass = hass
        self._device_name = device_name
        self._attr_name = f"Neovolt {device_name} Dispatch Mode"
        self._attr_unique_id = f"neovolt_{device_name}_dispatch_mode"
        self._attr_icon = "mdi:battery-sync"
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Return True if coordinator has valid cached data."""
        return self.coordinator.has_valid_data

    @property
    def current_option(self):
        """Detect mode from hardware state."""
        data = self.coordinator.data
        dispatch_start = data.get("dispatch_start", 0)
        dispatch_power = data.get("dispatch_power", 0)
        dispatch_mode = data.get("dispatch_mode", 0)

        if dispatch_start != 1:
            return "Normal"

        # Check modes by mode number
        if dispatch_mode == 19:
            return "No Battery Charge"
        elif dispatch_mode == 2:
            # Mode 2: State of Charge control - detect by power direction
            # Negative = charge (32000 - watts), Positive = discharge (32000 + watts)
            if dispatch_power < 0:
                return "Force Charge"
            elif dispatch_power > 0:
                return "Force Discharge"

        return "Normal"

    async def async_select_option(self, option: str) -> None:
        """Change the dispatch mode."""
        try:
            if option == "Normal":
                await self._stop_dispatch()
            elif option == "Force Charge":
                await self._start_force_charge()
            elif option == "Force Discharge":
                await self._start_force_discharge()
            elif option == "No Battery Charge":
                await self._start_no_battery_charge()
            else:
                _LOGGER.error(f"Unknown dispatch mode option: {option}")
        except Exception as e:
            _LOGGER.error(f"Failed to set dispatch mode to '{option}': {e}")

    async def _stop_dispatch(self):
        """Stop all dispatch - return to automatic operation."""
        _LOGGER.info("Stopping dispatch - returning to normal operation")
        await self._hass.async_add_executor_job(
            self._client.write_registers, 0x0880, DISPATCH_RESET_VALUES
        )
        self.coordinator.set_optimistic_value("dispatch_start", 0)
        self.coordinator.set_optimistic_value("dispatch_power", 0)
        self.coordinator.set_optimistic_value("dispatch_mode", 0)
        await self.coordinator.async_request_refresh()

    async def _start_force_charge(self):
        """Start force charging with parameters from number entities."""
        power = safe_get_entity_float(
            self._hass,
            f"number.neovolt_{self._device_name}_dispatch_power",
            3.0
        )
        duration = int(safe_get_entity_float(
            self._hass,
            f"number.neovolt_{self._device_name}_dispatch_duration",
            120.0
        ))
        soc_target = int(safe_get_entity_float(
            self._hass,
            f"number.neovolt_{self._device_name}_dispatch_charge_soc",
            100.0
        ))

        power_watts = int(power * 1000)
        soc_value = soc_percent_to_register(soc_target)

        values = [
            1,                              # Para1: Dispatch start
            0,                              # Para2 high byte
            MODBUS_OFFSET - power_watts,    # Para2 low: CHARGE = 32000 - watts
            0,                              # Para3 high byte
            0,                              # Para3 low: Reactive power = 0
            DISPATCH_MODE_POWER_WITH_SOC,   # Para4: Mode 2 (SOC control)
            soc_value,                      # Para5: SOC target
            0,                              # Para6 high byte
            duration * 60,                  # Para6 low: Time (seconds)
            255,                            # Para7: Energy routing (default)
            0,                              # Para8: PV switch (auto)
        ]

        _LOGGER.info(
            f"Starting force charging: {power}kW, target SOC {soc_target}%, timeout {duration}min"
        )

        await self._hass.async_add_executor_job(
            self._client.write_registers, 0x0880, values
        )
        self.coordinator.set_optimistic_value("dispatch_start", 1)
        self.coordinator.set_optimistic_value("dispatch_power", -power_watts)  # Negative = charge
        self.coordinator.set_optimistic_value("dispatch_mode", 2)
        await self.coordinator.async_request_refresh()

    async def _start_force_discharge(self):
        """Start force discharging with parameters from number entities."""
        power = safe_get_entity_float(
            self._hass,
            f"number.neovolt_{self._device_name}_dispatch_power",
            3.0
        )
        duration = int(safe_get_entity_float(
            self._hass,
            f"number.neovolt_{self._device_name}_dispatch_duration",
            120.0
        ))
        soc_cutoff = int(safe_get_entity_float(
            self._hass,
            f"number.neovolt_{self._device_name}_dispatch_discharge_soc",
            10.0
        ))

        power_watts = int(power * 1000)
        soc_value = soc_percent_to_register(soc_cutoff)

        values = [
            1,                              # Para1: Dispatch start
            0,                              # Para2 high byte
            MODBUS_OFFSET + power_watts,    # Para2 low: DISCHARGE = 32000 + watts
            0,                              # Para3 high byte
            0,                              # Para3 low: Reactive power = 0
            DISPATCH_MODE_POWER_WITH_SOC,   # Para4: Mode 2 (SOC control)
            soc_value,                      # Para5: SOC cutoff
            0,                              # Para6 high byte
            duration * 60,                  # Para6 low: Time (seconds)
            255,                            # Para7: Energy routing (default)
            0,                              # Para8: PV switch (auto)
        ]

        _LOGGER.info(
            f"Starting force discharging: {power}kW, cutoff SOC {soc_cutoff}%, timeout {duration}min"
        )

        await self._hass.async_add_executor_job(
            self._client.write_registers, 0x0880, values
        )
        self.coordinator.set_optimistic_value("dispatch_start", 1)
        self.coordinator.set_optimistic_value("dispatch_power", power_watts)  # Positive = discharge
        self.coordinator.set_optimistic_value("dispatch_mode", 2)
        await self.coordinator.async_request_refresh()

    async def _start_no_battery_charge(self):
        """Mode 19: Prevent all battery charging (solar & grid)."""
        duration = int(safe_get_entity_float(
            self._hass,
            f"number.neovolt_{self._device_name}_dispatch_duration",
            120.0
        ))

        values = [
            1,                              # Para1: Dispatch start
            0,                              # Para2 high byte
            0,                              # Para2 low: Raw 0 (NOT 32000!)
            0,                              # Para3 high byte
            0,                              # Para3 low: Reactive power = 0
            19,                             # Para4: Mode 19 (No Battery Charge)
            0,                              # Para5: SOC (not used)
            0,                              # Para6 high byte
            min(duration * 60, 65535),      # Para6 low: Time (seconds)
            255,                            # Para7: Energy routing (default)
            0,                              # Para8: PV switch (auto)
        ]

        _LOGGER.info(f"Enabling No Battery Charge mode for {duration} minutes")

        await self._hass.async_add_executor_job(
            self._client.write_registers, 0x0880, values
        )
        self.coordinator.set_optimistic_value("dispatch_start", 1)
        self.coordinator.set_optimistic_value("dispatch_power", 0)
        self.coordinator.set_optimistic_value("dispatch_mode", 19)
        await self.coordinator.async_request_refresh()


class NeovoltPVSwitchSelect(CoordinatorEntity, SelectEntity):
    """PV Switch control - controls PV open/close state independently."""

    _attr_options = [
        "Auto",
        "PV Open",
        "PV Close",
    ]

    # Mapping from option to Para8 value
    _option_to_value = {
        "Auto": 0,
        "PV Open": 1,
        "PV Close": 2,
    }

    _value_to_option = {v: k for k, v in _option_to_value.items()}

    def __init__(self, coordinator, device_info, device_name, client, hass):
        """Initialize the PV switch select entity."""
        super().__init__(coordinator)
        self._client = client
        self._hass = hass
        self._device_name = device_name
        self._attr_name = f"Neovolt {device_name} PV Switch"
        self._attr_unique_id = f"neovolt_{device_name}_pv_switch"
        self._attr_icon = "mdi:solar-panel"
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Return True if coordinator has valid cached data."""
        return self.coordinator.has_valid_data

    @property
    def current_option(self):
        """Detect PV switch state from hardware."""
        data = self.coordinator.data
        pv_switch = data.get("dispatch_pv_switch", 0)
        return self._value_to_option.get(pv_switch, "Auto")

    async def async_select_option(self, option: str) -> None:
        """Change the PV switch state."""
        try:
            new_value = self._option_to_value.get(option, 0)
            data = self.coordinator.data

            # Build dispatch values array with current state, updating Para8
            # Reconstruct power encoding from signed dispatch_power
            dispatch_power = data.get("dispatch_power", 0)
            if dispatch_power < 0:
                # Charging: 32000 - watts
                para2_lo = MODBUS_OFFSET + dispatch_power  # dispatch_power is negative
            elif dispatch_power > 0:
                # Discharging: 32000 + watts
                para2_lo = MODBUS_OFFSET + dispatch_power
            else:
                para2_lo = MODBUS_OFFSET

            values = [
                data.get("dispatch_start", 0),          # Para1
                0,                                       # Para2 high byte
                para2_lo,                               # Para2 low byte
                0,                                       # Para3 high byte
                0,                                       # Para3 low byte (reactive power)
                data.get("dispatch_mode", 0),           # Para4
                data.get("dispatch_soc", 0),            # Para5
                0,                                       # Para6 high byte
                data.get("dispatch_time_remaining", 90), # Para6 low byte
                data.get("dispatch_energy_routing", 255), # Para7
                new_value,                               # Para8: PV switch
            ]

            _LOGGER.info(f"Setting PV switch to: {option} (value: {new_value})")

            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, values
            )
            self.coordinator.set_optimistic_value("dispatch_pv_switch", new_value)
            await self.coordinator.async_request_refresh()

        except Exception as e:
            _LOGGER.error(f"Failed to set PV switch to '{option}': {e}")
