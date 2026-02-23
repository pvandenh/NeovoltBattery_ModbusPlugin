"""Number platform for Neovolt Solar Inverter."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    CONF_DYNAMIC_EXPORT_TARGET,
    DEFAULT_MAX_CHARGE_POWER,
    DEFAULT_MAX_DISCHARGE_POWER,
    DEFAULT_DYNAMIC_EXPORT_TARGET,
    DYNAMIC_EXPORT_MAX_POWER,
    DEVICE_ROLE_FOLLOWER,
    GRID_POWER_OFFSET_REGISTER,
    GRID_POWER_OFFSET_MIN,
    GRID_POWER_OFFSET_MAX,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neovolt numbers."""
    device_role = hass.data[DOMAIN][entry.entry_id]["device_role"]

    # Skip control entities for follower devices
    if device_role == DEVICE_ROLE_FOLLOWER:
        return

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    device_name = hass.data[DOMAIN][entry.entry_id]["device_name"]

    # Get max power from config entry
    max_charge_power = entry.data.get(CONF_MAX_CHARGE_POWER, DEFAULT_MAX_CHARGE_POWER)
    max_discharge_power = entry.data.get(CONF_MAX_DISCHARGE_POWER, DEFAULT_MAX_DISCHARGE_POWER)

    numbers = [
        # System Settings (write to Modbus)
        NeovoltNumber(
            coordinator, device_info, device_name, client, hass,
            "max_feed_to_grid", "Max Feed to Grid Power",
            0, 100, 1, PERCENTAGE, 0x0800, True
        ),
        NeovoltNumber(
            coordinator, device_info, device_name, client, hass,
            "charging_cutoff_soc", "Charging Cutoff SOC",
            10, 100, 1, PERCENTAGE, 0x0855, True
        ),
        NeovoltNumber(
            coordinator, device_info, device_name, client, hass,
            "discharging_cutoff_soc", "Discharging Cutoff SOC (Default)",
            4, 100, 1, PERCENTAGE, 0x0850, True
        ),

        # Consolidated Dispatch Controls (local storage, used by dispatch mode select)
        NeovoltNumber(
            coordinator, device_info, device_name, client, hass,
            "dispatch_power", "Dispatch Power",
            0.5, max(max_charge_power, max_discharge_power), 0.1, UnitOfPower.KILO_WATT, None, False,
            default_value=3.0, icon="mdi:lightning-bolt",
            config_entry=entry
        ),
        NeovoltNumber(
            coordinator, device_info, device_name, client, hass,
            "dispatch_duration", "Dispatch Duration",
            1, 480, 1, UnitOfTime.MINUTES, None, False,
            default_value=120, icon="mdi:timer"
        ),
        NeovoltNumber(
            coordinator, device_info, device_name, client, hass,
            "dispatch_charge_soc", "Dispatch Charge Target SOC",
            10, 100, 1, PERCENTAGE, None, False,
            default_value=100, icon="mdi:battery-charging-high"
        ),
        NeovoltNumber(
            coordinator, device_info, device_name, client, hass,
            "dispatch_discharge_soc", "Dispatch Discharge Cutoff SOC",
            4, 100, 1, PERCENTAGE, None, False,
            default_value=10, icon="mdi:battery-low"
        ),

        # Dynamic Export Target (local storage, used by dynamic export mode)
        # Fixed max to 15kW to support AC-coupled systems
        NeovoltNumber(
            coordinator, device_info, device_name, client, hass,
            "dynamic_export_target", "Dynamic Export Target",
            0.5, DYNAMIC_EXPORT_MAX_POWER, 0.1, UnitOfPower.KILO_WATT, None, False,
            default_value=DEFAULT_DYNAMIC_EXPORT_TARGET, icon="mdi:transmission-tower-export",
            config_entry=entry, fixed_max=True
        ),

        # PV Capacity (32-bit register, in Watts)
        NeovoltNumber(
            coordinator, device_info, device_name, client, hass,
            "pv_capacity", "PV Capacity",
            0, max_charge_power * 1000, 100, UnitOfPower.WATT, 0x0801, True,
            icon="mdi:solar-power", config_entry=entry, is_32bit=True
        ),

        # Grid Power Offset (AlphaESS shared firmware, register 0x11D5)
        # Compensates for persistent grid import undershoot (small constant import at idle).
        # Positive value → inverter believes it is importing more → discharges slightly harder.
        # Set to 0 to disable (default). The entity will show as unavailable if the
        # calibration register block is not supported on this firmware version.
        NeovoltGridPowerOffsetNumber(
            coordinator, device_info, device_name, client, hass
        ),
    ]

    async_add_entities(numbers)


