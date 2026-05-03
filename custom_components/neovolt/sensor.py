"""Sensor platform for Neovolt Solar Inverter."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfTemperature,
    PERCENTAGE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    DEVICE_ROLE_HOST,
    COMBINED_BATTERY_POWER,
    COMBINED_BATTERY_SOC,
    COMBINED_BATTERY_SOH,
    COMBINED_BATTERY_CAPACITY,
    COMBINED_HOUSE_LOAD,
    COMBINED_PV_POWER,
    COMBINED_BATTERY_MIN_CELL_V,
    COMBINED_BATTERY_MAX_CELL_V,
    COMBINED_BATTERY_MIN_CELL_T,
    COMBINED_BATTERY_MAX_CELL_T,
    COMBINED_BATTERY_CHARGE_E,
    COMBINED_BATTERY_DISCHARGE_E,
    BATTERY_STATUS_MAP,
    BATTERY_RELAY_STATUS_MAP,
    BATTERY_WARNING_BITS,
    BATTERY_FAULT_BITS,
    BATTERY_PROTECTION_BITS,
    INVERTER_WORK_MODE_MAP,
    INVERTER_WARNING_BITS,
    INVERTER_FAULT_BITS,
    INVERTER_FAULT_EXT_BITS,
    SYSTEM_FAULT_BITS,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neovolt sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    device_name = hass.data[DOMAIN][entry.entry_id]["device_name"]
    device_role = hass.data[DOMAIN][entry.entry_id]["device_role"]

    sensors = [
        # Grid Sensors
        NeovoltSensor(coordinator, device_info, device_name, "grid_energy_feed", "Total Energy Feed to Grid", 
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, 
                     SensorStateClass.TOTAL_INCREASING, "mdi:transmission-tower-export"),
        NeovoltSensor(coordinator, device_info, device_name, "grid_energy_consume", "Total Energy Consume from Grid",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.TOTAL_INCREASING, "mdi:transmission-tower-import"),
        NeovoltSensor(coordinator, device_info, device_name, "grid_voltage_a", "Grid Voltage Phase A",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:lightning-bolt"),
        NeovoltSensor(coordinator, device_info, device_name, "grid_voltage_b", "Grid Voltage Phase B",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:lightning-bolt"),
        NeovoltSensor(coordinator, device_info, device_name, "grid_voltage_c", "Grid Voltage Phase C",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:lightning-bolt"),
        NeovoltSensor(coordinator, device_info, device_name, "grid_current_a", "Grid Current Phase A",
                     UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                     SensorStateClass.MEASUREMENT, "mdi:current-ac"),
        NeovoltSensor(coordinator, device_info, device_name, "grid_current_b", "Grid Current Phase B",
                     UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                     SensorStateClass.MEASUREMENT, "mdi:current-ac"),
        NeovoltSensor(coordinator, device_info, device_name, "grid_current_c", "Grid Current Phase C",
                     UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                     SensorStateClass.MEASUREMENT, "mdi:current-ac"),
        NeovoltSensor(coordinator, device_info, device_name, "grid_frequency", "Grid Frequency",
                     UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY,
                     SensorStateClass.MEASUREMENT, "mdi:sine-wave"),
        NeovoltSensor(coordinator, device_info, device_name, "grid_power_a", "Grid Active Power Phase A",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:flash"),
        NeovoltSensor(coordinator, device_info, device_name, "grid_power_b", "Grid Active Power Phase B",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:flash"),
        NeovoltSensor(coordinator, device_info, device_name, "grid_power_c", "Grid Active Power Phase C",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:flash"),
        NeovoltSensor(coordinator, device_info, device_name, "grid_power_total", "Grid Total Active Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:transmission-tower"),
        NeovoltSensor(coordinator, device_info, device_name, "grid_power_factor", "Grid Power Factor",
                     None, SensorDeviceClass.POWER_FACTOR,
                     SensorStateClass.MEASUREMENT, "mdi:cosine-wave"),

        # PV Sensors
        NeovoltSensor(coordinator, device_info, device_name, "pv_energy_feed", "PV Total Energy Feed to Grid",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.TOTAL_INCREASING, "mdi:solar-power"),
        NeovoltSensor(coordinator, device_info, device_name, "pv_voltage_a", "PV Voltage Phase A",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
        NeovoltSensor(coordinator, device_info, device_name, "pv_power_total", "PV Total Active Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:solar-power"),
        NeovoltSensor(coordinator, device_info, device_name, "pv_dc_power_total", "PV DC Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:solar-power"),
        NeovoltSensor(coordinator, device_info, device_name, "pv_ac_power_total", "PV AC Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:solar-power-variant"),

        # Battery Sensors
        NeovoltSensor(coordinator, device_info, device_name, "battery_voltage", "Battery Voltage",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:battery-charging"),
        NeovoltSensor(coordinator, device_info, device_name, "battery_current", "Battery Current",
                     UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                     SensorStateClass.MEASUREMENT, "mdi:current-dc"),
        NeovoltSensor(coordinator, device_info, device_name, "battery_soc", "Battery SOC",
                     PERCENTAGE, SensorDeviceClass.BATTERY,
                     SensorStateClass.MEASUREMENT, "mdi:battery"),
        NeovoltSensor(coordinator, device_info, device_name, "battery_min_cell_voltage", "Battery Min Cell Voltage",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:battery-low"),
        NeovoltSensor(coordinator, device_info, device_name, "battery_max_cell_voltage", "Battery Max Cell Voltage",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:battery-high"),
        NeovoltSensor(coordinator, device_info, device_name, "battery_min_cell_temp", "Battery Min Cell Temperature",
                     UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,
                     SensorStateClass.MEASUREMENT, "mdi:thermometer-low"),
        NeovoltSensor(coordinator, device_info, device_name, "battery_max_cell_temp", "Battery Max Cell Temperature",
                     UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,
                     SensorStateClass.MEASUREMENT, "mdi:thermometer-high"),
        # FIXED: Changed state_class from MEASUREMENT to TOTAL for battery capacity
        NeovoltSensor(coordinator, device_info, device_name, "battery_capacity", "Battery Capacity",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.TOTAL, "mdi:battery-charging-100"),
        NeovoltSensor(coordinator, device_info, device_name, "battery_soh", "Battery SOH",
                     PERCENTAGE, None, SensorStateClass.MEASUREMENT, "mdi:battery-heart-variant"),
        NeovoltSensor(coordinator, device_info, device_name, "battery_charge_energy", "Battery Charge Energy",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.TOTAL_INCREASING, "mdi:battery-plus"),
        NeovoltSensor(coordinator, device_info, device_name, "battery_discharge_energy", "Battery Discharge Energy",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.TOTAL_INCREASING, "mdi:battery-minus"),
        NeovoltSensor(coordinator, device_info, device_name, "battery_power", "Battery Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:battery-charging-outline"),

        # Inverter Sensors
        NeovoltSensor(coordinator, device_info, device_name, "inv_energy_output", "Inverter Energy Output",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.TOTAL_INCREASING, "mdi:export"),
        NeovoltSensor(coordinator, device_info, device_name, "inv_energy_input", "Inverter Energy Input",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.TOTAL_INCREASING, "mdi:import"),
        NeovoltSensor(coordinator, device_info, device_name, "total_pv_energy", "Total PV Energy",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.TOTAL_INCREASING, "mdi:solar-power-variant"),
        NeovoltSensor(coordinator, device_info, device_name, "inv_module_temp", "Inverter Module Temperature",
                     UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,
                     SensorStateClass.MEASUREMENT, "mdi:thermometer"),
        NeovoltSensor(coordinator, device_info, device_name, "pv_boost_temp", "PV Boost Temperature",
                     UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,
                     SensorStateClass.MEASUREMENT, "mdi:thermometer"),
        NeovoltSensor(coordinator, device_info, device_name, "battery_buck_boost_temp", "Battery Buck Boost Temperature",
                     UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,
                     SensorStateClass.MEASUREMENT, "mdi:thermometer"),
        NeovoltSensor(coordinator, device_info, device_name, "bus_voltage", "Bus Voltage",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:sine-wave"),
        NeovoltSensor(coordinator, device_info, device_name, "pv1_voltage", "PV1 Voltage",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:solar-panel-large"),
        NeovoltSensor(coordinator, device_info, device_name, "pv2_voltage", "PV2 Voltage",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:solar-panel-large"),
        NeovoltSensor(coordinator, device_info, device_name, "pv3_voltage", "PV3 Voltage",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:solar-panel-large"),
        NeovoltSensor(coordinator, device_info, device_name, "pv1_current", "PV1 Current",
                     UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                     SensorStateClass.MEASUREMENT, "mdi:current-dc"),
        NeovoltSensor(coordinator, device_info, device_name, "pv2_current", "PV2 Current",
                     UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                     SensorStateClass.MEASUREMENT, "mdi:current-dc"),
        NeovoltSensor(coordinator, device_info, device_name, "pv3_current", "PV3 Current",
                     UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                     SensorStateClass.MEASUREMENT, "mdi:current-dc"),
        NeovoltSensor(coordinator, device_info, device_name, "pv1_power", "PV1 Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
        NeovoltSensor(coordinator, device_info, device_name, "pv2_power", "PV2 Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
        NeovoltSensor(coordinator, device_info, device_name, "pv3_power", "PV3 Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
        NeovoltSensor(coordinator, device_info, device_name, "inv_power_active", "Inverter Active Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:home-lightning-bolt"),
        NeovoltSensor(coordinator, device_info, device_name, "backup_power", "Backup Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:power-plug-off"),

        # AC-coupled PV
        NeovoltSensor(coordinator, device_info, device_name, "pv_inverter_energy", "PV Inverter Energy",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.TOTAL_INCREASING, "mdi:solar-power-variant-outline"),

        # Settings/Status
        NeovoltSensor(coordinator, device_info, device_name, "max_feed_to_grid", "Max Feed to Grid",
                     PERCENTAGE, None, SensorStateClass.MEASUREMENT, "mdi:transmission-tower-export"),
        NeovoltSensor(coordinator, device_info, device_name, "charging_cutoff_soc", "Charging Cutoff SOC",
                     PERCENTAGE, None, SensorStateClass.MEASUREMENT, "mdi:battery-charging-high"),
        NeovoltSensor(coordinator, device_info, device_name, "discharging_cutoff_soc", "Discharging Cutoff SOC",
                     PERCENTAGE, None, SensorStateClass.MEASUREMENT, "mdi:battery-charging-low"),
        NeovoltSensor(coordinator, device_info, device_name, "dispatch_start", "Dispatch Start",
                     None, None, None, "mdi:play-circle"),
        NeovoltSensor(coordinator, device_info, device_name, "dispatch_power", "Dispatch Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:flash"),
        NeovoltDispatchStatusSensor(coordinator, device_info, device_name),

        # Grid power calibration offset readback (AlphaESS shared firmware, register 0x11D5)
        # Shows the currently active offset in watts. Unavailable if firmware doesn't support it.
        NeovoltGridPowerOffsetSensor(coordinator, device_info, device_name),

        # ── Diagnostic / Fault sensors ────────────────────────────────────────
        # Inverter work mode (Note7) — useful to detect "Fault" mode (value 7)
        NeovoltWorkModeSensor(coordinator, device_info, device_name),

        # Battery status (Note1) and relay status (Note2)
        NeovoltBatteryStatusSensor(coordinator, device_info, device_name),
        NeovoltBatteryRelayStatusSensor(coordinator, device_info, device_name),

        # Battery fault / warning / protection bitmask sensors (Notes 4, 5, 6)
        NeovoltFaultSensor(
            coordinator, device_info, device_name,
            key="battery_fault_raw",
            has_fault_key="battery_has_fault",
            name="Battery Fault",
            bit_map=BATTERY_FAULT_BITS,
            icon="mdi:battery-alert",
        ),
        NeovoltFaultSensor(
            coordinator, device_info, device_name,
            key="battery_warning_raw",
            has_fault_key="battery_has_warning",
            name="Battery Warning",
            bit_map=BATTERY_WARNING_BITS,
            icon="mdi:battery-alert-variant",
        ),
        NeovoltFaultSensor(
            coordinator, device_info, device_name,
            key="battery_protection_raw",
            has_fault_key="battery_has_protection",
            name="Battery Protection",
            bit_map=BATTERY_PROTECTION_BITS,
            icon="mdi:battery-lock",
        ),

        # Inverter fault / warning bitmask sensors (Notes 10, 11, 12)
        NeovoltFaultSensor(
            coordinator, device_info, device_name,
            key="inv_fault_raw",
            has_fault_key="inv_has_fault",
            name="Inverter Fault",
            bit_map=INVERTER_FAULT_BITS,
            icon="mdi:alert-circle",
        ),
        NeovoltFaultSensor(
            coordinator, device_info, device_name,
            key="inv_fault_ext_raw",
            has_fault_key="inv_has_fault",
            name="Inverter Fault Extended",
            bit_map=INVERTER_FAULT_EXT_BITS,
            icon="mdi:alert-circle-outline",
        ),
        NeovoltFaultSensor(
            coordinator, device_info, device_name,
            key="inv_warning_raw",
            has_fault_key="inv_has_warning",
            name="Inverter Warning",
            bit_map=INVERTER_WARNING_BITS,
            icon="mdi:alert",
        ),

        # System-level fault bitmask sensor (Note8)
        NeovoltFaultSensor(
            coordinator, device_info, device_name,
            key="system_fault_raw",
            has_fault_key="system_has_fault",
            name="System Fault",
            bit_map=SYSTEM_FAULT_BITS,
            icon="mdi:alert-octagon",
        ),

        # Calculated/Template Sensors
        NeovoltCalculatedSensor(coordinator, device_info, device_name, "total_house_load", "Total House Load",
                               UnitOfPower.WATT, SensorDeviceClass.POWER,
                               SensorStateClass.MEASUREMENT, "mdi:home-lightning-bolt-outline"),
        NeovoltCalculatedSensor(coordinator, device_info, device_name, "excess_grid_export", "Excess Grid Export",
                               UnitOfPower.WATT, SensorDeviceClass.POWER,
                               SensorStateClass.MEASUREMENT, "mdi:transmission-tower-export"),
        NeovoltCalculatedSensor(coordinator, device_info, device_name, "current_pv_production", "Current PV Production",
                               UnitOfPower.WATT, SensorDeviceClass.POWER,
                               SensorStateClass.MEASUREMENT, "mdi:solar-power"),

        # Daily reset sensors
        NeovoltDailyResetSensor(coordinator, device_info, device_name, "pv_inverter_energy_today", "PV Inverter Energy Today",
                               UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                               "mdi:solar-power-variant-outline"),
    ]

    # ── Combined host + follower sensors (host device only) ──────────────────
    # These sensors appear on the host device and show system-wide totals.
    # They are populated by the coordinator only when a follower is linked.
    # On a single-inverter system they will show as unavailable until a
    # follower is configured, at which point they update automatically.
    if device_role == DEVICE_ROLE_HOST:
        combined_sensors = [
            NeovoltCombinedSensor(
                coordinator, device_info, device_name,
                COMBINED_BATTERY_POWER, "Combined Battery Power",
                UnitOfPower.WATT, SensorDeviceClass.POWER,
                SensorStateClass.MEASUREMENT, "mdi:battery-charging",
            ),
            NeovoltCombinedSensor(
                coordinator, device_info, device_name,
                COMBINED_BATTERY_SOC, "Combined Battery SOC",
                PERCENTAGE, SensorDeviceClass.BATTERY,
                SensorStateClass.MEASUREMENT, "mdi:battery",
            ),
            NeovoltCombinedSensor(
                coordinator, device_info, device_name,
                COMBINED_BATTERY_SOH, "Combined Battery SOH",
                PERCENTAGE, None,
                SensorStateClass.MEASUREMENT, "mdi:battery-heart-variant",
            ),
            NeovoltCombinedSensor(
                coordinator, device_info, device_name,
                COMBINED_BATTERY_CAPACITY, "Combined Battery Capacity",
                UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                SensorStateClass.TOTAL, "mdi:battery-charging-100",
            ),
            NeovoltCombinedSensor(
                coordinator, device_info, device_name,
                COMBINED_HOUSE_LOAD, "Combined House Load",
                UnitOfPower.WATT, SensorDeviceClass.POWER,
                SensorStateClass.MEASUREMENT, "mdi:home-lightning-bolt",
            ),
            NeovoltCombinedSensor(
                coordinator, device_info, device_name,
                COMBINED_PV_POWER, "Combined PV Power",
                UnitOfPower.WATT, SensorDeviceClass.POWER,
                SensorStateClass.MEASUREMENT, "mdi:solar-power",
            ),
            NeovoltCombinedSensor(
                coordinator, device_info, device_name,
                COMBINED_BATTERY_MIN_CELL_V, "Combined Battery Min Cell Voltage",
                UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                SensorStateClass.MEASUREMENT, "mdi:battery-low",
            ),
            NeovoltCombinedSensor(
                coordinator, device_info, device_name,
                COMBINED_BATTERY_MAX_CELL_V, "Combined Battery Max Cell Voltage",
                UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                SensorStateClass.MEASUREMENT, "mdi:battery-high",
            ),
            NeovoltCombinedSensor(
                coordinator, device_info, device_name,
                COMBINED_BATTERY_MIN_CELL_T, "Combined Battery Min Cell Temperature",
                UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,
                SensorStateClass.MEASUREMENT, "mdi:thermometer-low",
            ),
            NeovoltCombinedSensor(
                coordinator, device_info, device_name,
                COMBINED_BATTERY_MAX_CELL_T, "Combined Battery Max Cell Temperature",
                UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,
                SensorStateClass.MEASUREMENT, "mdi:thermometer-high",
            ),
            NeovoltCombinedSensor(
                coordinator, device_info, device_name,
                COMBINED_BATTERY_CHARGE_E, "Combined Battery Charge Energy",
                UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                SensorStateClass.TOTAL_INCREASING, "mdi:battery-plus",
            ),
            NeovoltCombinedSensor(
                coordinator, device_info, device_name,
                COMBINED_BATTERY_DISCHARGE_E, "Combined Battery Discharge Energy",
                UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                SensorStateClass.TOTAL_INCREASING, "mdi:battery-minus",
            ),
        ]
        sensors.extend(combined_sensors)

    # System time sensor — available on all roles, polls the inverter clock registers
    sensors.append(NeovoltSystemTimeSensor(coordinator, device_info, device_name))

    async_add_entities(sensors)


class NeovoltSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Neovolt sensor."""

    def __init__(self, coordinator, device_info, device_name, key, name, unit, device_class,
                 state_class, icon):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"Neovolt {device_name} {name}"
        self._attr_unique_id = f"neovolt_{device_name}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Return True if coordinator has valid cached data.

        Override CoordinatorEntity.available to prevent brief unavailability
        during connection hiccups. Entity stays available as long as we have
        cached data that's less than 12 hours old.
        """
        return self.coordinator.has_valid_data

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.coordinator.data.get(self._key)

    @property
    def extra_state_attributes(self):
        """Return additional state attributes including data freshness."""
        attrs = {}
        if hasattr(self.coordinator, 'data_age_seconds'):
            age = self.coordinator.data_age_seconds
            if age is not None:
                attrs["data_age_seconds"] = round(age)
                attrs["data_stale"] = age > 43200  # 12 hours
        return attrs


class NeovoltCalculatedSensor(CoordinatorEntity, SensorEntity):
    """Representation of a calculated Neovolt sensor."""

    def __init__(self, coordinator, device_info, device_name, key, name, unit, device_class,
                 state_class, icon):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"Neovolt {device_name} {name}"
        self._attr_unique_id = f"neovolt_{device_name}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Return True if coordinator has valid cached data."""
        return self.coordinator.has_valid_data

    @property
    def native_value(self):
        """Return the calculated state of the sensor."""
        # These sensors are pre-calculated in the coordinator
        # Just return the value from coordinator data
        return self.coordinator.data.get(self._key)

    @property
    def extra_state_attributes(self):
        """Return additional state attributes including data freshness."""
        attrs = {}
        if hasattr(self.coordinator, 'data_age_seconds'):
            age = self.coordinator.data_age_seconds
            if age is not None:
                attrs["data_age_seconds"] = round(age)
                attrs["data_stale"] = age > 43200  # 12 hours
        return attrs


