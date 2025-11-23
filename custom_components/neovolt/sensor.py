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
    is_multi_inverter = hass.data[DOMAIN][entry.entry_id].get("is_multi_inverter", False)

    if is_multi_inverter:
        # Multi-inverter setup
        await async_setup_multi_inverter_sensors(hass, entry, async_add_entities, coordinator)
    else:
        # Single inverter setup
        await async_setup_single_inverter_sensors(hass, entry, async_add_entities, coordinator)


async def async_setup_single_inverter_sensors(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    coordinator,
) -> None:
    """Set up sensors for single inverter."""
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]

    sensors = [
        # Grid Sensors
        NeovoltSensor(coordinator, device_info, "grid_energy_feed", "Total Energy Feed to Grid", 
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, 
                     SensorStateClass.TOTAL_INCREASING, "mdi:transmission-tower-export"),
        NeovoltSensor(coordinator, device_info, "grid_energy_consume", "Total Energy Consume from Grid",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.TOTAL_INCREASING, "mdi:transmission-tower-import"),
        NeovoltSensor(coordinator, device_info, "grid_voltage_a", "Grid Voltage Phase A",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:lightning-bolt"),
        NeovoltSensor(coordinator, device_info, "grid_voltage_b", "Grid Voltage Phase B",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:lightning-bolt"),
        NeovoltSensor(coordinator, device_info, "grid_voltage_c", "Grid Voltage Phase C",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:lightning-bolt"),
        NeovoltSensor(coordinator, device_info, "grid_current_a", "Grid Current Phase A",
                     UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                     SensorStateClass.MEASUREMENT, "mdi:current-ac"),
        NeovoltSensor(coordinator, device_info, "grid_current_b", "Grid Current Phase B",
                     UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                     SensorStateClass.MEASUREMENT, "mdi:current-ac"),
        NeovoltSensor(coordinator, device_info, "grid_current_c", "Grid Current Phase C",
                     UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                     SensorStateClass.MEASUREMENT, "mdi:current-ac"),
        NeovoltSensor(coordinator, device_info, "grid_frequency", "Grid Frequency",
                     UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY,
                     SensorStateClass.MEASUREMENT, "mdi:sine-wave"),
        NeovoltSensor(coordinator, device_info, "grid_power_a", "Grid Active Power Phase A",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:flash"),
        NeovoltSensor(coordinator, device_info, "grid_power_b", "Grid Active Power Phase B",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:flash"),
        NeovoltSensor(coordinator, device_info, "grid_power_c", "Grid Active Power Phase C",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:flash"),
        NeovoltSensor(coordinator, device_info, "grid_power_total", "Grid Total Active Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:transmission-tower"),
        NeovoltSensor(coordinator, device_info, "grid_power_factor", "Grid Power Factor",
                     None, SensorDeviceClass.POWER_FACTOR,
                     SensorStateClass.MEASUREMENT, "mdi:cosine-wave"),
        
        # PV Sensors
        NeovoltSensor(coordinator, device_info, "pv_energy_feed", "PV Total Energy Feed to Grid",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.TOTAL_INCREASING, "mdi:solar-power"),
        NeovoltSensor(coordinator, device_info, "pv_voltage_a", "PV Voltage Phase A",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
        NeovoltSensor(coordinator, device_info, "pv_power_total", "PV Total Active Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:solar-power"),
        
        # Battery Sensors
        NeovoltSensor(coordinator, device_info, "battery_voltage", "Battery Voltage",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:battery-charging"),
        NeovoltSensor(coordinator, device_info, "battery_current", "Battery Current",
                     UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                     SensorStateClass.MEASUREMENT, "mdi:current-dc"),
        NeovoltSensor(coordinator, device_info, "battery_soc", "Battery SOC",
                     PERCENTAGE, SensorDeviceClass.BATTERY,
                     SensorStateClass.MEASUREMENT, "mdi:battery"),
        NeovoltSensor(coordinator, device_info, "battery_min_cell_voltage", "Battery Min Cell Voltage",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:battery-low"),
        NeovoltSensor(coordinator, device_info, "battery_max_cell_voltage", "Battery Max Cell Voltage",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:battery-high"),
        NeovoltSensor(coordinator, device_info, "battery_min_cell_temp", "Battery Min Cell Temperature",
                     UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,
                     SensorStateClass.MEASUREMENT, "mdi:thermometer-low"),
        NeovoltSensor(coordinator, device_info, "battery_max_cell_temp", "Battery Max Cell Temperature",
                     UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,
                     SensorStateClass.MEASUREMENT, "mdi:thermometer-high"),
        NeovoltSensor(coordinator, device_info, "battery_capacity", "Battery Capacity",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.MEASUREMENT, "mdi:battery-charging-100"),
        NeovoltSensor(coordinator, device_info, "battery_soh", "Battery SOH",
                     PERCENTAGE, None, SensorStateClass.MEASUREMENT, "mdi:battery-heart-variant"),
        NeovoltSensor(coordinator, device_info, "battery_charge_energy", "Battery Charge Energy",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.TOTAL_INCREASING, "mdi:battery-plus"),
        NeovoltSensor(coordinator, device_info, "battery_discharge_energy", "Battery Discharge Energy",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.TOTAL_INCREASING, "mdi:battery-minus"),
        NeovoltSensor(coordinator, device_info, "battery_power", "Battery Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:battery-charging-outline"),
        
        # Inverter Sensors
        NeovoltSensor(coordinator, device_info, "inv_energy_output", "Inverter Energy Output",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.TOTAL_INCREASING, "mdi:export"),
        NeovoltSensor(coordinator, device_info, "inv_energy_input", "Inverter Energy Input",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.TOTAL_INCREASING, "mdi:import"),
        NeovoltSensor(coordinator, device_info, "total_pv_energy", "Total PV Energy",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.TOTAL_INCREASING, "mdi:solar-power-variant"),
        NeovoltSensor(coordinator, device_info, "inv_module_temp", "Inverter Module Temperature",
                     UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,
                     SensorStateClass.MEASUREMENT, "mdi:thermometer"),
        NeovoltSensor(coordinator, device_info, "pv_boost_temp", "PV Boost Temperature",
                     UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,
                     SensorStateClass.MEASUREMENT, "mdi:thermometer"),
        NeovoltSensor(coordinator, device_info, "battery_buck_boost_temp", "Battery Buck Boost Temperature",
                     UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,
                     SensorStateClass.MEASUREMENT, "mdi:thermometer"),
        NeovoltSensor(coordinator, device_info, "bus_voltage", "Bus Voltage",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:sine-wave"),
        NeovoltSensor(coordinator, device_info, "pv1_voltage", "PV1 Voltage",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:solar-panel-large"),
        NeovoltSensor(coordinator, device_info, "pv2_voltage", "PV2 Voltage",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:solar-panel-large"),
        NeovoltSensor(coordinator, device_info, "pv3_voltage", "PV3 Voltage",
                     UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                     SensorStateClass.MEASUREMENT, "mdi:solar-panel-large"),
        NeovoltSensor(coordinator, device_info, "pv1_current", "PV1 Current",
                     UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                     SensorStateClass.MEASUREMENT, "mdi:current-dc"),
        NeovoltSensor(coordinator, device_info, "pv2_current", "PV2 Current",
                     UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                     SensorStateClass.MEASUREMENT, "mdi:current-dc"),
        NeovoltSensor(coordinator, device_info, "pv3_current", "PV3 Current",
                     UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                     SensorStateClass.MEASUREMENT, "mdi:current-dc"),
        NeovoltSensor(coordinator, device_info, "pv1_power", "PV1 Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
        NeovoltSensor(coordinator, device_info, "pv2_power", "PV2 Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
        NeovoltSensor(coordinator, device_info, "pv3_power", "PV3 Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:solar-panel"),
        NeovoltSensor(coordinator, device_info, "inv_power_active", "Inverter Active Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:home-lightning-bolt"),
        NeovoltSensor(coordinator, device_info, "backup_power", "Backup Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:power-plug-off"),
        
        # AC-coupled PV
        NeovoltSensor(coordinator, device_info, "pv_inverter_energy", "PV Inverter Energy",
                     UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
                     SensorStateClass.TOTAL_INCREASING, "mdi:solar-power-variant-outline"),
        
        # Settings/Status
        NeovoltSensor(coordinator, device_info, "max_feed_to_grid", "Max Feed to Grid",
                     PERCENTAGE, None, SensorStateClass.MEASUREMENT, "mdi:transmission-tower-export"),
        NeovoltSensor(coordinator, device_info, "charging_cutoff_soc", "Charging Cutoff SOC",
                     PERCENTAGE, None, SensorStateClass.MEASUREMENT, "mdi:battery-charging-high"),
        NeovoltSensor(coordinator, device_info, "discharging_cutoff_soc", "Discharging Cutoff SOC",
                     PERCENTAGE, None, SensorStateClass.MEASUREMENT, "mdi:battery-charging-low"),
        NeovoltSensor(coordinator, device_info, "dispatch_start", "Dispatch Start",
                     None, None, None, "mdi:play-circle"),
        NeovoltSensor(coordinator, device_info, "dispatch_power", "Dispatch Power",
                     UnitOfPower.WATT, SensorDeviceClass.POWER,
                     SensorStateClass.MEASUREMENT, "mdi:flash"),
        
        # Calculated/Template Sensors
        NeovoltCalculatedSensor(coordinator, device_info, "total_house_load", "Total House Load",
                               UnitOfPower.WATT, SensorDeviceClass.POWER,
                               SensorStateClass.MEASUREMENT, "mdi:home-lightning-bolt-outline"),
        NeovoltCalculatedSensor(coordinator, device_info, "excess_grid_export", "Excess Grid Export",
                               UnitOfPower.WATT, SensorDeviceClass.POWER,
                               SensorStateClass.MEASUREMENT, "mdi:transmission-tower-export"),
        NeovoltCalculatedSensor(coordinator, device_info, "current_pv_production", "Current PV Production",
                               UnitOfPower.WATT, SensorDeviceClass.POWER,
                               SensorStateClass.MEASUREMENT, "mdi:solar-power"),
    ]

    async_add_entities(sensors)


async def async_setup_multi_inverter_sensors(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    coordinator,
) -> None:
    """Set up sensors for multi-inverter system."""
    master_device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    slave_device_infos = hass.data[DOMAIN][entry.entry_id]["slave_device_infos"]

    sensors = []

    # Create aggregated sensors on master device
    aggregated_sensors = [
        # Aggregated power sensors
        NeovoltMultiInverterSensor(coordinator, master_device_info, "total_battery_power", "Total Battery Power",
                                   UnitOfPower.WATT, SensorDeviceClass.POWER,
                                   SensorStateClass.MEASUREMENT, "mdi:battery-charging", "aggregated"),
        NeovoltMultiInverterSensor(coordinator, master_device_info, "total_pv_power", "Total PV Power",
                                   UnitOfPower.WATT, SensorDeviceClass.POWER,
                                   SensorStateClass.MEASUREMENT, "mdi:solar-power", "aggregated"),
        NeovoltMultiInverterSensor(coordinator, master_device_info, "total_battery_capacity", "Total Battery Capacity",
                                   UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY_STORAGE,
                                   SensorStateClass.MEASUREMENT, "mdi:battery", "aggregated"),
        NeovoltMultiInverterSensor(coordinator, master_device_info, "average_battery_soc", "Average Battery SOC",
                                   PERCENTAGE, SensorDeviceClass.BATTERY,
                                   SensorStateClass.MEASUREMENT, "mdi:battery", "aggregated"),
        NeovoltMultiInverterSensor(coordinator, master_device_info, "grid_power_total", "Grid Total Active Power",
                                   UnitOfPower.WATT, SensorDeviceClass.POWER,
                                   SensorStateClass.MEASUREMENT, "mdi:transmission-tower", "aggregated"),
        NeovoltMultiInverterSensor(coordinator, master_device_info, "total_house_load", "System House Load",
                                   UnitOfPower.WATT, SensorDeviceClass.POWER,
                                   SensorStateClass.MEASUREMENT, "mdi:home-lightning-bolt-outline", "aggregated"),
        NeovoltMultiInverterSensor(coordinator, master_device_info, "excess_grid_export", "Excess Grid Export",
                                   UnitOfPower.WATT, SensorDeviceClass.POWER,
                                   SensorStateClass.MEASUREMENT, "mdi:transmission-tower-export", "aggregated"),
        NeovoltMultiInverterSensor(coordinator, master_device_info, "current_pv_production", "Total PV Production",
                                   UnitOfPower.WATT, SensorDeviceClass.POWER,
                                   SensorStateClass.MEASUREMENT, "mdi:solar-power", "aggregated"),
    ]
    sensors.extend(aggregated_sensors)

    # Create master inverter sensors
    master_sensors = _create_inverter_sensors(coordinator, master_device_info, "master", "Master")
    sensors.extend(master_sensors)

    # Create slave inverter sensors
    for idx, slave_device_info in enumerate(slave_device_infos):
        slave_sensors = _create_inverter_sensors(coordinator, slave_device_info, f"slave_{idx}", f"Slave {idx + 1}")
        sensors.extend(slave_sensors)

    async_add_entities(sensors)


def _create_inverter_sensors(coordinator, device_info, data_key, inverter_name):
    """Create sensors for a single inverter in multi-inverter setup."""
    return [
        # Battery Sensors
        NeovoltMultiInverterSensor(coordinator, device_info, "battery_voltage", f"{inverter_name} Battery Voltage",
                                   UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                                   SensorStateClass.MEASUREMENT, "mdi:battery-charging", data_key),
        NeovoltMultiInverterSensor(coordinator, device_info, "battery_current", f"{inverter_name} Battery Current",
                                   UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                                   SensorStateClass.MEASUREMENT, "mdi:current-dc", data_key),
        NeovoltMultiInverterSensor(coordinator, device_info, "battery_soc", f"{inverter_name} Battery SOC",
                                   PERCENTAGE, SensorDeviceClass.BATTERY,
                                   SensorStateClass.MEASUREMENT, "mdi:battery", data_key),
        NeovoltMultiInverterSensor(coordinator, device_info, "battery_power", f"{inverter_name} Battery Power",
                                   UnitOfPower.WATT, SensorDeviceClass.POWER,
                                   SensorStateClass.MEASUREMENT, "mdi:battery-charging", data_key),
        NeovoltMultiInverterSensor(coordinator, device_info, "battery_capacity", f"{inverter_name} Battery Capacity",
                                   UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY_STORAGE,
                                   SensorStateClass.MEASUREMENT, "mdi:battery", data_key),
        NeovoltMultiInverterSensor(coordinator, device_info, "battery_soh", f"{inverter_name} Battery SOH",
                                   PERCENTAGE, None,
                                   SensorStateClass.MEASUREMENT, "mdi:battery-heart-variant", data_key),

        # PV Sensors
        NeovoltMultiInverterSensor(coordinator, device_info, "pv_power_total", f"{inverter_name} PV Total Power",
                                   UnitOfPower.WATT, SensorDeviceClass.POWER,
                                   SensorStateClass.MEASUREMENT, "mdi:solar-power", data_key),
        NeovoltMultiInverterSensor(coordinator, device_info, "pv1_voltage", f"{inverter_name} PV1 Voltage",
                                   UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                                   SensorStateClass.MEASUREMENT, "mdi:solar-panel", data_key),
        NeovoltMultiInverterSensor(coordinator, device_info, "pv1_current", f"{inverter_name} PV1 Current",
                                   UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                                   SensorStateClass.MEASUREMENT, "mdi:current-dc", data_key),
        NeovoltMultiInverterSensor(coordinator, device_info, "pv1_power", f"{inverter_name} PV1 Power",
                                   UnitOfPower.WATT, SensorDeviceClass.POWER,
                                   SensorStateClass.MEASUREMENT, "mdi:solar-panel", data_key),
        NeovoltMultiInverterSensor(coordinator, device_info, "pv2_voltage", f"{inverter_name} PV2 Voltage",
                                   UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                                   SensorStateClass.MEASUREMENT, "mdi:solar-panel", data_key),
        NeovoltMultiInverterSensor(coordinator, device_info, "pv2_current", f"{inverter_name} PV2 Current",
                                   UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                                   SensorStateClass.MEASUREMENT, "mdi:current-dc", data_key),
        NeovoltMultiInverterSensor(coordinator, device_info, "pv2_power", f"{inverter_name} PV2 Power",
                                   UnitOfPower.WATT, SensorDeviceClass.POWER,
                                   SensorStateClass.MEASUREMENT, "mdi:solar-panel", data_key),
        NeovoltMultiInverterSensor(coordinator, device_info, "pv3_voltage", f"{inverter_name} PV3 Voltage",
                                   UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                                   SensorStateClass.MEASUREMENT, "mdi:solar-panel", data_key),
        NeovoltMultiInverterSensor(coordinator, device_info, "pv3_current", f"{inverter_name} PV3 Current",
                                   UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                                   SensorStateClass.MEASUREMENT, "mdi:current-dc", data_key),
        NeovoltMultiInverterSensor(coordinator, device_info, "pv3_power", f"{inverter_name} PV3 Power",
                                   UnitOfPower.WATT, SensorDeviceClass.POWER,
                                   SensorStateClass.MEASUREMENT, "mdi:solar-panel", data_key),
        NeovoltMultiInverterSensor(coordinator, device_info, "current_pv_production", f"{inverter_name} PV Production",
                                   UnitOfPower.WATT, SensorDeviceClass.POWER,
                                   SensorStateClass.MEASUREMENT, "mdi:solar-power", data_key),

        # Inverter Sensors
        NeovoltMultiInverterSensor(coordinator, device_info, "inv_module_temp", f"{inverter_name} Module Temperature",
                                   UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,
                                   SensorStateClass.MEASUREMENT, "mdi:thermometer", data_key),
        NeovoltMultiInverterSensor(coordinator, device_info, "pv_boost_temp", f"{inverter_name} PV Boost Temperature",
                                   UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,
                                   SensorStateClass.MEASUREMENT, "mdi:thermometer", data_key),
        NeovoltMultiInverterSensor(coordinator, device_info, "battery_buck_boost_temp", f"{inverter_name} Battery Buck Boost Temp",
                                   UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,
                                   SensorStateClass.MEASUREMENT, "mdi:thermometer", data_key),
    ]


class NeovoltSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Neovolt sensor."""

    def __init__(self, coordinator, device_info, key, name, unit, device_class, 
                 state_class, icon):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"Neovolt Inverter {name}"
        self._attr_unique_id = f"neovolt_inverter_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.coordinator.data.get(self._key)


class NeovoltCalculatedSensor(CoordinatorEntity, SensorEntity):
    """Representation of a calculated Neovolt sensor."""

    def __init__(self, coordinator, device_info, key, name, unit, device_class,
                 state_class, icon):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"Neovolt Inverter {name}"
        self._attr_unique_id = f"neovolt_inverter_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the calculated state of the sensor."""
        # These sensors are pre-calculated in the coordinator
        # Just return the value from coordinator data
        return self.coordinator.data.get(self._key)


class NeovoltMultiInverterSensor(CoordinatorEntity, SensorEntity):
    """Representation of a sensor in multi-inverter setup."""

    def __init__(self, coordinator, device_info, key, name, unit, device_class,
                 state_class, icon, data_key):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._data_key = data_key  # "master", "slave_0", "slave_1", or "aggregated"
        self._attr_name = f"Neovolt {name}"
        self._attr_unique_id = f"neovolt_{data_key}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the state of the sensor from nested data structure."""
        # Multi-inverter data structure: {master: {...}, slave_0: {...}, aggregated: {...}}
        inverter_data = self.coordinator.data.get(self._data_key, {})
        return inverter_data.get(self._key)