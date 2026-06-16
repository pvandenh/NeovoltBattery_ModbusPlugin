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
    DISPATCH_MODE_DYNAMIC_SOC_EXPORT,
    DISPATCH_MODE_POWER_WITH_SOC,
    DYNAMIC_EXPORT_MIN_POWER,
    DYNAMIC_EXPORT_UPDATE_INTERVAL,
    DYNAMIC_EXPORT_SETTLE_SECONDS,
    DYNAMIC_EXPORT_MAX_STEP_KW,
    DYNAMIC_MODE_FAST_POLL_INTERVAL,
    DYNAMIC_SOC_EXPORT_DEFAULT_TARGET_SOC,
    DYNAMIC_SOC_EXPORT_DEFAULT_BUFFER,
    MODBUS_OFFSET,
    SOC_CONVERSION_FACTOR,
    MAX_SOC_REGISTER,
    MIN_SOC_REGISTER,
    COMBINED_BATTERY_SOC,
    COMBINED_BATTERY_POWER,
    COMBINED_BATTERY_CAPACITY,
    COMBINED_HOUSE_LOAD,
)

_LOGGER = logging.getLogger(__name__)

# Imported here (not at top-level) to avoid circular import at module load time.
# Both managers call this at runtime, well after all modules are initialised.
def _safe_get_by_unique_id(hass: HomeAssistant, unique_id: str, default: float) -> float:
    """Look up a number entity by unique_id and return its float value.

    Delegates to select.safe_get_by_unique_id which uses the entity registry
    rather than a generated entity_id string, making it robust to any device
    naming or slugification the user may have chosen.
    """
    from .select import safe_get_by_unique_id
    value, _, _ = safe_get_by_unique_id(hass, unique_id, default)
    return value


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

    # Internal tracking mode tag stamped onto coordinator data for current_option detection.
    # Subclasses (e.g. DynamicSOCExportManager) override to distinguish themselves while
    # reusing the underlying control loop and command builders.
    _dispatch_mode_tag = DISPATCH_MODE_DYNAMIC_EXPORT

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
        self._last_grid_power_w: Optional[float] = None  # Last grid reading used for debounce
        self._last_commanded_power_kw: float = 0.0       # Last power sent — used for slew limiting
        self._start_time: Optional[datetime] = None
        self._duration_minutes: Optional[int] = None
        # Hardware timer written to Para6 on every command — set to the full
        # user-configured duration on start() so the inverter cannot self-reset
        # between HA update cycles even if several cycles are missed.
        self._timeout_seconds: int = 600

        # Get max charge/discharge power directly from the coordinator's own config
        # entry — this is always correct and avoids the previous name-matching loop
        # which silently fell back to 5 kW defaults whenever device_name didn't
        # match exactly (e.g. slugified vs. un-slugified names, migrated entries).
        entry = coordinator.config_entry
        self._max_discharge_power = entry.data.get(
            CONF_MAX_DISCHARGE_POWER, DEFAULT_MAX_DISCHARGE_POWER
        )
        self._max_charge_power = entry.data.get(
            CONF_MAX_CHARGE_POWER, DEFAULT_MAX_CHARGE_POWER
        )

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

        # Get duration from number entity (unique_id lookup — robust to device naming)
        duration_minutes = int(_safe_get_by_unique_id(
            self._hass,
            f"neovolt_{self._device_name}_dispatch_duration",
            120.0,
        ))

        _LOGGER.info(f"Starting Dynamic Export mode (duration: {duration_minutes} minutes)")
        self._running = True
        self._last_update_time = None
        self._last_grid_power_w = None
        self._last_commanded_power_kw = 0.0
        self._start_time = dt_util.now()
        self._duration_minutes = duration_minutes
        # Set hardware timer to full duration so the inverter cannot self-reset
        # between HA update cycles even if several consecutive cycles are missed.
        self._timeout_seconds = min(duration_minutes * 60, 65535)

        # Pin grid and battery blocks to fast poll rate for the duration of this mode
        self._coordinator.polling_manager.pin_block_interval("grid", DYNAMIC_MODE_FAST_POLL_INTERVAL)
        self._coordinator.polling_manager.pin_block_interval("battery", DYNAMIC_MODE_FAST_POLL_INTERVAL)
        _LOGGER.info(
            f"Dynamic Export: pinned grid+battery blocks to {DYNAMIC_MODE_FAST_POLL_INTERVAL}s poll interval"
        )

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

        # Release the fast-poll pin so grid+battery return to adaptive control
        self._coordinator.polling_manager.unpin_block_interval("grid")
        self._coordinator.polling_manager.unpin_block_interval("battery")
        _LOGGER.info("Dynamic Export: released grid+battery poll interval pins")

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

        Sign convention for grid_power_total (register 0x0021H):
            positive → importing from grid
            negative → exporting to grid

        To reach a target export level T (positive W):
            battery_power_needed = target_export_W + grid_power_total_W

        Worked examples (target = 200 W):
            Grid = -50 W  (exporting 50 W)  → needed = 200 + (-50) = +150 W discharge
            Grid = +100 W (importing 100 W) → needed = 200 + 100   = +300 W discharge
            Grid = -300 W (exporting 300 W) → needed = 200 + (-300) = -100 W charge

        DEBOUNCE:
        We debounce on the *grid power reading* (W), not the battery command.
        This prevents the closed-loop from oscillating: once a command is sent and
        the battery responds, the grid reading stabilises near target and subsequent
        cycles correctly see only a small change and skip redundant commands.
        """
        data = self._coordinator.data

        # Get target export — subclasses override _get_target_export_kw() to compute
        # this dynamically (e.g. SOC-paced smooth rate). Base class reads the entity.
        target_export_kw = self._get_target_export_kw()

        # Get discharge SOC cutoff (unique_id lookup — robust to device naming)
        soc_cutoff = int(_safe_get_by_unique_id(
            self._hass,
            f"neovolt_{self._device_name}_dispatch_discharge_soc",
            10.0,
        ))

        # ── Grid power (signed, W) ────────────────────────────────────────────
        # Authoritative system-wide net power — incorporates all inverters,
        # all house loads and all PV without needing to read them individually.
        grid_power_w = data.get("grid_power_total")
        if grid_power_w is None:
            _LOGGER.warning("Cannot calculate Dynamic Export — grid_power_total unavailable")
            return

        # ── Core calculation ──────────────────────────────────────────────────
        # Two methods depending on whether follower battery data is available:
        #
        # METHOD A — Host+Follower (COMBINED_BATTERY_POWER present):
        #   Uses actual combined battery output as baseline, applies grid error as delta.
        #   new_cmd = current_battery_power + grid_error
        #   More accurate because it knows exactly what the batteries are doing.
        #
        # METHOD B — Host only (no follower data):
        #   Uses last commanded power as baseline, applies grid error as delta.
        #   new_cmd = last_commanded + clamp(grid_error, ±MAX_STEP)
        #   Safe because it never jumps more than MAX_STEP per cycle regardless
        #   of what the inverter actually did with the previous command.
        #
        # Both methods: grid_error = grid_power_w + target_export_w
        #   positive error → need more discharge
        #   negative error → exporting too much, ease off
        #
        # Sign convention: grid positive = importing, negative = exporting.
        target_export_w = target_export_kw * 1000
        grid_error_w = grid_power_w + target_export_w
        grid_error_kw = grid_error_w / 1000.0
        current_export_w = -grid_power_w

        combined_battery_w = data.get(COMBINED_BATTERY_POWER)
        has_follower = (
            self._coordinator.follower_coordinator is not None
            and bool(self._coordinator.follower_coordinator.data)
        )
        if has_follower and combined_battery_w is not None:
            # Method A: follower data available — use actual battery power as baseline
            battery_power_needed_kw = (combined_battery_w + grid_error_w) / 1000.0
            _LOGGER.debug(
                f"Dynamic Export [Method A — host+follower]: "
                f"Target={target_export_w:.0f}W, Grid={grid_power_w:.0f}W, "
                f"GridError={grid_error_w:.0f}W, CombinedBattery={combined_battery_w:.0f}W, "
                f"BatteryNeeded={battery_power_needed_kw:.2f}kW"
            )
        else:
            # Method B: host only — step from last commanded power
            delta_kw = max(-DYNAMIC_EXPORT_MAX_STEP_KW, min(DYNAMIC_EXPORT_MAX_STEP_KW, grid_error_kw))
            battery_power_needed_kw = self._last_commanded_power_kw + delta_kw
            _LOGGER.debug(
                f"Dynamic Export [Method B — host only]: "
                f"Target={target_export_w:.0f}W, Grid={grid_power_w:.0f}W, "
                f"GridError={grid_error_w:.0f}W, LastCmd={self._last_commanded_power_kw:.2f}kW, "
                f"Delta={delta_kw:.2f}kW, BatteryNeeded={battery_power_needed_kw:.2f}kW"
            )

        # ── Settle timer ─────────────────────────────────────────────────────
        # After sending any command, wait DYNAMIC_EXPORT_SETTLE_SECONDS before
        # adjusting again. This gives the inverter time to actually ramp to the
        # commanded power and the grid meter time to reflect the change, preventing
        # the staircase oscillation caused by re-commanding before the hardware responds.
        now = dt_util.now()
        seconds_since_command = (
            (now - self._last_update_time).total_seconds()
            if self._last_update_time else float("inf")
        )

        if seconds_since_command < DYNAMIC_EXPORT_SETTLE_SECONDS:
            _LOGGER.debug(
                f"Dynamic Export: Waiting for inverter to settle — "
                f"{seconds_since_command:.0f}s since last command "
                f"(settle period={DYNAMIC_EXPORT_SETTLE_SECONDS}s), "
                f"current grid={grid_power_w/1000:.2f}kW"
            )
            return

        # ── Send command ──────────────────────────────────────────────────────
        if battery_power_needed_kw > DYNAMIC_EXPORT_MIN_POWER:
            discharge_power_kw = min(battery_power_needed_kw, self._max_discharge_power)
            discharge_power_kw = max(discharge_power_kw, DYNAMIC_EXPORT_MIN_POWER)
            _LOGGER.info(
                f"Dynamic Export: Discharging battery at {discharge_power_kw:.2f}kW "
                f"(Grid={grid_power_w/1000:.2f}kW, Export={current_export_w/1000:.2f}kW, "
                f"Target={target_export_kw:.2f}kW)"
            )
            await self._send_discharge_command(discharge_power_kw, soc_cutoff)
            self._last_commanded_power_kw = discharge_power_kw

        elif battery_power_needed_kw < -DYNAMIC_EXPORT_MIN_POWER:
            charge_power_kw = min(abs(battery_power_needed_kw), self._max_charge_power)
            charge_power_kw = max(charge_power_kw, DYNAMIC_EXPORT_MIN_POWER)
            _LOGGER.info(
                f"Dynamic Export: Charging battery at {charge_power_kw:.2f}kW to absorb excess "
                f"(Grid={grid_power_w/1000:.2f}kW, Export={current_export_w/1000:.2f}kW, "
                f"Target={target_export_kw:.2f}kW)"
            )
            await self._send_charge_command(charge_power_kw, 100)
            self._last_commanded_power_kw = -charge_power_kw

        else:
            _LOGGER.info(
                f"Dynamic Export: Within tolerance "
                f"(Grid={grid_power_w/1000:.2f}kW, Target={target_export_kw:.2f}kW)"
            )
            await self._send_standby_command()
            self._last_commanded_power_kw = 0.0

        self._last_update_time = now

    def _get_target_export_kw(self) -> float:
        """Return the desired net grid export setpoint (kW) for this cycle.

        Base implementation reads the static "Dynamic Mode Power Target" entity.
        Subclasses override to compute a dynamic setpoint.
        """
        return _safe_get_by_unique_id(
            self._hass,
            f"neovolt_{self._device_name}_dynamic_mode_power_target",
            1.0,
        )

    async def _send_discharge_command(self, power_kw: float, soc_cutoff: int) -> None:
        """Send force discharge command to inverter.

        Para5 is the system safety floor only (discharging_cutoff_soc register).
        The user's dispatch target is managed by DispatchSocWatcher in HA.
        """
        power_watts = int(power_kw * 1000)

        # Safety floor from inverter's own discharging_cutoff_soc register
        safety_floor = self._coordinator.data.get("discharging_cutoff_soc", 10) if self._coordinator.data else 10
        soc_value = soc_percent_to_register(safety_floor)

        # Use the full user-configured duration as the hardware timer so the
        # inverter cannot self-reset between HA update cycles.
        values = [
            1,                              # Para1: Dispatch start
            0,                              # Para2 high byte
            MODBUS_OFFSET + power_watts,    # Para2 low: DISCHARGE = 32000 + watts
            0,                              # Para3 high byte
            0,                              # Para3 low: Reactive power = 0
            DISPATCH_MODE_POWER_WITH_SOC,   # Para4: Mode 2 (SOC control)
            soc_value,                      # Para5: SOC cutoff (0-255 range)
            0,                              # Para6 high byte
            self._timeout_seconds,          # Para6 low: Time (seconds) — full duration
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
            self._coordinator.set_optimistic_value("dispatch_mode", self._dispatch_mode_tag)

        except Exception as e:
            _LOGGER.error(f"Failed to send Dynamic Export discharge command: {e}")
            raise

    async def _send_charge_command(self, power_kw: float, soc_target: int) -> None:
        """Send force charge command to inverter.

        Para5 is the system safety ceiling only (charging_cutoff_soc register).
        The user's dispatch target is managed by DispatchSocWatcher in HA.
        """
        power_watts = int(power_kw * 1000)

        # Safety ceiling from inverter's own charging_cutoff_soc register
        safety_ceiling = self._coordinator.data.get("charging_cutoff_soc", 100) if self._coordinator.data else 100
        soc_value = soc_percent_to_register(safety_ceiling)

        # Use the full user-configured duration as the hardware timer so the
        # inverter cannot self-reset between HA update cycles.
        values = [
            1,                              # Para1: Dispatch start
            0,                              # Para2 high byte
            MODBUS_OFFSET - power_watts,    # Para2 low: CHARGE = 32000 - watts
            0,                              # Para3 high byte
            0,                              # Para3 low: Reactive power = 0
            DISPATCH_MODE_POWER_WITH_SOC,   # Para4: Mode 2 (SOC control)
            soc_value,                      # Para5: SOC target (0-255 range)
            0,                              # Para6 high byte
            self._timeout_seconds,          # Para6 low: Time (seconds) — full duration
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
            self._coordinator.set_optimistic_value("dispatch_mode", self._dispatch_mode_tag)

        except Exception as e:
            _LOGGER.error(f"Failed to send Dynamic Export charge command: {e}")
            raise

    async def _send_standby_command(self, soc_limit: int = 0) -> None:
        """Send standby command (dispatch start=1 but power=0) to keep mode active.

        Para5 uses the system safety floor from the discharging_cutoff_soc register.
        """
        safety_floor = self._coordinator.data.get("discharging_cutoff_soc", 10) if self._coordinator.data else 10
        soc_value = soc_percent_to_register(safety_floor)
        try:
            # Keep dispatch active but with 0W command
            values = [
                1,                              # Para1: Dispatch start (keep active)
                0,                              # Para2 high byte
                MODBUS_OFFSET,                  # Para2 low: 0W (32000 + 0)
                0,                              # Para3 high byte
                0,                              # Para3 low: Reactive power = 0
                DISPATCH_MODE_POWER_WITH_SOC,   # Para4: Mode 2
                soc_value,                      # Para5: SOC cutoff (preserve floor)
                0,                              # Para6 high byte
                self._timeout_seconds,          # Para6 low: Time (seconds) — full duration
                255,                            # Para7: Energy routing (default)
                0,                              # Para8: PV switch (auto)
            ]

            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, values
            )

            # Update coordinator with optimistic values
            self._coordinator.set_optimistic_value("dispatch_start", 1)
            self._coordinator.set_optimistic_value("dispatch_power", 0)
            self._coordinator.set_optimistic_value("dispatch_mode", self._dispatch_mode_tag)

        except Exception as e:
            _LOGGER.error(f"Failed to send Dynamic Export standby command: {e}")

    async def _stop_and_reset_dispatch(self) -> None:
        """Stop dispatch, reset to Normal mode, and exit Dynamic Export."""
        from .const import DISPATCH_RESET_VALUES

        _LOGGER.info("Dynamic Export: resetting to Normal mode")

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
# Dynamic SOC Export Manager
# ---------------------------------------------------------------------------

class DynamicSOCExportManager(DynamicExportManager):
    """Dynamic SOC Export — smooth discharge to a target SOC across a window.

    Behaviour:
      * Each cycle, compute the smooth discharge rate needed to reach the target
        SOC by the end of the discharge window:

            smooth_rate_kw = (current_soc - target_soc)% × capacity_kWh / remaining_hours

      * To never import, the battery instead discharges at:

            battery_discharge_kw = max(smooth_rate_kw, house_load_kw + safety_buffer_kw)

        Equivalently, the grid export setpoint passed to the closed loop is:

            target_export_kw = max(smooth_rate_kw - house_load_kw, safety_buffer_kw)

      * When house load drops, the smooth rate is recomputed against the new
        (lower) remaining SOC and the (smaller) remaining time — so any excess
        discharged during a spike is naturally amortised across the rest of the
        window.

    The hard discharge cutoff (Dispatch Discharge Cutoff SOC) still applies as a
    floor — once reached, the loop sends standby commands and Para5 enforces
    the floor at the inverter.
    """

    _dispatch_mode_tag = DISPATCH_MODE_DYNAMIC_SOC_EXPORT

    def _get_target_export_kw(self) -> float:
        """Compute the export setpoint from SOC pacing and house load."""
        data = self._coordinator.data

        # ── Read user inputs ─────────────────────────────────────────────────
        target_soc = _safe_get_by_unique_id(
            self._hass,
            f"neovolt_{self._device_name}_dispatch_discharge_target_soc",
            float(DYNAMIC_SOC_EXPORT_DEFAULT_TARGET_SOC),
        )
        buffer_kw = _safe_get_by_unique_id(
            self._hass,
            f"neovolt_{self._device_name}_dispatch_discharge_export_buffer",
            float(DYNAMIC_SOC_EXPORT_DEFAULT_BUFFER),
        )

        # ── Remaining time in window ─────────────────────────────────────────
        # Floor at 1 minute so the smooth rate doesn't blow up in the final
        # seconds; once the window elapses the control loop ends the mode anyway.
        if self._start_time and self._duration_minutes:
            elapsed_s = (dt_util.now() - self._start_time).total_seconds()
            remaining_s = self._duration_minutes * 60.0 - elapsed_s
            remaining_hours = max(remaining_s / 3600.0, 1.0 / 60.0)
        else:
            remaining_hours = 1.0

        # ── Current SOC ──────────────────────────────────────────────────────
        current_soc = data.get(COMBINED_BATTERY_SOC) or data.get("battery_soc")
        if current_soc is None:
            _LOGGER.warning(
                "Dynamic SOC Export: current SOC unavailable, falling back to buffer only"
            )
            return buffer_kw

        # ── Battery capacity (kWh) ───────────────────────────────────────────
        capacity_kwh = (
            data.get(COMBINED_BATTERY_CAPACITY)
            or data.get("battery_capacity")
            or 20.1
        )

        # ── Smooth rate ──────────────────────────────────────────────────────
        soc_delta_pct = max(0.0, current_soc - target_soc)
        energy_to_discharge_kwh = (soc_delta_pct / 100.0) * capacity_kwh
        smooth_rate_kw = energy_to_discharge_kwh / remaining_hours

        # ── House load (W → kW) ──────────────────────────────────────────────
        house_load_w = (
            data.get(COMBINED_HOUSE_LOAD)
            or data.get("total_house_load")
            or 0
        )
        house_load_kw = house_load_w / 1000.0

        # ── Target grid export setpoint ──────────────────────────────────────
        # Battery discharge = max(smooth_rate, house_load + buffer)
        #   ⇒ grid export = battery_discharge − house_load
        #                 = max(smooth_rate − house_load, buffer)
        target_export_kw = max(smooth_rate_kw - house_load_kw, buffer_kw)

        _LOGGER.debug(
            f"Dynamic SOC Export: SOC {current_soc:.1f}%→{target_soc:.0f}%, "
            f"remaining={remaining_hours * 60:.1f}min, capacity={capacity_kwh:.1f}kWh, "
            f"smooth_rate={smooth_rate_kw:.2f}kW, load={house_load_kw:.2f}kW, "
            f"buffer={buffer_kw:.2f}kW → target_export={target_export_kw:.2f}kW"
        )
        return target_export_kw


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
        self._last_grid_power_w: Optional[float] = None  # Last grid reading used for debounce
        self._last_commanded_power_kw: float = 0.0       # Last power sent — used for slew limiting
        self._start_time: Optional[datetime] = None
        self._duration_minutes: Optional[int] = None
        # Hardware timer written to Para6 on every command — set to the full
        # user-configured duration on start() so the inverter cannot self-reset
        # between HA update cycles even if several cycles are missed.
        self._timeout_seconds: int = 600

        # Get max charge/discharge power directly from the coordinator's own config
        # entry — this is always correct and avoids the previous name-matching loop
        # which silently fell back to 5 kW defaults whenever device_name didn't
        # match exactly (e.g. slugified vs. un-slugified names, migrated entries).
        entry = coordinator.config_entry
        self._max_discharge_power = entry.data.get(
            CONF_MAX_DISCHARGE_POWER, DEFAULT_MAX_DISCHARGE_POWER
        )
        self._max_charge_power = entry.data.get(
            CONF_MAX_CHARGE_POWER, DEFAULT_MAX_CHARGE_POWER
        )

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

        duration_minutes = int(_safe_get_by_unique_id(
            self._hass,
            f"neovolt_{self._device_name}_dispatch_duration",
            120.0,
        ))

        _LOGGER.info(f"Starting Dynamic Import mode (duration: {duration_minutes} minutes)")
        self._running = True
        self._last_update_time = None
        self._last_grid_power_w = None
        self._last_commanded_power_kw = 0.0
        self._start_time = dt_util.now()
        self._duration_minutes = duration_minutes
        # Set hardware timer to full duration so the inverter cannot self-reset
        # between HA update cycles even if several consecutive cycles are missed.
        self._timeout_seconds = min(duration_minutes * 60, 65535)

        # Pin grid and battery blocks to fast poll rate for the duration of this mode
        self._coordinator.polling_manager.pin_block_interval("grid", DYNAMIC_MODE_FAST_POLL_INTERVAL)
        self._coordinator.polling_manager.pin_block_interval("battery", DYNAMIC_MODE_FAST_POLL_INTERVAL)
        _LOGGER.info(
            f"Dynamic Import: pinned grid+battery blocks to {DYNAMIC_MODE_FAST_POLL_INTERVAL}s poll interval"
        )

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

        # Release the fast-poll pin so grid+battery return to adaptive control
        self._coordinator.polling_manager.unpin_block_interval("grid")
        self._coordinator.polling_manager.unpin_block_interval("battery")
        _LOGGER.info("Dynamic Import: released grid+battery poll interval pins")

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

        Sign convention for grid_power_total (register 0x0021H):
            positive → importing from grid
            negative → exporting to grid

        To reach a target import level T (positive W):
            battery_charge_needed = target_import_W - grid_power_total_W

        Worked examples (target = 500 W):
            Grid = +200 W (importing 200 W) → needed = 500 - 200 = +300 W charge
            Grid = +700 W (importing 700 W) → needed = 500 - 700 = -200 W discharge
            Grid = -100 W (exporting 100 W) → needed = 500 - (-100) = +600 W charge

        DEBOUNCE:
        We debounce on the *grid power reading* (W), not the battery command.
        This prevents the closed-loop from oscillating: once a command is sent and
        the battery responds, the grid reading stabilises near target and subsequent
        cycles correctly see only a small change and skip redundant commands.
        """
        data = self._coordinator.data

        # Get target import power (kW) from the shared number entity (unique_id lookup)
        target_import_kw = _safe_get_by_unique_id(
            self._hass,
            f"neovolt_{self._device_name}_dynamic_mode_power_target",
            1.0,
        )

        # Get charge SOC ceiling from the Dispatch Charge Target SOC entity (unique_id lookup)
        soc_target = int(_safe_get_by_unique_id(
            self._hass,
            f"neovolt_{self._device_name}_dispatch_charge_soc",
            100.0,
        ))

        # ── Grid power (signed, W) ────────────────────────────────────────────
        # Authoritative system-wide net power — incorporates all inverters,
        # all house loads and all PV without needing to read them individually.
        grid_power_w = data.get("grid_power_total")
        if grid_power_w is None:
            _LOGGER.warning("Cannot calculate Dynamic Import — grid_power_total unavailable")
            return

        # ── Core calculation ──────────────────────────────────────────────────
        # grid_error = grid_power_w - target_import_w
        #   positive → importing more than target → ease off (less charge / more discharge)
        #   negative → importing less than target (or exporting) → charge more
        #
        # Two methods depending on follower availability:
        #
        # METHOD A — Host+Follower (combined_battery_w available and accurate):
        #   Uses actual combined battery output as baseline.
        #   current charge power = -combined_battery_w  (battery sign flipped: charge=negative)
        #   new charge = current charge + (-grid_error)  (negate: neg error → more charge)
        #   → battery_charge_needed = (-combined_battery_w - grid_error_w) / 1000
        #
        #   Verify (grid=-6815W, target=12100W, battery=+9917W discharging):
        #     grid_error = -6815 - 12100 = -18915W
        #     charge_needed = (-9917 - (-18915)) / 1000 = +9.0kW charge ✓
        #
        #   Steady state (grid=+12100W, battery=-6000W charging):
        #     grid_error = 0W → charge_needed = (6000 - 0) / 1000 = +6kW (holds) ✓
        #
        # METHOD B — Host only:
        #   No reliable battery baseline — step from last commanded power instead.
        #   Negate grid_error for delta: negative error → positive delta (more charge).
        #   → battery_charge_needed = last_commanded + clamp(-grid_error, ±MAX_STEP)
        target_import_w = target_import_kw * 1000
        grid_error_w = grid_power_w - target_import_w
        grid_error_kw = grid_error_w / 1000.0

        combined_battery_w = data.get(COMBINED_BATTERY_POWER)
        has_follower = (
            self._coordinator.follower_coordinator is not None
            and bool(self._coordinator.follower_coordinator.data)
        )
        if has_follower and combined_battery_w is not None:
            # Method A: accurate baseline from actual combined battery output
            battery_charge_needed_kw = (-combined_battery_w - grid_error_w) / 1000.0
            _LOGGER.debug(
                f"Dynamic Import [Method A — host+follower]: "
                f"Target={target_import_w:.0f}W, Grid={grid_power_w:.0f}W, "
                f"GridError={grid_error_w:.0f}W, CombinedBattery={combined_battery_w:.0f}W, "
                f"ChargeNeeded={battery_charge_needed_kw:.2f}kW"
            )
        else:
            # Method B: host only — step from last commanded power
            delta_kw = max(-DYNAMIC_EXPORT_MAX_STEP_KW, min(DYNAMIC_EXPORT_MAX_STEP_KW, -grid_error_kw))
            battery_charge_needed_kw = self._last_commanded_power_kw + delta_kw
            _LOGGER.debug(
                f"Dynamic Import [Method B — host only]: "
                f"Target={target_import_w:.0f}W, Grid={grid_power_w:.0f}W, "
                f"GridError={grid_error_w:.0f}W, LastCmd={self._last_commanded_power_kw:.2f}kW, "
                f"Delta={delta_kw:.2f}kW, ChargeNeeded={battery_charge_needed_kw:.2f}kW"
            )

        # ── Settle timer ─────────────────────────────────────────────────────
        now = dt_util.now()
        seconds_since_command = (
            (now - self._last_update_time).total_seconds()
            if self._last_update_time else float("inf")
        )

        if seconds_since_command < DYNAMIC_EXPORT_SETTLE_SECONDS:
            _LOGGER.debug(
                f"Dynamic Import: Waiting for inverter to settle — "
                f"{seconds_since_command:.0f}s since last command "
                f"(settle period={DYNAMIC_EXPORT_SETTLE_SECONDS}s), "
                f"current grid={grid_power_w/1000:.2f}kW"
            )
            return

        # ── Send command ─────────────────────────────────────────────────────
        if battery_charge_needed_kw > DYNAMIC_EXPORT_MIN_POWER:
            charge_power_kw = min(battery_charge_needed_kw, self._max_charge_power)
            charge_power_kw = max(charge_power_kw, DYNAMIC_EXPORT_MIN_POWER)
            _LOGGER.info(
                f"Dynamic Import: Charging battery at {charge_power_kw:.2f}kW "
                f"(Grid={grid_power_w/1000:.2f}kW, Target={target_import_kw:.2f}kW)"
            )
            await self._send_charge_command(charge_power_kw, soc_target)
            self._last_commanded_power_kw = charge_power_kw

        elif battery_charge_needed_kw < -DYNAMIC_EXPORT_MIN_POWER:
            discharge_power_kw = min(abs(battery_charge_needed_kw), self._max_discharge_power)
            discharge_power_kw = max(discharge_power_kw, DYNAMIC_EXPORT_MIN_POWER)
            _LOGGER.info(
                f"Dynamic Import: Discharging battery at {discharge_power_kw:.2f}kW "
                f"to reduce grid import to target "
                f"(Grid={grid_power_w/1000:.2f}kW, Target={target_import_kw:.2f}kW)"
            )
            soc_floor = int(_safe_get_by_unique_id(
                self._hass,
                f"neovolt_{self._device_name}_dispatch_discharge_soc",
                10.0,
            ))
            await self._send_discharge_command(discharge_power_kw, soc_floor)
            self._last_commanded_power_kw = -discharge_power_kw

        else:
            _LOGGER.info(
                f"Dynamic Import: Within tolerance "
                f"(Grid={grid_power_w/1000:.2f}kW, Target={target_import_kw:.2f}kW)"
            )
            await self._send_standby_command()
            self._last_commanded_power_kw = 0.0

        # Record time of this command for settle timer
        self._last_update_time = now

    async def _send_charge_command(self, power_kw: float, soc_target: int) -> None:
        """Send force charge command to inverter.

        Para5 is the system safety ceiling only (charging_cutoff_soc register).
        The user's dispatch target is managed by DispatchSocWatcher in HA.
        """
        power_watts = int(power_kw * 1000)
        safety_ceiling = self._coordinator.data.get("charging_cutoff_soc", 100) if self._coordinator.data else 100
        soc_value = soc_percent_to_register(safety_ceiling)

        # Use the full user-configured duration as the hardware timer so the
        # inverter cannot self-reset between HA update cycles.
        values = [
            1,                              # Para1: Dispatch start
            0,                              # Para2 high byte
            MODBUS_OFFSET - power_watts,    # Para2 low: CHARGE = 32000 - watts
            0,                              # Para3 high byte
            0,                              # Para3 low: Reactive power = 0
            DISPATCH_MODE_POWER_WITH_SOC,   # Para4: Mode 2 (SOC control)
            soc_value,                      # Para5: SOC target (0-255 range)
            0,                              # Para6 high byte
            self._timeout_seconds,          # Para6 low: Time (seconds) — full duration
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
        """Send force discharge command to counteract PV surplus.

        Para5 is the system safety floor only (discharging_cutoff_soc register).
        The user's dispatch target is managed by DispatchSocWatcher in HA.
        """
        power_watts = int(power_kw * 1000)
        safety_floor = self._coordinator.data.get("discharging_cutoff_soc", 10) if self._coordinator.data else 10
        soc_value = soc_percent_to_register(safety_floor)

        # Use the full user-configured duration as the hardware timer so the
        # inverter cannot self-reset between HA update cycles.
        values = [
            1,                              # Para1: Dispatch start
            0,                              # Para2 high byte
            MODBUS_OFFSET + power_watts,    # Para2 low: DISCHARGE = 32000 + watts
            0,                              # Para3 high byte
            0,                              # Para3 low: Reactive power = 0
            DISPATCH_MODE_POWER_WITH_SOC,   # Para4: Mode 2 (SOC control)
            soc_value,                      # Para5: SOC cutoff (0-255 range)
            0,                              # Para6 high byte
            self._timeout_seconds,          # Para6 low: Time (seconds) — full duration
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

    async def _send_standby_command(self, soc_limit: int = 100) -> None:
        """Send standby command to keep mode active at 0W.

        Para5 uses the system safety ceiling from the charging_cutoff_soc register.
        """
        safety_ceiling = self._coordinator.data.get("charging_cutoff_soc", 100) if self._coordinator.data else 100
        soc_value = soc_percent_to_register(safety_ceiling)
        try:
            values = [
                1,                              # Para1: Dispatch start (keep active)
                0,                              # Para2 high byte
                MODBUS_OFFSET,                  # Para2 low: 0W
                0,                              # Para3 high byte
                0,                              # Para3 low: Reactive power = 0
                DISPATCH_MODE_POWER_WITH_SOC,   # Para4: Mode 2
                soc_value,                      # Para5: SOC target (preserve ceiling)
                0,                              # Para6 high byte
                self._timeout_seconds,          # Para6 low: Time (seconds) — full duration
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

        _LOGGER.info("Dynamic Import: resetting to Normal mode")

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