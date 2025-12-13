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
    DEFAULT_MAX_CHARGE_POWER,
    DEFAULT_MAX_DISCHARGE_POWER,
    DEVICE_ROLE_FOLLOWER,
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

        # Force Charging Controls (local storage, used by switch) - WITH DYNAMIC MAX
        NeovoltNumber(
            coordinator, device_info, device_name, client, hass,
            "force_charging_power", "Force Charging Power",
            0.5, max_charge_power, 0.1, UnitOfPower.KILO_WATT, None, False,
            default_value=min(3.0, max_charge_power), icon="mdi:lightning-bolt",
            config_entry=entry
        ),
        NeovoltNumber(
            coordinator, device_info, device_name, client, hass,
            "force_charging_duration", "Force Charging Duration",
            1, 480, 1, UnitOfTime.MINUTES, None, False,
            default_value=120, icon="mdi:timer"
        ),
        NeovoltNumber(
            coordinator, device_info, device_name, client, hass,
            "charging_soc_target", "Charging SOC Target",
            10, 100, 1, PERCENTAGE, None, False,
            default_value=100, icon="mdi:battery-charging-100"
        ),

        # Force Discharging Controls (local storage, used by switch) - WITH DYNAMIC MAX
        NeovoltNumber(
            coordinator, device_info, device_name, client, hass,
            "force_discharging_power", "Force Discharging Power",
            0.5, max_discharge_power, 0.1, UnitOfPower.KILO_WATT, None, False,
            default_value=min(3.0, max_discharge_power), icon="mdi:lightning-bolt-outline",
            config_entry=entry
        ),
        NeovoltNumber(
            coordinator, device_info, device_name, client, hass,
            "force_discharging_duration", "Force Discharging Duration",
            1, 480, 1, UnitOfTime.MINUTES, None, False,
            default_value=120, icon="mdi:timer-outline"
        ),
        NeovoltNumber(
            coordinator, device_info, device_name, client, hass,
            "discharging_soc_cutoff", "Discharging SOC Cutoff",
            4, 50, 1, PERCENTAGE, None, False,
            default_value=20, icon="mdi:battery-charging-20"
        ),

        # Prevent Solar Charging Controls (local storage, used by switch)
        NeovoltNumber(
            coordinator, device_info, device_name, client, hass,
            "prevent_solar_charging_duration", "Prevent Solar Charging Duration",
            1, 1440, 1, UnitOfTime.MINUTES, None, False,
            default_value=480, icon="mdi:timer-lock"
        ),

        # PV Capacity (32-bit register, in Watts)
        NeovoltNumber(
            coordinator, device_info, device_name, client, hass,
            "pv_capacity", "PV Capacity",
            0, max_charge_power * 1000, 100, UnitOfPower.WATT, 0x0801, True,
            icon="mdi:solar-power", config_entry=entry, is_32bit=True
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
        scale=1
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
        # Update max value from config entry for power settings
        if self._config_entry and self._key in ["force_charging_power", "force_discharging_power", "pv_capacity"]:
            config_key = CONF_MAX_CHARGE_POWER if "charging" in self._key or self._key == "pv_capacity" else CONF_MAX_DISCHARGE_POWER
            config_max = self._config_entry.data.get(config_key, self._attr_native_max_value)
            # pv_capacity is in Watts, config is in kW
            new_max = config_max * 1000 if self._key == "pv_capacity" else config_max
            if new_max != self._attr_native_max_value:
                _LOGGER.info(f"Updated max value for {self._key} to {new_max}")
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
                await self.coordinator.async_request_refresh()
            else:
                # Store locally for force charge/discharge settings
                _LOGGER.debug(f"Setting local value for {self._key}: {value}")
                self._local_value = value
                self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error(f"Failed to set {self._key}: {e}")