class NeovoltNumber(CoordinatorEntity, NumberEntity):
    """Representation of a Neovolt number entity."""

    def __init__(
        self,
        coordinator,
        device_info,
        device_name,
        client,
        hass,
        key,
        name,
        min_val,
        max_val,
        step,
        unit,
        address=None,
        write_to_modbus=True,
        default_value=None,
        icon=None,
        config_entry=None,
        is_32bit=False,
        scale=1,
        fixed_max=False
    ):
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._client = client
        self._hass = hass
        self._key = key
        self._address = address
        self._write_to_modbus = write_to_modbus
        self._config_entry = config_entry
        self._is_32bit = is_32bit
        self._scale = scale
        self._fixed_max = fixed_max  # If True, max value is fixed and won't update from config
        self._attr_name = f"Neovolt {device_name} {name}"
        self._attr_unique_id = f"neovolt_{device_name}_{key}"
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_mode = NumberMode.SLIDER
        self._attr_device_info = device_info

        if icon:
            self._attr_icon = icon

        # Set default values for local settings
        if not write_to_modbus:
            self._local_value = default_value if default_value is not None else min_val

    @property
    def available(self) -> bool:
        """Return True if coordinator has valid cached data."""
        return self.coordinator.has_valid_data

    @property
    def native_max_value(self) -> float:
        """Return the maximum value (dynamically from config if applicable)."""
        # Skip dynamic max update if fixed_max is True (e.g., dynamic_export_target)
        if self._fixed_max:
            return self._attr_native_max_value
        
        # Update max value from config entry for power settings
        if self._config_entry and self._key in ["dispatch_power", "pv_capacity"]:
            if self._key == "dispatch_power":
                # Use the higher of charge/discharge max power
                charge_max = self._config_entry.data.get(CONF_MAX_CHARGE_POWER, DEFAULT_MAX_CHARGE_POWER)
                discharge_max = self._config_entry.data.get(CONF_MAX_DISCHARGE_POWER, DEFAULT_MAX_DISCHARGE_POWER)
                new_max = max(charge_max, discharge_max)
            else:
                # pv_capacity is in Watts, config is in kW
                new_max = self._config_entry.data.get(CONF_MAX_CHARGE_POWER, self._attr_native_max_value) * 1000
            if new_max != self._attr_native_max_value:
                _LOGGER.debug(f"Updated max value for {self._key} to {new_max}")
                self._attr_native_max_value = new_max
        return self._attr_native_max_value

    @property
    def native_value(self):
        """Return the current value."""
        if self._write_to_modbus:
            # Get value from Modbus (coordinator data)
            return self.coordinator.data.get(self._key)
        else:
            # Return local value for force charge/discharge settings
            return getattr(self, '_local_value', self._attr_native_min_value)

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        try:
            if self._write_to_modbus and self._address:
                if self._is_32bit:
                    # 32-bit write: convert to scaled value and split into high/low words
                    scaled_value = int(value * self._scale)
                    high_word = (scaled_value >> 16) & 0xFFFF
                    low_word = scaled_value & 0xFFFF
                    _LOGGER.info(
                        f"Writing {value} (scaled: {scaled_value}) to Modbus registers "
                        f"{hex(self._address)}/{hex(self._address + 1)} for {self._key}"
                    )
                    await self._hass.async_add_executor_job(
                        self._client.write_registers, self._address, [high_word, low_word]
                    )
                else:
                    # Single register write
                    _LOGGER.info(f"Writing {value} to Modbus register {hex(self._address)} for {self._key}")
                    await self._hass.async_add_executor_job(
                        self._client.write_register, self._address, int(value)
                    )
                # Optimistic update - show expected value immediately
                self.coordinator.set_optimistic_value(self._key, value)
                await self.coordinator.async_request_refresh()
            else:
                # Store locally for force charge/discharge settings
                _LOGGER.debug(f"Setting local value for {self._key}: {value}")
                self._local_value = value
                self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error(f"Failed to set {self._key}: {e}")


class NeovoltGridPowerOffsetNumber(CoordinatorEntity, NumberEntity):
    """Grid power calibration offset — register 0x11D5 (AlphaESS shared firmware).

    Positive value (e.g. 30) → inverter thinks it is importing 30W more than measured
    → it discharges slightly harder → persistent grid import undershoot is cancelled.

    Set to 0 to disable. The entity reports unavailable if the calibration register
    block is not accessible on this firmware (grid_power_offset_supported == False or absent).
    """

    def __init__(self, coordinator, device_info, device_name, client, hass):
        """Initialize the grid power offset number."""
        super().__init__(coordinator)
        self._client = client
        self._hass = hass
        self._device_name = device_name
        self._attr_name = f"Neovolt {device_name} Grid Power Offset"
        self._attr_unique_id = f"neovolt_{device_name}_grid_power_offset"
        self._attr_native_min_value = GRID_POWER_OFFSET_MIN
        self._attr_native_max_value = GRID_POWER_OFFSET_MAX
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_mode = NumberMode.SLIDER
        self._attr_icon = "mdi:tune"
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Return True only if the calibration register block is confirmed accessible."""
        if not self.coordinator.has_valid_data:
            return False
        # Only available once the calibration block has been successfully read at least once.
        # If the register doesn't exist on this firmware, grid_power_offset_supported stays absent.
        return self.coordinator.data.get("grid_power_offset_supported", False)

    @property
    def native_value(self):
        """Return the current grid power offset in watts."""
        return self.coordinator.data.get("grid_power_offset")

    async def async_set_native_value(self, value: float) -> None:
        """Write new grid power offset to register 0x11D5."""
        int_value = int(value)
        # Encode as a 16-bit two's-complement value for negative numbers
        if int_value < 0:
            int_value = int_value & 0xFFFF
        try:
            _LOGGER.info(
                f"Writing grid power offset {value}W to register "
                f"{hex(GRID_POWER_OFFSET_REGISTER)} for {self._device_name}"
            )
            await self._hass.async_add_executor_job(
                self._client.write_register, GRID_POWER_OFFSET_REGISTER, int_value
            )
            # Optimistic update so UI reflects the change immediately
            self.coordinator.set_optimistic_value("grid_power_offset", int(value))
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to set grid power offset: {e}")