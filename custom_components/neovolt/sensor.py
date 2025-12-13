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

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neovolt sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    device_name = hass.data[DOMAIN][entry.entry_id]["device_name"]

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