class NeovoltCombinedSensor(CoordinatorEntity, SensorEntity):
    """Combined host + follower sensor — shows system-wide totals on the host device.

    Values are pre-calculated by the coordinator's _calculate_combined_values()
    and written into the host data dict as COMBINED_* keys. If no follower is
    linked the key will be absent from the data dict and the sensor reports
    unavailable, distinguishing it clearly from a zero reading.
    """

    def __init__(self, coordinator, device_info, device_name, key, name, unit,
                 device_class, state_class, icon):
        """Initialize the combined sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"Neovolt {device_name} {name}"
        self._attr_unique_id = f"neovolt_{device_name}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Available whenever the host coordinator has valid data.

        Option A behaviour: combined sensors always show a value. When no
        follower is linked they equal the host-only value. When a follower is
        linked they reflect the true combined system total.
        """
        return self.coordinator.has_valid_data and self._key in self.coordinator.data

    @property
    def native_value(self):
        """Return the combined value from the host coordinator data dict."""
        return self.coordinator.data.get(self._key)

    @property
    def extra_state_attributes(self):
        """Return data freshness attributes and follower link status."""
        attrs = {"follower_linked": self.coordinator.follower_coordinator is not None}
        if hasattr(self.coordinator, 'data_age_seconds'):
            age = self.coordinator.data_age_seconds
            if age is not None:
                attrs["data_age_seconds"] = round(age)
                attrs["data_stale"] = age > 43200  # 12 hours
        return attrs


