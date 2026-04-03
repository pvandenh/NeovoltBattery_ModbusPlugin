"""The Neovolt integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    CONF_DEVICE_NAME,
    CONF_DEVICE_ROLE,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    DEVICE_ROLE_HOST,
    DEVICE_ROLE_FOLLOWER,
    DOMAIN,
    CONF_MIN_POLL_INTERVAL,
    CONF_MAX_POLL_INTERVAL,
    CONF_CONSECUTIVE_FAILURE_THRESHOLD,
    CONF_STALENESS_THRESHOLD,
    DEFAULT_MIN_POLL_INTERVAL,
    DEFAULT_MAX_POLL_INTERVAL,
    DEFAULT_CONSECUTIVE_FAILURES,
    DEFAULT_STALENESS_THRESHOLD,
    DEFAULT_MAX_CHARGE_POWER,
    DEFAULT_MAX_DISCHARGE_POWER,
    STORAGE_LAST_RESET_DATE,
    STORAGE_MIDNIGHT_BASELINE,
    STORAGE_LAST_KNOWN_TOTAL,
    STORAGE_DAILY_PRESERVED,
)
from .coordinator import NeovoltDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_FORCE_CHARGE = "force_charge"
SERVICE_FORCE_DISCHARGE = "force_discharge"
SERVICE_RETURN_TO_NORMAL = "return_to_normal"
SERVICE_SET_GRID_POWER_OFFSET = "set_grid_power_offset"
SERVICE_SET_SCHEDULE_WINDOW = "set_schedule_window"
SERVICE_SET_SCHEDULE_WINDOW_HHMM = "set_schedule_window_hhmm"
SERVICE_SET_IMMEDIATE_CONTROL = "set_immediate_control"

IMMEDIATE_MODE_OPTIONS = {
    "Auto/Normal": 0,
    "Charge": 1,
    "Discharge": 2,
    "Standby": 3,
}

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.BUTTON
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Neovolt from a config entry."""
    _LOGGER.debug(f"Setting up Neovolt integration with config: {entry.data}")

    new_data = {**entry.data}

    # Migrate existing entries without device_name (keep "inverter" for backward compatibility)
    if CONF_DEVICE_NAME not in entry.data:
        new_data[CONF_DEVICE_NAME] = "inverter"
        _LOGGER.info("Migrated existing entry to device_name='inverter'")

    # Migrate existing entries without device_role (default to host)
    if CONF_DEVICE_ROLE not in entry.data:
        new_data[CONF_DEVICE_ROLE] = DEVICE_ROLE_HOST
        _LOGGER.info("Migrated existing entry to device_role='host'")

    # Migrate existing entries without polling configuration
    if CONF_MIN_POLL_INTERVAL not in entry.data:
        new_data[CONF_MIN_POLL_INTERVAL] = DEFAULT_MIN_POLL_INTERVAL
        new_data[CONF_MAX_POLL_INTERVAL] = DEFAULT_MAX_POLL_INTERVAL
        new_data[CONF_CONSECUTIVE_FAILURE_THRESHOLD] = DEFAULT_CONSECUTIVE_FAILURES
        new_data[CONF_STALENESS_THRESHOLD] = DEFAULT_STALENESS_THRESHOLD
        _LOGGER.info("Migrated existing entry with default polling configuration")

    # Migrate existing entries without power configuration
    if CONF_MAX_CHARGE_POWER not in entry.data:
        new_data[CONF_MAX_CHARGE_POWER] = DEFAULT_MAX_CHARGE_POWER
        new_data[CONF_MAX_DISCHARGE_POWER] = DEFAULT_MAX_DISCHARGE_POWER
        _LOGGER.info("Migrated existing entry with default power configuration")

    # NOTE: We intentionally do NOT slugify device_name for existing entries here.
    # Doing so would change unique_id strings for all entities on that device,
    # causing Home Assistant to orphan the old entities and break any automations,
    # dashboards, or energy dashboard entries that reference them by entity ID.
    # Slugification is enforced only for new entries via config_flow.py.

    # Apply migrations if any
    if new_data != entry.data:
        hass.config_entries.async_update_entry(entry, data=new_data)

    # Read from new_data to ensure we have migrated values
    device_name = new_data.get(CONF_DEVICE_NAME, "inverter")
    device_role = new_data.get(CONF_DEVICE_ROLE, DEVICE_ROLE_HOST)

    coordinator = NeovoltDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    # Create device info with device name
    device_info = DeviceInfo(
        identifiers={(DOMAIN, f"{entry.data['host']}_{entry.data['slave_id']}")},
        name=f"Neovolt {device_name}",
        manufacturer="Bytewatt Technology Co., Ltd",
        model="Neovolt Hybrid Inverter",
        configuration_url=f"http://{entry.data['host']}",
    )

    # Initialize domain data if not exists
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("services_registered", False)

    # Store coordinator, device info, client, device_name, and device_role
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "device_info": device_info,
        "client": coordinator.client,
        "device_name": device_name,
        "device_role": device_role,
    }

    if not hass.data[DOMAIN]["services_registered"]:
        _register_services(hass)
        hass.data[DOMAIN]["services_registered"] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ── Link follower coordinator into host ──────────────────────────────────
    # After every entry setup (host or follower), scan all loaded Neovolt entries
    # and wire any follower coordinator reference into the host coordinator.
    # This is safe to call multiple times — it simply re-links on each load.
    _link_follower_to_host(hass)

    # Setup options update listener
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


