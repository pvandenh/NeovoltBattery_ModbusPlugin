"""The Neovolt integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DOMAIN,
    CONF_MASTER,
    CONF_SLAVES,
    CONF_NUM_INVERTERS,
    CONF_INVERTER_NAME,
)
from .coordinator import NeovoltDataUpdateCoordinator
from .modbus_client import NeovoltModbusClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR, 
    Platform.SWITCH, 
    Platform.NUMBER, 
    Platform.SELECT, 
    Platform.BUTTON
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Neovolt from a config entry."""
    _LOGGER.debug(f"Setting up Neovolt integration with config: {entry.data}")

    # Initialize domain data if not exists
    hass.data.setdefault(DOMAIN, {})

    # Check if this is a multi-inverter setup
    is_multi_inverter = CONF_MASTER in entry.data

    if is_multi_inverter:
        # Multi-inverter setup
        num_inverters = entry.data[CONF_NUM_INVERTERS]
        master_config = entry.data[CONF_MASTER]
        slaves_config = entry.data[CONF_SLAVES]

        _LOGGER.info(f"Setting up multi-inverter system with {num_inverters} inverters")

        # Create Modbus clients for all inverters
        master_client = NeovoltModbusClient(
            master_config["host"],
            master_config["port"],
            master_config["slave_id"]
        )

        slave_clients = [
            NeovoltModbusClient(
                slave_config["host"],
                slave_config["port"],
                slave_config["slave_id"]
            )
            for slave_config in slaves_config
        ]

        all_clients = [master_client] + slave_clients

        # Create coordinator with all clients
        coordinator = NeovoltDataUpdateCoordinator(
            hass, entry, clients=all_clients, is_multi_inverter=True
        )
        await coordinator.async_config_entry_first_refresh()

        # Create device info for master
        master_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"master_{master_config['host']}_{master_config['slave_id']}")},
            name=master_config.get(CONF_INVERTER_NAME, "Master Inverter"),
            manufacturer="Bytewatt Technology Co., Ltd",
            model="Neovolt Hybrid Inverter (Master)",
            sw_version=coordinator.data.get("master", {}).get("ems_version"),
            configuration_url=f"http://{master_config['host']}",
        )

        # Create device info for each slave
        slave_device_infos = []
        for idx, slave_config in enumerate(slaves_config):
            slave_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"slave_{idx}_{slave_config['host']}_{slave_config['slave_id']}")},
                name=slave_config.get(CONF_INVERTER_NAME, f"Slave Inverter {idx + 1}"),
                manufacturer="Bytewatt Technology Co., Ltd",
                model="Neovolt Hybrid Inverter (Slave)",
                sw_version=coordinator.data.get(f"slave_{idx}", {}).get("ems_version"),
                configuration_url=f"http://{slave_config['host']}",
                via_device=(DOMAIN, f"master_{master_config['host']}_{master_config['slave_id']}"),
            )
            slave_device_infos.append(slave_device_info)

        # Store coordinator and device info
        hass.data[DOMAIN][entry.entry_id] = {
            "coordinator": coordinator,
            "device_info": master_device_info,
            "slave_device_infos": slave_device_infos,
            "clients": all_clients,
            "is_multi_inverter": True,
        }

    else:
        # Single inverter setup (backwards compatibility)
        coordinator = NeovoltDataUpdateCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()

        # Create device info
        device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.data['host']}_{entry.data['slave_id']}")},
            name=entry.data.get(CONF_INVERTER_NAME, "Neovolt Inverter"),
            manufacturer="Bytewatt Technology Co., Ltd",
            model="Neovolt Hybrid Inverter",
            sw_version=coordinator.data.get("ems_version"),
            configuration_url=f"http://{entry.data['host']}",
        )

        # Store coordinator and device info
        hass.data[DOMAIN][entry.entry_id] = {
            "coordinator": coordinator,
            "device_info": device_info,
            "client": coordinator.client,
            "is_multi_inverter": False,
        }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Setup options update listener
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Close Modbus connection(s) before cleanup
        entry_data = hass.data[DOMAIN][entry.entry_id]

        if entry_data.get("is_multi_inverter", False):
            # Close all clients in multi-inverter setup
            clients = entry_data["clients"]
            for client in clients:
                await hass.async_add_executor_job(client.close)
            _LOGGER.debug(f"Closed {len(clients)} Modbus connections for multi-inverter setup")
        else:
            # Single client
            client = entry_data["client"]
            await hass.async_add_executor_job(client.close)
            _LOGGER.debug("Closed Modbus connection for Neovolt integration")

        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)