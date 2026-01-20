"""Dynamic Export Manager for Neovolt Solar Inverter.

This module manages the Dynamic Export dispatch mode, which continuously
adjusts battery discharge/charge to maintain target export power.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    CONF_MAX_DISCHARGE_POWER,
    CONF_MAX_CHARGE_POWER,
    DEFAULT_MAX_DISCHARGE_POWER,
    DEFAULT_MAX_CHARGE_POWER,
    DISPATCH_MODE_DYNAMIC_EXPORT,
    DISPATCH_MODE_POWER_WITH_SOC,
    DYNAMIC_EXPORT_DEBOUNCE_THRESHOLD,
    DYNAMIC_EXPORT_UPDATE_INTERVAL,
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
            return default

        state = entity.state
        if state in ("unknown", "unavailable", "None", None):
            return default

        return float(state)

    except (ValueError, TypeError):
        return default
    except Exception:
        return default


def soc_percent_to_register(soc_percent: float) -> int:
    """Convert SOC percentage (0-100%) to register value (0-250)."""
    register_value = int(soc_percent * 2.5)
    return max(0, min(250, register_value))


class DynamicExportManager:
    """Manages Dynamic Export mode - continuous adjustment of battery discharge/charge."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator,
        client,
        device_name: str,
    ):
        """Initialize the Dynamic Export Manager.

        Args:
            hass: Home Assistant instance
            coordinator: Data coordinator for accessing sensor data
            client: Modbus client for sending commands
            device_name: Device name for entity ID generation
        """
        self._hass = hass
        self._coordinator = coordinator
        self._client = client
        self._device_name = device_name
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_update_time: Optional[datetime] = None
        self._last_commanded_power: float = 0.0
        self._start_time: Optional[datetime] = None
        self._duration_minutes: Optional[int] = None

        # Get max charge/discharge power from config entry
        entry = None
        for config_entry in hass.config_entries.async_entries("neovolt"):
            if config_entry.data.get("device_name") == device_name:
                entry = config_entry
                break

        if entry:
            self._max_discharge_power = entry.data.get(
                CONF_MAX_DISCHARGE_POWER, DEFAULT_MAX_DISCHARGE_POWER
            )
            self._max_charge_power = entry.data.get(
                CONF_MAX_CHARGE_POWER, DEFAULT_MAX_CHARGE_POWER
            )
        else:
            self._max_discharge_power = DEFAULT_MAX_DISCHARGE_POWER
            self._max_charge_power = DEFAULT_MAX_CHARGE_POWER

        _LOGGER.info(
            f"Initialized Dynamic Export Manager for {device_name} "
            f"(max discharge: {self._max_discharge_power}kW, "
            f"max charge: {self._max_charge_power}kW)"
        )

    @property
    def is_running(self) -> bool:
        """Check if Dynamic Export mode is currently active."""
        return self._running

    async def start(self) -> None:
        """Start the Dynamic Export control loop."""
        if self._running:
            _LOGGER.warning("Dynamic Export already running")
            return

        # Get duration from number entity
        duration_minutes = int(safe_get_entity_float(
            self._hass,
            f"number.neovolt_{self._device_name}_dispatch_duration",
            120.0,
        ))

        _LOGGER.info(f"Starting Dynamic Export mode (duration: {duration_minutes} minutes)")
        self._running = True
        self._last_update_time = None
        self._last_commanded_power = 0.0
        self._start_time = dt_util.now()
        self._duration_minutes = duration_minutes

        # Start the control loop as a background task
        try:
            self._task = self._hass.async_create_task(self._control_loop())
            _LOGGER.info("Dynamic Export control loop task created successfully")
        except Exception as e:
            _LOGGER.error(f"Failed to create Dynamic Export task: {e}", exc_info=True)
            self._running = False
            raise

    async def stop(self) -> None:
        """Stop the Dynamic Export control loop."""
        if not self._running:
            return

        _LOGGER.info("Stopping Dynamic Export mode")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _control_loop(self) -> None:
        """Main control loop for Dynamic Export mode."""
        _LOGGER.info("Dynamic Export control loop started")
        
        try:
            while self._running:
                # Check if duration has expired
                if self._start_time and self._duration_minutes:
                    elapsed = (dt_util.now() - self._start_time).total_seconds() / 60.0
                    if elapsed >= self._duration_minutes:
                        _LOGGER.info(
                            f"Dynamic Export duration expired ({self._duration_minutes} minutes). "
                            "Stopping automatically."
                        )
                        await self._stop_dispatch()
                        break
                
                try:
                    _LOGGER.debug("Dynamic Export: Running update cycle")
                    await self._update_battery_power()
                except Exception as e:
                    _LOGGER.error(f"Error in Dynamic Export control loop: {e}", exc_info=True)

                # Wait for next update interval
                _LOGGER.debug(f"Dynamic Export: Sleeping for {DYNAMIC_EXPORT_UPDATE_INTERVAL}s")
                await asyncio.sleep(DYNAMIC_EXPORT_UPDATE_INTERVAL)

        except asyncio.CancelledError:
            _LOGGER.info("Dynamic Export control loop cancelled")
            raise
        finally:
            _LOGGER.info("Dynamic Export control loop ended")

    async def _update_battery_power(self) -> None:
        """Calculate and update battery power to maintain target export.
        
        Formula: Battery Power = (Target Export + House Load) - PV Production
        
        Positive power = discharge battery
        Negative power = charge battery (reduced rate)
        """
        # Get target export from number entity
        target_export_kw = safe_get_entity_float(
            self._hass,
            f"number.neovolt_{self._device_name}_dynamic_export_target",
            1.0,
        )

        # Get cutoff SOC from number entity
        soc_cutoff = int(safe_get_entity_float(
            self._hass,
            f"number.neovolt_{self._device_name}_dispatch_discharge_soc",
            10.0,
        ))

        # Get current load and PV generation from coordinator data
        data = self._coordinator.data
        current_load_w = data.get("total_house_load")
        pv_production_w = data.get("pv_power_total", 0)
        
        if pv_production_w is None:
            pv_production_w = 0
            _LOGGER.debug("PV power sensor unavailable, assuming 0W")

        # Validate we have load data
        if current_load_w is None:
            _LOGGER.warning("Cannot calculate Dynamic Export - house load unavailable")
            return

        # CORRECTED CALCULATION:
        # To export X kW while powering house load Y kW, we need total power of (X + Y) kW
        # PV provides some of this, battery provides the rest
        # Battery Power = (Target Export + House Load) - PV Production
        
        target_export_w = target_export_kw * 1000
        total_power_needed_w = target_export_w + current_load_w
        battery_power_needed_w = total_power_needed_w - pv_production_w
        battery_power_needed_kw = battery_power_needed_w / 1000.0
        
        _LOGGER.debug(
            f"Dynamic Export calculation: "
            f"Target Export={target_export_w}W, Load={current_load_w}W, "
            f"Total Needed={total_power_needed_w}W, PV={pv_production_w}W, "
            f"Battery Needed={battery_power_needed_w}W ({battery_power_needed_kw:.2f}kW)"
        )

        # Check if update is needed (debouncing)
        power_change_kw = abs(battery_power_needed_kw - self._last_commanded_power)

        # Always update if enough time has passed (stale data protection)
        now = dt_util.now()
        time_since_update = None
        if self._last_update_time:
            time_since_update = (now - self._last_update_time).total_seconds()

        # Update if:
        # 1. Power changed significantly (> debounce threshold), OR
        # 2. More than 60 seconds since last update (prevent stale commands)
        should_update = (
            power_change_kw >= DYNAMIC_EXPORT_DEBOUNCE_THRESHOLD
            or time_since_update is None
            or time_since_update >= 60
        )

        if not should_update:
            _LOGGER.debug(
                f"Skipping Dynamic Export update - change {power_change_kw:.2f}kW "
                f"below threshold {DYNAMIC_EXPORT_DEBOUNCE_THRESHOLD}kW, "
                f"last update {time_since_update:.0f}s ago"
            )
            return

        # Determine action based on battery power needed
        if battery_power_needed_kw > 0.5:
            # Need to discharge battery (positive power)
            discharge_power_kw = min(battery_power_needed_kw, self._max_discharge_power)
            
            _LOGGER.info(
                f"Dynamic Export: Discharging battery at {discharge_power_kw:.2f}kW "
                f"(Target Export={target_export_kw}kW, Load={current_load_w/1000:.2f}kW, "
                f"PV={pv_production_w/1000:.2f}kW)"
            )
            
            await self._send_discharge_command(discharge_power_kw, soc_cutoff)
            self._last_commanded_power = discharge_power_kw
            
        elif battery_power_needed_kw < -0.5:
            # Need to charge battery (negative power = excess PV)
            # Charge at the excess rate to absorb surplus and maintain target export
            charge_power_kw = min(abs(battery_power_needed_kw), self._max_charge_power)
            
            _LOGGER.info(
                f"Dynamic Export: Charging battery at {charge_power_kw:.2f}kW to absorb excess "
                f"(Target Export={target_export_kw}kW, Load={current_load_w/1000:.2f}kW, "
                f"PV={pv_production_w/1000:.2f}kW)"
            )
            
            await self._send_charge_command(charge_power_kw, 100)  # Charge to 100% SOC
            self._last_commanded_power = -charge_power_kw
            
        else:
            # Between -0.5kW and +0.5kW - within tolerance, stop dispatch
            _LOGGER.info(
                f"Dynamic Export: Battery power needed {battery_power_needed_kw:.2f}kW "
                f"is within tolerance (-0.5 to +0.5kW). "
                f"PV is covering target export. Stopping dispatch."
            )
            await self._stop_dispatch()
            return

        # Update tracking
        self._last_update_time = now

    async def _send_discharge_command(self, power_kw: float, soc_cutoff: int) -> None:
        """Send force discharge command to inverter.

        Args:
            power_kw: Discharge power in kW
            soc_cutoff: SOC cutoff percentage (0-100)
        """
        power_watts = int(power_kw * 1000)
        soc_value = soc_percent_to_register(soc_cutoff)

        # Build dispatch command for force discharge
        timeout_seconds = 600  # 10 minutes

        values = [
            1,                              # Para1: Dispatch start
            0,                              # Para2 high byte
            MODBUS_OFFSET + power_watts,    # Para2 low: DISCHARGE = 32000 + watts
            0,                              # Para3 high byte
            0,                              # Para3 low: Reactive power = 0
            DISPATCH_MODE_POWER_WITH_SOC,   # Para4: Mode 2 (SOC control)
            soc_value,                      # Para5: SOC cutoff
            0,                              # Para6 high byte
            min(timeout_seconds, 65535),    # Para6 low: Time (seconds)
            255,                            # Para7: Energy routing (default)
            0,                              # Para8: PV switch (auto)
        ]

        try:
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, values
            )

            # Update coordinator with optimistic values
            self._coordinator.set_optimistic_value("dispatch_start", 1)
            self._coordinator.set_optimistic_value("dispatch_power", power_watts)
            self._coordinator.set_optimistic_value("dispatch_mode", DISPATCH_MODE_DYNAMIC_EXPORT)

        except Exception as e:
            _LOGGER.error(f"Failed to send Dynamic Export discharge command: {e}")
            raise

    async def _send_charge_command(self, power_kw: float, soc_target: int) -> None:
        """Send force charge command to inverter.

        Args:
            power_kw: Charge power in kW
            soc_target: SOC target percentage (0-100)
        """
        power_watts = int(power_kw * 1000)
        soc_value = soc_percent_to_register(soc_target)

        # Build dispatch command for force charge
        timeout_seconds = 600  # 10 minutes

        values = [
            1,                              # Para1: Dispatch start
            0,                              # Para2 high byte
            MODBUS_OFFSET - power_watts,    # Para2 low: CHARGE = 32000 - watts
            0,                              # Para3 high byte
            0,                              # Para3 low: Reactive power = 0
            DISPATCH_MODE_POWER_WITH_SOC,   # Para4: Mode 2 (SOC control)
            soc_value,                      # Para5: SOC target
            0,                              # Para6 high byte
            min(timeout_seconds, 65535),    # Para6 low: Time (seconds)
            255,                            # Para7: Energy routing (default)
            0,                              # Para8: PV switch (auto)
        ]

        try:
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, values
            )

            # Update coordinator with optimistic values
            self._coordinator.set_optimistic_value("dispatch_start", 1)
            self._coordinator.set_optimistic_value("dispatch_power", -power_watts)
            self._coordinator.set_optimistic_value("dispatch_mode", DISPATCH_MODE_DYNAMIC_EXPORT)

        except Exception as e:
            _LOGGER.error(f"Failed to send Dynamic Export charge command: {e}")
            raise

    async def _stop_dispatch(self) -> None:
        """Stop dispatch and exit Dynamic Export mode."""
        from .const import DISPATCH_RESET_VALUES
        
        _LOGGER.info("Stopping Dynamic Export - target export achievable with current PV")
        
        try:
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, DISPATCH_RESET_VALUES
            )
            
            # Update coordinator
            self._coordinator.set_optimistic_value("dispatch_start", 0)
            self._coordinator.set_optimistic_value("dispatch_power", 0)
            self._coordinator.set_optimistic_value("dispatch_mode", 0)
            
            # Stop the control loop
            await self.stop()
            
        except Exception as e:
            _LOGGER.error(f"Failed to stop Dynamic Export dispatch: {e}")