class NeovoltDailyResetSensor(CoordinatorEntity, SensorEntity):
    """Representation of a daily reset sensor that tracks energy from midnight."""

    def __init__(self, coordinator, device_info, device_name, key, name, unit, device_class, icon):
        """Initialize the daily reset sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"Neovolt {device_name} {name}"
        self._attr_unique_id = f"neovolt_{device_name}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = icon
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Return True if coordinator has valid cached data."""
        return self.coordinator.has_valid_data

    @property
    def native_value(self):
        """Return the daily reset value from coordinator."""
        return self.coordinator.data.get(self._key)

    @property
    def extra_state_attributes(self):
        """Return additional state attributes including data freshness."""
        attrs = {}
        if hasattr(self.coordinator, 'data_age_seconds'):
            age = self.coordinator.data_age_seconds
            if age is not None:
                attrs["data_age_seconds"] = round(age)
                attrs["data_stale"] = age > 43200  # 12 hours
        return attrs


class NeovoltDispatchStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing current dispatch operation status."""

    def __init__(self, coordinator, device_info, device_name):
        """Initialize the dispatch status sensor."""
        super().__init__(coordinator)
        self._device_name = device_name
        self._attr_name = f"Neovolt {device_name} Dispatch Status"
        self._attr_unique_id = f"neovolt_{device_name}_dispatch_status"
        self._attr_icon = "mdi:information-outline"
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Return True if coordinator has valid cached data."""
        return self.coordinator.has_valid_data

    @property
    def native_value(self) -> str:
        """Return human-readable dispatch status."""
        from .const import DISPATCH_MODE_DYNAMIC_EXPORT, DISPATCH_MODE_DYNAMIC_IMPORT, DISPATCH_MODE_NO_DISCHARGE

        data = self.coordinator.data
        dispatch_start = data.get("dispatch_start", 0)

        if dispatch_start != 1:
            return "Normal (Auto)"

        dispatch_power = data.get("dispatch_power", 0)
        dispatch_mode = data.get("dispatch_mode", 0)
        dispatch_time = data.get("dispatch_time_remaining", 0)

        # Determine mode and power display
        mode = None
        power_kw = None

        if dispatch_mode == DISPATCH_MODE_DYNAMIC_EXPORT:
            # Get current load and target for Dynamic Export
            load = data.get("total_house_load", 0)

            # Try to get target export value
            try:
                from .select import safe_get_entity_float
                target = safe_get_entity_float(
                    self.hass,
                    f"number.neovolt_{self._device_name}_dynamic_mode_power_target",
                    1.0
                )
                mode = f"Dynamic Export (Load: {load/1000:.1f}kW + {target:.1f}kW)"
                power_kw = abs(dispatch_power) / 1000 if dispatch_power else None
            except Exception:
                mode = "Dynamic Export"
                power_kw = abs(dispatch_power) / 1000 if dispatch_power else None

            # For Dynamic Export, get time remaining from the manager
            if hasattr(self.coordinator, 'dynamic_export_manager'):
                manager = self.coordinator.dynamic_export_manager
                if manager.is_running and manager._start_time and manager._duration_minutes:
                    elapsed_minutes = (dt_util.now() - manager._start_time).total_seconds() / 60.0
                    remaining_minutes = max(0, manager._duration_minutes - elapsed_minutes)
                    dispatch_time = int(remaining_minutes * 60)  # Convert to seconds

        elif dispatch_mode == DISPATCH_MODE_DYNAMIC_IMPORT:
            # Get target import value
            try:
                from .select import safe_get_entity_float
                target = safe_get_entity_float(
                    self.hass,
                    f"number.neovolt_{self._device_name}_dynamic_mode_power_target",
                    1.0
                )
                mode = f"Dynamic Import (Target: {target:.1f}kW from grid)"
                power_kw = abs(dispatch_power) / 1000 if dispatch_power else None
            except Exception:
                mode = "Dynamic Import"
                power_kw = abs(dispatch_power) / 1000 if dispatch_power else None

            # Get time remaining from the import manager
            if hasattr(self.coordinator, 'dynamic_import_manager'):
                manager = self.coordinator.dynamic_import_manager
                if manager.is_running and manager._start_time and manager._duration_minutes:
                    elapsed_minutes = (dt_util.now() - manager._start_time).total_seconds() / 60.0
                    remaining_minutes = max(0, manager._duration_minutes - elapsed_minutes)
                    dispatch_time = int(remaining_minutes * 60)  # Convert to seconds

        elif dispatch_mode == 1:
            mode = "Battery PV Only"
        elif dispatch_mode == 3:
            mode = "Load Following"
            power_kw = abs(dispatch_power) / 1000 if dispatch_power else None
        elif dispatch_mode == 19:
            mode = "No Battery Charge"
        elif dispatch_mode == DISPATCH_MODE_NO_DISCHARGE:
            mode = "Idle (No Dispatch)"
        elif dispatch_mode == 2:
            if dispatch_power > 0:
                mode = "Force Discharging"
                power_kw = dispatch_power / 1000
            elif dispatch_power == -50:
                mode = "Preventing Solar Charge"
            elif dispatch_power < 0:
                mode = "Force Charging"
                power_kw = abs(dispatch_power) / 1000
            else:
                mode = "Dispatch Active"
        else:
            mode = f"Mode {dispatch_mode}"

        # Build status string — suppress power display for dynamic/no-power modes
        dynamic_modes = (DISPATCH_MODE_DYNAMIC_EXPORT, DISPATCH_MODE_DYNAMIC_IMPORT, DISPATCH_MODE_NO_DISCHARGE)
        if power_kw and dispatch_mode not in dynamic_modes:
            status = f"{mode} @ {power_kw:.1f}kW"
        else:
            status = mode

        # Add time remaining (shown for all modes including dynamic ones)
        if dispatch_time > 0:
            hours = dispatch_time // 3600
            minutes = (dispatch_time % 3600) // 60
            if hours > 0:
                status = f"{status} ({hours}h {minutes}m)"
            elif minutes > 0:
                status = f"{status} ({minutes}m)"

        return status

    @property
    def extra_state_attributes(self) -> dict:
        """Return detailed dispatch state as attributes."""
        from .const import DISPATCH_MODE_DYNAMIC_EXPORT, DISPATCH_MODE_DYNAMIC_IMPORT

        data = self.coordinator.data
        attrs = {
            "dispatch_active": data.get("dispatch_start", 0) == 1,
            "dispatch_power_w": data.get("dispatch_power", 0),
            "dispatch_mode": data.get("dispatch_mode", 0),
            "dispatch_soc_value": data.get("dispatch_soc", 0),
            "dispatch_time_remaining_s": data.get("dispatch_time_remaining", 0),
        }

        current_mode = data.get("dispatch_mode", 0)

        # Add Dynamic Export specific attributes
        if current_mode == DISPATCH_MODE_DYNAMIC_EXPORT:
            attrs["dynamic_export_active"] = True
            if hasattr(self.coordinator, 'dynamic_export_manager'):
                attrs["dynamic_export_running"] = self.coordinator.dynamic_export_manager.is_running

        # Add Dynamic Import specific attributes
        elif current_mode == DISPATCH_MODE_DYNAMIC_IMPORT:
            attrs["dynamic_import_active"] = True
            if hasattr(self.coordinator, 'dynamic_import_manager'):
                attrs["dynamic_import_running"] = self.coordinator.dynamic_import_manager.is_running

        return attrs