def _link_follower_to_host(hass: HomeAssistant) -> None:
    """Wire the follower coordinator reference into the host coordinator.

    Called after every Neovolt entry loads so that, regardless of which entry
    loads first, the host always ends up with a valid follower_coordinator
    reference once both are ready.

    If more than one follower is found, the first one encountered is linked.
    If no follower is present (single-inverter setup), the host's
    follower_coordinator is set to None and combined keys are not produced.
    """
    domain_data = hass.data.get(DOMAIN, {})

    host_entry_id = None
    follower_entry_id = None

    for entry_id, entry_data in domain_data.items():
        if not isinstance(entry_data, dict):
            continue
        role = entry_data.get("device_role")
        if role == DEVICE_ROLE_HOST and host_entry_id is None:
            host_entry_id = entry_id
        elif role == DEVICE_ROLE_FOLLOWER and follower_entry_id is None:
            follower_entry_id = entry_id

    if host_entry_id is None:
        return  # Host not loaded yet

    host_coordinator = domain_data[host_entry_id]["coordinator"]

    if follower_entry_id is not None:
        follower_coordinator = domain_data[follower_entry_id]["coordinator"]
        if host_coordinator.follower_coordinator is not follower_coordinator:
            host_coordinator.follower_coordinator = follower_coordinator
            _LOGGER.info(
                f"Linked follower coordinator "
                f"({domain_data[follower_entry_id]['device_name']}) "
                f"into host coordinator "
                f"({domain_data[host_entry_id]['device_name']}) — "
                f"combined sensors active"
            )
    else:
        # No follower present — clear any stale reference
        if host_coordinator.follower_coordinator is not None:
            host_coordinator.follower_coordinator = None
            _LOGGER.info("Follower coordinator unlinked — combined sensors disabled")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Close Modbus connection before cleanup (with safety check)
        if entry.entry_id in hass.data.get(DOMAIN, {}):
            coordinator = hass.data[DOMAIN][entry.entry_id].get("coordinator")

            # Stop dynamic export manager if running
            if coordinator and hasattr(coordinator, 'dynamic_export_manager'):
                try:
                    await coordinator.dynamic_export_manager.stop()
                    _LOGGER.info("Stopped Dynamic Export manager during unload")
                except Exception as e:
                    _LOGGER.debug(f"Error stopping Dynamic Export manager (ignored): {e}")

            # Stop dynamic import manager if running
            if coordinator and hasattr(coordinator, 'dynamic_import_manager'):
                try:
                    await coordinator.dynamic_import_manager.stop()
                    _LOGGER.info("Stopped Dynamic Import manager during unload")
                except Exception as e:
                    _LOGGER.debug(f"Error stopping Dynamic Import manager (ignored): {e}")

            # Close Modbus connection
            client = hass.data[DOMAIN][entry.entry_id].get("client")
            if client:
                await hass.async_add_executor_job(client.close)
                _LOGGER.debug("Closed Modbus connection for Neovolt integration")
            hass.data[DOMAIN].pop(entry.entry_id, None)

        if DOMAIN in hass.data:
            active_entries = [k for k in hass.data[DOMAIN].keys() if k != "services_registered"]
            if not active_entries and hass.data[DOMAIN].get("services_registered"):
                for service in [
                    SERVICE_FORCE_CHARGE,
                    SERVICE_FORCE_DISCHARGE,
                    SERVICE_RETURN_TO_NORMAL,
                    SERVICE_SET_GRID_POWER_OFFSET,
                    SERVICE_SET_SCHEDULE_WINDOW,
                    SERVICE_SET_SCHEDULE_WINDOW_HHMM,
                    SERVICE_SET_IMMEDIATE_CONTROL,
                ]:
                    hass.services.async_remove(DOMAIN, service)
                hass.data[DOMAIN]["services_registered"] = False

        # Re-link after unload — if the follower was removed, clear the host's reference
        _link_follower_to_host(hass)

    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update - only reload for configuration changes, not runtime data."""
    # Runtime data keys that should NOT trigger a reload
    # These are updated by the coordinator during normal operation
    RUNTIME_KEYS = {
        STORAGE_LAST_RESET_DATE,
        STORAGE_MIDNIGHT_BASELINE,
        STORAGE_LAST_KNOWN_TOTAL,
        STORAGE_DAILY_PRESERVED,
    }

    # Get current options
    options = entry.options or {}

    # If we have options, check if only runtime keys were updated
    if options:
        # Get all keys that are NOT runtime keys (i.e., actual config keys)
        config_keys = set(options.keys()) - RUNTIME_KEYS

        # If no config keys exist (only runtime keys), skip reload
        if not config_keys:
            _LOGGER.debug(
                "Persistent data updated (runtime keys only), skipping integration reload"
            )
            return

    # Configuration keys were changed - reload integration
    _LOGGER.info("Configuration changed, reloading Neovolt integration")
    await hass.config_entries.async_reload(entry.entry_id)


def _get_target_device(hass: HomeAssistant, device_name: str | None = None) -> dict:
    """Return target Neovolt entry data, defaulting to first host device."""
    domain_data = hass.data.get(DOMAIN, {})
    candidates = [
        data for key, data in domain_data.items()
        if key != "services_registered" and data.get("device_role") == DEVICE_ROLE_HOST
    ]
    if device_name is not None:
        for data in candidates:
            if data.get("device_name") == device_name:
                return data
        raise ValueError(f"No Neovolt host with device_name={device_name}")
    if not candidates:
        raise ValueError("No Neovolt host devices loaded")
    return candidates[0]


def _register_services(hass: HomeAssistant) -> None:
    """Register Neovolt helper services."""

    async def _call_entity_service(domain: str, service: str, data: dict) -> None:
        await hass.services.async_call(domain, service, data, blocking=True)

    async def _apply_schedule_window(device_name: str, mode: str, window: int, start_hour: int, start_minute: int, end_hour: int, end_minute: int) -> None:
        prefix = f"{mode}_window_{window}"
        for suffix, value in [
            ("start_hour", start_hour),
            ("start_minute", start_minute),
            ("end_hour", end_hour),
            ("end_minute", end_minute),
        ]:
            await _call_entity_service("number", "set_value", {
                "entity_id": f"number.neovolt_{device_name}_{prefix}_{suffix}",
                "value": value,
            })

    async def handle_force_charge(call: ServiceCall) -> None:
        target = _get_target_device(hass, call.data.get("device_name"))
        device_name = target["device_name"]
        await _call_entity_service("number", "set_value", {
            "entity_id": f"number.neovolt_{device_name}_dispatch_power",
            "value": call.data.get("power_kw", 1.0),
        })
        await _call_entity_service("number", "set_value", {
            "entity_id": f"number.neovolt_{device_name}_dispatch_duration",
            "value": call.data.get("duration_minutes", 5),
        })
        await _call_entity_service("number", "set_value", {
            "entity_id": f"number.neovolt_{device_name}_dispatch_charge_soc",
            "value": call.data.get("target_soc", 100),
        })
        await _call_entity_service("select", "select_option", {
            "entity_id": f"select.neovolt_{device_name}_dispatch_mode",
            "option": "Force Charge",
        })

    async def handle_force_discharge(call: ServiceCall) -> None:
        target = _get_target_device(hass, call.data.get("device_name"))
        device_name = target["device_name"]
        await _call_entity_service("number", "set_value", {
            "entity_id": f"number.neovolt_{device_name}_dispatch_power",
            "value": call.data.get("power_kw", 1.0),
        })
        await _call_entity_service("number", "set_value", {
            "entity_id": f"number.neovolt_{device_name}_dispatch_duration",
            "value": call.data.get("duration_minutes", 5),
        })
        await _call_entity_service("number", "set_value", {
            "entity_id": f"number.neovolt_{device_name}_dispatch_discharge_soc",
            "value": call.data.get("cutoff_soc", 20),
        })
        await _call_entity_service("select", "select_option", {
            "entity_id": f"select.neovolt_{device_name}_dispatch_mode",
            "option": "Force Discharge",
        })

    async def handle_return_to_normal(call: ServiceCall) -> None:
        target = _get_target_device(hass, call.data.get("device_name"))
        device_name = target["device_name"]
        await _call_entity_service("select", "select_option", {
            "entity_id": f"select.neovolt_{device_name}_dispatch_mode",
            "option": "Normal",
        })

    async def handle_set_grid_power_offset(call: ServiceCall) -> None:
        target = _get_target_device(hass, call.data.get("device_name"))
        device_name = target["device_name"]
        await _call_entity_service("number", "set_value", {
            "entity_id": f"number.neovolt_{device_name}_grid_power_offset",
            "value": call.data.get("offset_w", 0),
        })

    async def handle_set_schedule_window(call: ServiceCall) -> None:
        target = _get_target_device(hass, call.data.get("device_name"))
        device_name = target["device_name"]
        mode = call.data["mode"]
        window = int(call.data.get("window", 1))
        start_hour = int(call.data.get("start_hour", 0))
        start_minute = int(call.data.get("start_minute", 0))
        end_hour = int(call.data.get("end_hour", 0))
        end_minute = int(call.data.get("end_minute", 0))
        await _apply_schedule_window(device_name, mode, window, start_hour, start_minute, end_hour, end_minute)

    async def handle_set_schedule_window_hhmm(call: ServiceCall) -> None:
        def parse_time(text: str) -> tuple[int, int]:
            hour_text, minute_text = text.split(":", 1)
            return int(hour_text), int(minute_text)

        target = _get_target_device(hass, call.data.get("device_name"))
        device_name = target["device_name"]
        start_hour, start_minute = parse_time(call.data["start_time"])
        end_hour, end_minute = parse_time(call.data["end_time"])
        await _apply_schedule_window(
            device_name,
            call.data["mode"],
            int(call.data.get("window", 1)),
            start_hour,
            start_minute,
            end_hour,
            end_minute,
        )

    async def handle_set_immediate_control(call: ServiceCall) -> None:
        target = _get_target_device(hass, call.data.get("device_name"))
        client = target["client"]
        coordinator = target["coordinator"]
        if "system_mode" in call.data:
            value = IMMEDIATE_MODE_OPTIONS[call.data["system_mode"]]
            await hass.async_add_executor_job(client.write_register, 0x071C, value)
            coordinator.set_optimistic_value("system_mode", value)
        if "battery_mode" in call.data:
            value = IMMEDIATE_MODE_OPTIONS[call.data["battery_mode"]]
            await hass.async_add_executor_job(client.write_register, 0x072D, value)
            coordinator.set_optimistic_value("battery_mode", value)
        if "battery_power_setpoint_w" in call.data:
            value = int(call.data["battery_power_setpoint_w"])
            if value < 0:
                value = value & 0xFFFF
            await hass.async_add_executor_job(client.write_register, 0x072E, value)
            coordinator.set_optimistic_value("battery_power_setpoint", int(call.data["battery_power_setpoint_w"]))
        if "inverter_output_power_limit_w" in call.data:
            value = int(call.data["inverter_output_power_limit_w"])
            await hass.async_add_executor_job(client.write_register, 0x072F, value)
            coordinator.set_optimistic_value("inverter_output_power_limit", value)
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_FORCE_CHARGE, handle_force_charge)
    hass.services.async_register(DOMAIN, SERVICE_FORCE_DISCHARGE, handle_force_discharge)
    hass.services.async_register(DOMAIN, SERVICE_RETURN_TO_NORMAL, handle_return_to_normal)
    hass.services.async_register(DOMAIN, SERVICE_SET_GRID_POWER_OFFSET, handle_set_grid_power_offset)
    hass.services.async_register(DOMAIN, SERVICE_SET_SCHEDULE_WINDOW, handle_set_schedule_window)
    hass.services.async_register(DOMAIN, SERVICE_SET_SCHEDULE_WINDOW_HHMM, handle_set_schedule_window_hhmm)
    hass.services.async_register(DOMAIN, SERVICE_SET_IMMEDIATE_CONTROL, handle_set_immediate_control)
