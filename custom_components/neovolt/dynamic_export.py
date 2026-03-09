"""Dynamic Export / Import Manager for Neovolt Solar Inverter.

This module manages two continuous dispatch modes:

  DynamicExportManager — discharges the battery to maintain a target grid
      export power level.  Battery power = (Target Export + House Load) − PV.

  DynamicImportManager — charges the battery from the grid to maintain a
      target grid import power level.  Battery power =
      (PV − House Load) + Target Import  (negative = charge).
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
    DISPATCH_MODE_DYNAMIC_IMPORT,
    DISPATCH_MODE_POWER_WITH_SOC,
    DYNAMIC_EXPORT_DEBOUNCE_THRESHOLD,
    DYNAMIC_EXPORT_MIN_POWER,
    DYNAMIC_EXPORT_UPDATE_INTERVAL,
    MODBUS_OFFSET,
    SOC_CONVERSION_FACTOR,
    MAX_SOC_REGISTER,
    MIN_SOC_REGISTER,
    COMBINED_BATTERY_SOC,
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
    """
    Convert SOC percentage (0-100%) to register value (0-255).
    
    FIXED: Uses correct conversion factor and full 0-255 range.
    Formula: register_value = soc_percent × 2.55
    Examples: 0% = 0, 50% = 128, 100% = 255
    """
    register_value = round(soc_percent * SOC_CONVERSION_FACTOR)
    return max(MIN_SOC_REGISTER, min(MAX_SOC_REGISTER, register_value))


# ---------------------------------------------------------------------------
# Dynamic Export Manager
# ---------------------------------------------------------------------------

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
                        await self._stop_and_reset_dispatch()
                        break
                
                try:
                    _LOGGER.debug("Dynamic Export: Running update cycle")
                    await self._update_battery_power()
                except Exception as e:
                    _LOGGER.error(f"Error in Dynamic Export control loop: {e}", exc_info=True)

                # Wait for next update interval
                await asyncio.sleep(DYNAMIC_EXPORT_UPDATE_INTERVAL)
                
        except asyncio.CancelledError:
            _LOGGER.info("Dynamic Export control loop cancelled")
            raise
        except Exception as e:
            _LOGGER.error(f"Unexpected error in Dynamic Export control loop: {e}", exc_info=True)
            self._running = False

    async def _update_battery_power(self) -> None:
        """
        Calculate required battery power and send appropriate command.

        GRID-BASED CALCULATION:
        The grid meter provides a complete, system-wide view of net power flow,
        incorporating all inverters (including any follower not visible via Modbus).
        This makes house load and PV measurements unnecessary for control purposes.

        Sign convention for grid_power_total (from register 0x0021H):
            positive → importing from grid
            negative → exporting to grid

        To reach a target export level T (positive kW):
            current_export  = -grid_power_total   (negate: export is positive here)
            error           = T - current_export
            battery_discharge_needed = error
              > 0 → discharge more (or charge less) to increase export
              < 0 → charge more (or discharge less) to reduce export / absorb excess

        Equivalent form used below:
            battery_power_needed = target_export_W + grid_power_total_W
        """
        # Get current system state from coordinator.
        data = self._coordinator.data

        # Get target export from number entity
        target_export_kw = safe_get_entity_float(
            self._hass,
            f"number.neovolt_{self._device_name}_dynamic_mode_power_target",
            1.0,
        )

        # Get discharge SOC cutoff
        soc_cutoff = int(safe_get_entity_float(
            self._hass,
            f"number.neovolt_{self._device_name}_dispatch_discharge_soc",
            10.0,
        ))

        # ── SOC guard — use combined SOC when follower is linked ─────────────
        # Falls back to host battery_soc on single-inverter setups.
        current_soc = data.get(COMBINED_BATTERY_SOC) or data.get("battery_soc")
        if current_soc is not None and current_soc <= soc_cutoff:
            _LOGGER.info(
                f"Dynamic Export: SOC {current_soc:.1f}% at or below "
                f"cutoff {soc_cutoff}% — sending standby command"
            )
            await self._send_standby_command()
            self._last_commanded_power = 0.0
            self._last_update_time = dt_util.now()
            return

        # ── Grid power (signed, W) ────────────────────────────────────────────
        # grid_power_total: positive = importing, negative = exporting.
        # This is the authoritative system-wide measurement — it accounts for
        # all inverters, house load and PV without needing to read them separately.
        grid_power_w = data.get("grid_power_total")
        if grid_power_w is None:
            _LOGGER.warning("Cannot calculate Dynamic Export — grid_power_total unavailable")
            return

        # ── Core calculation ──────────────────────────────────────────────────
        # battery_power_needed = target_export_W + grid_power_total_W
        #
        # Worked examples (target export = 200 W):
        #   Currently exporting 50 W  → grid = -50 W  → needed = 200 + (-50) = +150 W discharge
        #   Currently importing 100 W → grid = +100 W → needed = 200 + 100  = +300 W discharge
        #   Currently exporting 300 W → grid = -300 W → needed = 200 + (-300) = -100 W charge
        target_export_w = target_export_kw * 1000
        battery_power_needed_w = target_export_w + grid_power_w
        battery_power_needed_kw = battery_power_needed_w / 1000.0

        current_export_w = -grid_power_w  # Positive = currently exporting
        _LOGGER.debug(
            f"Dynamic Export calculation (grid-based): "
            f"Target Export={target_export_w:.0f}W, "
            f"Grid={grid_power_w:.0f}W (export={current_export_w:.0f}W), "
            f"Battery Needed={battery_power_needed_w:.0f}W ({battery_power_needed_kw:.2f}kW)"
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
        if battery_power_needed_kw > DYNAMIC_EXPORT_MIN_POWER:
            # Need to discharge battery (positive power)
            discharge_power_kw = min(battery_power_needed_kw, self._max_discharge_power)
            
            _LOGGER.info(
                f"Dynamic Export: Discharging battery at {discharge_power_kw:.2f}kW "
                f"(Target Export={target_export_kw}kW, "
                f"Grid={grid_power_w/1000:.2f}kW, Current Export={current_export_w/1000:.2f}kW)"
            )
            
            await self._send_discharge_command(discharge_power_kw, soc_cutoff)
            self._last_commanded_power = discharge_power_kw
            
        elif battery_power_needed_kw < -DYNAMIC_EXPORT_MIN_POWER:
            # Need to charge battery (negative power = excess PV)
            # Charge at the excess rate to absorb surplus and maintain target export
            charge_power_kw = min(abs(battery_power_needed_kw), self._max_charge_power)
            
            _LOGGER.info(
                f"Dynamic Export: Charging battery at {charge_power_kw:.2f}kW to absorb excess "
                f"(Target Export={target_export_kw}kW, "
                f"Grid={grid_power_w/1000:.2f}kW, Current Export={current_export_w/1000:.2f}kW)"
            )
            
            await self._send_charge_command(charge_power_kw, 100)  # Charge to 100% SOC
            self._last_commanded_power = -charge_power_kw
            
        else:
            # Between -0.5kW and +0.5kW - within tolerance, send standby command
            # but keep Dynamic Export mode running
            _LOGGER.info(
                f"Dynamic Export: Battery power needed {battery_power_needed_kw:.2f}kW "
                f"is within tolerance (-0.5 to +0.5kW). "
                f"PV is covering target export. Sending standby command."
            )
            await self._send_standby_command()
            self._last_commanded_power = 0.0

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
            soc_value,                      # Para5: SOC cutoff (0-255 range)
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
            soc_value,                      # Para5: SOC target (0-255 range)
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

    async def _send_standby_command(self) -> None:
        """Send standby command (dispatch start=1 but power=0) to keep mode active."""
        try:
            # Keep dispatch active but with 0W command
            values = [
                1,                              # Para1: Dispatch start (keep active)
                0,                              # Para2 high byte
                MODBUS_OFFSET,                  # Para2 low: 0W (32000 + 0)
                0,                              # Para3 high byte
                0,                              # Para3 low: Reactive power = 0
                DISPATCH_MODE_POWER_WITH_SOC,   # Para4: Mode 2
                0,                              # Para5: SOC (not used for 0W)
                0,                              # Para6 high byte
                600,                            # Para6 low: 10 minute timeout
                255,                            # Para7: Energy routing (default)
                0,                              # Para8: PV switch (auto)
            ]

            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, values
            )

            # Update coordinator with optimistic values
            self._coordinator.set_optimistic_value("dispatch_start", 1)
            self._coordinator.set_optimistic_value("dispatch_power", 0)
            self._coordinator.set_optimistic_value("dispatch_mode", DISPATCH_MODE_DYNAMIC_EXPORT)

        except Exception as e:
            _LOGGER.error(f"Failed to send Dynamic Export standby command: {e}")

    async def _stop_and_reset_dispatch(self) -> None:
        """Stop dispatch, reset to Normal mode, and exit Dynamic Export."""
        from .const import DISPATCH_RESET_VALUES
        
        _LOGGER.info("Dynamic Export duration expired - resetting to Normal mode")
        
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


# ---------------------------------------------------------------------------
# Dynamic Import Manager
# ---------------------------------------------------------------------------

class DynamicImportManager:
    """Manages Dynamic Import mode — charges battery to maintain a target grid import level.

    Calculation:
        Grid power = PV − Load − Battery  (positive = export, negative = import)
        To target a specific import level T (positive = importing from grid):
            Battery charge needed = (PV − Load) + T
        When battery_charge_needed is positive the battery should charge.
        When battery_charge_needed is negative (excess PV beyond import target)
        the battery should discharge to absorb excess and keep import at target.

    The Dispatch Charge Target SOC number entity is used as the charge SOC ceiling.
    The Dispatch Duration number entity controls how long the mode runs.
    The Dynamic Mode Power Target number entity sets the desired import level.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator,
        client,
        device_name: str,
    ):
        """Initialize the Dynamic Import Manager."""
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
            f"Initialized Dynamic Import Manager for {device_name} "
            f"(max charge: {self._max_charge_power}kW, "
            f"max discharge: {self._max_discharge_power}kW)"
        )

    @property
    def is_running(self) -> bool:
        """Check if Dynamic Import mode is currently active."""
        return self._running

    async def start(self) -> None:
        """Start the Dynamic Import control loop."""
        if self._running:
            _LOGGER.warning("Dynamic Import already running")
            return

        duration_minutes = int(safe_get_entity_float(
            self._hass,
            f"number.neovolt_{self._device_name}_dispatch_duration",
            120.0,
        ))

        _LOGGER.info(f"Starting Dynamic Import mode (duration: {duration_minutes} minutes)")
        self._running = True
        self._last_update_time = None
        self._last_commanded_power = 0.0
        self._start_time = dt_util.now()
        self._duration_minutes = duration_minutes

        try:
            self._task = self._hass.async_create_task(self._control_loop())
            _LOGGER.info("Dynamic Import control loop task created successfully")
        except Exception as e:
            _LOGGER.error(f"Failed to create Dynamic Import task: {e}", exc_info=True)
            self._running = False
            raise

    async def stop(self) -> None:
        """Stop the Dynamic Import control loop."""
        if not self._running:
            return

        _LOGGER.info("Stopping Dynamic Import mode")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _control_loop(self) -> None:
        """Main control loop for Dynamic Import mode."""
        _LOGGER.info("Dynamic Import control loop started")

        try:
            while self._running:
                # Check if duration has expired
                if self._start_time and self._duration_minutes:
                    elapsed = (dt_util.now() - self._start_time).total_seconds() / 60.0
                    if elapsed >= self._duration_minutes:
                        _LOGGER.info(
                            f"Dynamic Import duration expired ({self._duration_minutes} minutes). "
                            "Stopping automatically."
                        )
                        await self._stop_and_reset_dispatch()
                        break

                try:
                    _LOGGER.debug("Dynamic Import: Running update cycle")
                    await self._update_battery_power()
                except Exception as e:
                    _LOGGER.error(f"Error in Dynamic Import control loop: {e}", exc_info=True)

                await asyncio.sleep(DYNAMIC_EXPORT_UPDATE_INTERVAL)

        except asyncio.CancelledError:
            _LOGGER.info("Dynamic Import control loop cancelled")
            raise
        except Exception as e:
            _LOGGER.error(f"Unexpected error in Dynamic Import control loop: {e}", exc_info=True)
            self._running = False

    async def _update_battery_power(self) -> None:
        """Calculate required battery charge/discharge and send command.

        GRID-BASED CALCULATION:
        The grid meter provides a complete, system-wide view of net power flow,
        incorporating all inverters (including any follower not visible via Modbus).
        This makes house load and PV measurements unnecessary for control purposes.

        Sign convention for grid_power_total (from register 0x0021H):
            positive → importing from grid
            negative → exporting to grid

        To reach a target import level T (positive kW):
            error = T - grid_power_total
            battery_charge_needed = error
              > 0 → charge more (grid is not importing enough, battery must absorb more)
              < 0 → discharge more (grid is importing too much, battery should offset it)

        Worked examples (target import = 500 W):
            Currently importing 200 W → grid = +200 W → needed = 500 - 200 = +300 W charge
            Currently importing 700 W → grid = +700 W → needed = 500 - 700 = -200 W discharge
            Currently exporting 100 W → grid = -100 W → needed = 500 - (-100) = +600 W charge
        """
        data = self._coordinator.data

        # Get target import power (kW) from the shared number entity
        target_import_kw = safe_get_entity_float(
            self._hass,
            f"number.neovolt_{self._device_name}_dynamic_mode_power_target",
            1.0,
        )

        # Get charge SOC ceiling from the Dispatch Charge Target SOC entity
        soc_target = int(safe_get_entity_float(
            self._hass,
            f"number.neovolt_{self._device_name}_dispatch_charge_soc",
            100.0,
        ))

        # ── SOC guard — stop charging if battery is at or above target SOC ──
        current_soc = data.get(COMBINED_BATTERY_SOC) or data.get("battery_soc")
        if current_soc is not None and current_soc >= soc_target:
            _LOGGER.info(
                f"Dynamic Import: SOC {current_soc:.1f}% at or above "
                f"target {soc_target}% — sending standby command"
            )
            await self._send_standby_command()
            self._last_commanded_power = 0.0
            self._last_update_time = dt_util.now()
            return

        # ── Grid power (signed, W) ────────────────────────────────────────────
        # grid_power_total: positive = importing, negative = exporting.
        # This is the authoritative system-wide measurement — it accounts for
        # all inverters, house load and PV without needing to read them separately.
        grid_power_w = data.get("grid_power_total")
        if grid_power_w is None:
            _LOGGER.warning("Cannot calculate Dynamic Import — grid_power_total unavailable")
            return

        # ── Core calculation ─────────────────────────────────────────────────
        # battery_charge_needed = target_import_W - grid_power_total_W
        target_import_w = target_import_kw * 1000
        battery_charge_needed_w = target_import_w - grid_power_w
        battery_charge_needed_kw = battery_charge_needed_w / 1000.0

        _LOGGER.debug(
            f"Dynamic Import calculation (grid-based): "
            f"Target Import={target_import_w:.0f}W, "
            f"Grid={grid_power_w:.0f}W, "
            f"Battery Charge Needed={battery_charge_needed_w:.0f}W "
            f"({battery_charge_needed_kw:.2f}kW)"
        )

        # ── Debounce check ───────────────────────────────────────────────────
        power_change_kw = abs(battery_charge_needed_kw - self._last_commanded_power)
        now = dt_util.now()
        time_since_update = None
        if self._last_update_time:
            time_since_update = (now - self._last_update_time).total_seconds()

        should_update = (
            power_change_kw >= DYNAMIC_EXPORT_DEBOUNCE_THRESHOLD
            or time_since_update is None
            or time_since_update >= 60
        )

        if not should_update:
            _LOGGER.debug(
                f"Skipping Dynamic Import update - change {power_change_kw:.2f}kW "
                f"below threshold {DYNAMIC_EXPORT_DEBOUNCE_THRESHOLD}kW, "
                f"last update {time_since_update:.0f}s ago"
            )
            return

        # ── Send command ─────────────────────────────────────────────────────
        if battery_charge_needed_kw > DYNAMIC_EXPORT_MIN_POWER:
            # Charge battery to achieve target import
            charge_power_kw = min(battery_charge_needed_kw, self._max_charge_power)

            _LOGGER.info(
                f"Dynamic Import: Charging battery at {charge_power_kw:.2f}kW "
                f"(Target Import={target_import_kw}kW, Grid={grid_power_w/1000:.2f}kW)"
            )

            await self._send_charge_command(charge_power_kw, soc_target)
            self._last_commanded_power = charge_power_kw

        elif battery_charge_needed_kw < -DYNAMIC_EXPORT_MIN_POWER:
            # PV surplus exceeds target import — discharge to prevent unintended export
            discharge_power_kw = min(abs(battery_charge_needed_kw), self._max_discharge_power)

            _LOGGER.info(
                f"Dynamic Import: Discharging battery at {discharge_power_kw:.2f}kW "
                f"to reduce grid import to target "
                f"(Target Import={target_import_kw}kW, Grid={grid_power_w/1000:.2f}kW)"
            )

            # Use dispatch_discharge_soc as the floor for this discharge
            soc_floor = int(safe_get_entity_float(
                self._hass,
                f"number.neovolt_{self._device_name}_dispatch_discharge_soc",
                10.0,
            ))
            await self._send_discharge_command(discharge_power_kw, soc_floor)
            self._last_commanded_power = -discharge_power_kw

        else:
            # Within tolerance — standby
            _LOGGER.info(
                f"Dynamic Import: Battery power needed {battery_charge_needed_kw:.2f}kW "
                f"is within tolerance. Sending standby command."
            )
            await self._send_standby_command()
            self._last_commanded_power = 0.0

        self._last_update_time = now

    async def _send_charge_command(self, power_kw: float, soc_target: int) -> None:
        """Send force charge command to inverter."""
        power_watts = int(power_kw * 1000)
        soc_value = soc_percent_to_register(soc_target)
        timeout_seconds = 600  # 10 minutes

        values = [
            1,                              # Para1: Dispatch start
            0,                              # Para2 high byte
            MODBUS_OFFSET - power_watts,    # Para2 low: CHARGE = 32000 - watts
            0,                              # Para3 high byte
            0,                              # Para3 low: Reactive power = 0
            DISPATCH_MODE_POWER_WITH_SOC,   # Para4: Mode 2 (SOC control)
            soc_value,                      # Para5: SOC target (0-255 range)
            0,                              # Para6 high byte
            min(timeout_seconds, 65535),    # Para6 low: Time (seconds)
            255,                            # Para7: Energy routing (default)
            0,                              # Para8: PV switch (auto)
        ]

        try:
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, values
            )
            self._coordinator.set_optimistic_value("dispatch_start", 1)
            self._coordinator.set_optimistic_value("dispatch_power", -power_watts)
            self._coordinator.set_optimistic_value("dispatch_mode", DISPATCH_MODE_DYNAMIC_IMPORT)
        except Exception as e:
            _LOGGER.error(f"Failed to send Dynamic Import charge command: {e}")
            raise

    async def _send_discharge_command(self, power_kw: float, soc_cutoff: int) -> None:
        """Send force discharge command to counteract PV surplus."""
        power_watts = int(power_kw * 1000)
        soc_value = soc_percent_to_register(soc_cutoff)
        timeout_seconds = 600

        values = [
            1,                              # Para1: Dispatch start
            0,                              # Para2 high byte
            MODBUS_OFFSET + power_watts,    # Para2 low: DISCHARGE = 32000 + watts
            0,                              # Para3 high byte
            0,                              # Para3 low: Reactive power = 0
            DISPATCH_MODE_POWER_WITH_SOC,   # Para4: Mode 2 (SOC control)
            soc_value,                      # Para5: SOC cutoff (0-255 range)
            0,                              # Para6 high byte
            min(timeout_seconds, 65535),    # Para6 low: Time (seconds)
            255,                            # Para7: Energy routing (default)
            0,                              # Para8: PV switch (auto)
        ]

        try:
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, values
            )
            self._coordinator.set_optimistic_value("dispatch_start", 1)
            self._coordinator.set_optimistic_value("dispatch_power", power_watts)
            self._coordinator.set_optimistic_value("dispatch_mode", DISPATCH_MODE_DYNAMIC_IMPORT)
        except Exception as e:
            _LOGGER.error(f"Failed to send Dynamic Import discharge command: {e}")
            raise

    async def _send_standby_command(self) -> None:
        """Send standby command to keep mode active at 0W."""
        try:
            values = [
                1,                              # Para1: Dispatch start (keep active)
                0,                              # Para2 high byte
                MODBUS_OFFSET,                  # Para2 low: 0W
                0,                              # Para3 high byte
                0,                              # Para3 low: Reactive power = 0
                DISPATCH_MODE_POWER_WITH_SOC,   # Para4: Mode 2
                0,                              # Para5: SOC (not used for 0W)
                0,                              # Para6 high byte
                600,                            # Para6 low: 10 minute timeout
                255,                            # Para7: Energy routing (default)
                0,                              # Para8: PV switch (auto)
            ]

            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, values
            )
            self._coordinator.set_optimistic_value("dispatch_start", 1)
            self._coordinator.set_optimistic_value("dispatch_power", 0)
            self._coordinator.set_optimistic_value("dispatch_mode", DISPATCH_MODE_DYNAMIC_IMPORT)
        except Exception as e:
            _LOGGER.error(f"Failed to send Dynamic Import standby command: {e}")

    async def _stop_and_reset_dispatch(self) -> None:
        """Stop dispatch, reset to Normal mode, and exit Dynamic Import."""
        from .const import DISPATCH_RESET_VALUES

        _LOGGER.info("Dynamic Import duration expired - resetting to Normal mode")

        try:
            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, DISPATCH_RESET_VALUES
            )
            self._coordinator.set_optimistic_value("dispatch_start", 0)
            self._coordinator.set_optimistic_value("dispatch_power", 0)
            self._coordinator.set_optimistic_value("dispatch_mode", 0)
            await self.stop()
        except Exception as e:
            _LOGGER.error(f"Failed to stop Dynamic Import dispatch: {e}")