class NeovoltFaultSensor(CoordinatorEntity, SensorEntity):
    """Diagnostic sensor that decodes a bitmask register into a human-readable state.

    State is "OK" when no bits are set, or a short summary of the first active
    fault/warning/protection bit otherwise.  All active conditions are exposed
    as a list in the ``active_conditions`` extra state attribute so that HA
    automations can inspect the full set of active bits.

    The raw integer value is also exposed as ``raw_value`` for advanced use.
    """

    def __init__(
        self,
        coordinator,
        device_info,
        device_name: str,
        key: str,
        has_fault_key: str,
        name: str,
        bit_map: dict,
        icon: str,
    ):
        """Initialize the fault sensor."""
        super().__init__(coordinator)
        self._key = key
        self._has_fault_key = has_fault_key
        self._bit_map = bit_map
        self._attr_name = f"Neovolt {device_name} {name}"
        self._attr_unique_id = f"neovolt_{device_name}_{key}_sensor"
        self._attr_icon = icon
        self._attr_device_info = device_info
        # No unit, no device class — it's a text/diagnostic sensor
        self._attr_native_unit_of_measurement = None
        self._attr_device_class = None
        self._attr_state_class = None

    @property
    def available(self) -> bool:
        """Return True if coordinator has valid cached data and register was read."""
        return self.coordinator.has_valid_data and self._key in self.coordinator.data

    def _get_active_conditions(self) -> list[str]:
        """Return a list of human-readable labels for all set bits in the raw value."""
        raw = self.coordinator.data.get(self._key, 0) or 0
        active = []
        for bit, label in self._bit_map.items():
            if raw & (1 << bit):
                active.append(label)
        return active

    @property
    def native_value(self) -> str:
        """Return 'OK' when no faults, or the first active condition label."""
        active = self._get_active_conditions()
        if not active:
            return "OK"
        # Return the first (lowest bit) active condition as the primary state
        return active[0] if len(active) == 1 else f"{active[0]} (+{len(active) - 1} more)"

    @property
    def extra_state_attributes(self) -> dict:
        """Return the full set of active conditions and the raw register value."""
        active = self._get_active_conditions()
        raw = self.coordinator.data.get(self._key, 0) or 0
        return {
            "active_conditions": active,
            "active_count": len(active),
            "raw_value": raw,
            "raw_hex": hex(raw),
            "has_fault": bool(self.coordinator.data.get(self._has_fault_key, False)),
        }


class NeovoltWorkModeSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the inverter work mode (register 0x050E, Note7).

    State is the human-readable mode name.  "Fault" mode (value 7) is the
    most actionable: it means the inverter has stopped and raised a fault.
    """

    def __init__(self, coordinator, device_info, device_name: str):
        """Initialize the work mode sensor."""
        super().__init__(coordinator)
        self._attr_name = f"Neovolt {device_name} Inverter Work Mode"
        self._attr_unique_id = f"neovolt_{device_name}_inv_work_mode"
        self._attr_icon = "mdi:cog"
        self._attr_device_info = device_info
        self._attr_native_unit_of_measurement = None
        self._attr_device_class = None
        self._attr_state_class = None

    @property
    def available(self) -> bool:
        """Return True if coordinator has valid cached data."""
        return (
            self.coordinator.has_valid_data
            and "inv_work_mode_raw" in self.coordinator.data
        )

    @property
    def native_value(self) -> str:
        """Return the human-readable work mode name."""
        raw = self.coordinator.data.get("inv_work_mode_raw")
        if raw is None:
            return None
        return INVERTER_WORK_MODE_MAP.get(raw, f"Unknown ({raw})")

    @property
    def extra_state_attributes(self) -> dict:
        """Return raw mode value and fault-mode flag."""
        raw = self.coordinator.data.get("inv_work_mode_raw")
        return {
            "raw_value": raw,
            "in_fault_mode": self.coordinator.data.get("inv_in_fault_mode", False),
        }


class NeovoltBatteryStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the battery charge/discharge status (register 0x0103, Note1)."""

    def __init__(self, coordinator, device_info, device_name: str):
        """Initialize the battery status sensor."""
        super().__init__(coordinator)
        self._attr_name = f"Neovolt {device_name} Battery Status"
        self._attr_unique_id = f"neovolt_{device_name}_battery_status"
        self._attr_icon = "mdi:battery-charging"
        self._attr_device_info = device_info
        self._attr_native_unit_of_measurement = None
        self._attr_device_class = None
        self._attr_state_class = None

    @property
    def available(self) -> bool:
        """Return True if coordinator has valid cached data."""
        return (
            self.coordinator.has_valid_data
            and "battery_status_raw" in self.coordinator.data
        )

    @property
    def native_value(self) -> str:
        """Return the human-readable battery status."""
        raw = self.coordinator.data.get("battery_status_raw")
        if raw is None:
            return None
        return BATTERY_STATUS_MAP.get(raw, f"Unknown ({raw})")

    @property
    def extra_state_attributes(self) -> dict:
        """Return raw register value."""
        return {"raw_value": self.coordinator.data.get("battery_status_raw")}


class NeovoltBatteryRelayStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the battery relay status (register 0x0104, Note2)."""

    def __init__(self, coordinator, device_info, device_name: str):
        """Initialize the battery relay status sensor."""
        super().__init__(coordinator)
        self._attr_name = f"Neovolt {device_name} Battery Relay Status"
        self._attr_unique_id = f"neovolt_{device_name}_battery_relay_status"
        self._attr_icon = "mdi:electric-switch"
        self._attr_device_info = device_info
        self._attr_native_unit_of_measurement = None
        self._attr_device_class = None
        self._attr_state_class = None

    @property
    def available(self) -> bool:
        """Return True if coordinator has valid cached data."""
        return (
            self.coordinator.has_valid_data
            and "battery_relay_status_raw" in self.coordinator.data
        )

    @property
    def native_value(self) -> str:
        """Return the human-readable relay status."""
        raw = self.coordinator.data.get("battery_relay_status_raw")
        if raw is None:
            return None
        return BATTERY_RELAY_STATUS_MAP.get(raw, f"Unknown ({raw})")

    @property
    def extra_state_attributes(self) -> dict:
        """Return raw register value."""
        return {"raw_value": self.coordinator.data.get("battery_relay_status_raw")}


class NeovoltGridPowerOffsetSensor(CoordinatorEntity, SensorEntity):
    """Readback sensor for the grid power calibration offset (register 0x11D5).

    Shows the currently active offset value in watts. The entity reports
    unavailable until the calibration register block has been successfully
    read at least once, confirming the AlphaESS shared firmware supports it.
    If the register does not exist on this firmware the entity stays unavailable.
    """

    def __init__(self, coordinator, device_info, device_name):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = f"Neovolt {device_name} Grid Power Offset"
        self._attr_unique_id = f"neovolt_{device_name}_grid_power_offset_sensor"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:tune"
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Only available once the calibration block has been confirmed accessible."""
        if not self.coordinator.has_valid_data:
            return False
        return self.coordinator.data.get("grid_power_offset_supported", False)

    @property
    def native_value(self):
        """Return the current grid power offset in watts."""
        return self.coordinator.data.get("grid_power_offset")


class NeovoltSystemTimeSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the inverter's internal system clock.

    State is the inverter time formatted as an ISO-style string
    (YYYY-MM-DD HH:MM:SS) so users can immediately see whether the clock
    is correct and whether a Sync is needed.

    The sensor also exposes the individual time components as extra state
    attributes, and a ``drift_seconds`` attribute showing the difference
    between the inverter clock and HA's current time — positive means the
    inverter is ahead, negative means it is behind.
    """

    def __init__(self, coordinator, device_info, device_name: str) -> None:
        """Initialize the system time sensor."""
        super().__init__(coordinator)
        self._attr_name = f"Neovolt {device_name} Inverter System Time"
        self._attr_unique_id = f"neovolt_{device_name}_inverter_system_time"
        self._attr_icon = "mdi:clock-outline"
        self._attr_device_info = device_info
        # Plain string state — no unit, no numeric device class
        self._attr_native_unit_of_measurement = None
        self._attr_device_class = None
        self._attr_state_class = None

    @property
    def available(self) -> bool:
        """Available once the coordinator has read the system time block."""
        return (
            self.coordinator.has_valid_data
            and "inverter_time_year" in self.coordinator.data
        )

    def _get_time_parts(self) -> tuple[int, int, int, int, int, int] | None:
        """Return (year, month, day, hour, minute, second) or None if not ready."""
        data = self.coordinator.data
        keys = (
            "inverter_time_year",
            "inverter_time_month",
            "inverter_time_day",
            "inverter_time_hour",
            "inverter_time_minute",
            "inverter_time_second",
        )
        values = [data.get(k) for k in keys]
        if any(v is None for v in values):
            return None
        return tuple(int(v) for v in values)

    @property
    def native_value(self) -> str | None:
        """Return inverter time as 'YYYY-MM-DD HH:MM:SS'."""
        parts = self._get_time_parts()
        if parts is None:
            return None
        year, month, day, hour, minute, second = parts
        try:
            return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
        except (ValueError, TypeError):
            return None

    @property
    def extra_state_attributes(self) -> dict:
        """Return individual time components and drift vs HA time."""
        parts = self._get_time_parts()
        if parts is None:
            return {}

        year, month, day, hour, minute, second = parts
        attrs = {
            "year":   year,
            "month":  month,
            "day":    day,
            "hour":   hour,
            "minute": minute,
            "second": second,
        }

        # Calculate drift: positive = inverter ahead of HA, negative = behind
        try:
            from datetime import datetime as dt
            inverter_dt = dt(year, month, day, hour, minute, second)
            ha_now = dt_util.now().replace(tzinfo=None)
            drift = int((inverter_dt - ha_now).total_seconds())
            attrs["drift_seconds"] = drift
            attrs["drift_minutes"] = round(drift / 60, 1)
        except (ValueError, TypeError):
            pass

        return attrs