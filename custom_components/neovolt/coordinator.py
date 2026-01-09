"""DataUpdateCoordinator for Neovolt Solar Inverter."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta, datetime
from typing import Any, Dict, List, Optional

from pymodbus.exceptions import ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_SLAVE_ID,
    CONF_MIN_POLL_INTERVAL,
    CONF_MAX_POLL_INTERVAL,
    CONF_CONSECUTIVE_FAILURE_THRESHOLD,
    CONF_STALENESS_THRESHOLD,
    DEFAULT_MIN_POLL_INTERVAL,
    DEFAULT_MAX_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_CONSECUTIVE_FAILURES,
    DEFAULT_STALENESS_THRESHOLD,
    RECOVERY_COOLDOWN_SECONDS,
    REGISTER_BLOCKS,
)
from .modbus_client import NeovoltModbusClient

_LOGGER = logging.getLogger(__name__)

# Base update interval - coordinator runs at min interval, but blocks are polled adaptively
UPDATE_INTERVAL = timedelta(seconds=10)

# Minimum time between persistent data saves (prevents excessive writes)
SAVE_DEBOUNCE_INTERVAL = timedelta(minutes=5)

# Maximum age of cached data before marking entities unavailable (12 hours)
DATA_STALE_THRESHOLD = timedelta(hours=12)

# Keys for storing persistent data in config entry
STORAGE_LAST_RESET_DATE = "last_reset_date"
STORAGE_MIDNIGHT_BASELINE = "pv_inverter_energy_at_midnight"
STORAGE_LAST_KNOWN_TOTAL = "last_known_total_energy"
STORAGE_DAILY_PRESERVED = "daily_energy_before_unavailable"


class AdaptivePollingManager:
    """Manages adaptive polling intervals per register block."""

    def __init__(
        self,
        min_interval: int = DEFAULT_MIN_POLL_INTERVAL,
        max_interval: int = DEFAULT_MAX_POLL_INTERVAL,
        default_interval: int = DEFAULT_POLL_INTERVAL,
    ):
        """Initialize the adaptive polling manager."""
        self.min_interval = max(min_interval, 10)  # Hard cap at 10s minimum
        self.max_interval = max_interval
        self.default_interval = default_interval
        self.block_intervals: Dict[str, float] = {}
        self.block_last_poll: Dict[str, datetime] = {}
        self.block_last_values: Dict[str, Dict[str, Any]] = {}
        self.block_consecutive_failures: Dict[str, int] = {}

    def should_poll_block(self, block_name: str, now: datetime) -> bool:
        """Check if enough time has elapsed to poll this block."""
        last_poll = self.block_last_poll.get(block_name)
        if last_poll is None:
            return True
        interval = self.block_intervals.get(block_name, self.default_interval)
        elapsed = (now - last_poll).total_seconds()
        return elapsed >= interval

    def update_after_poll(
        self, block_name: str, new_values: Dict[str, Any], now: datetime
    ) -> bool:
        """
        Update interval based on whether values changed.

        Returns True if values changed, False otherwise.
        """
        old_values = self.block_last_values.get(block_name, {})
        values_changed = new_values != old_values

        current = self.block_intervals.get(block_name, self.default_interval)
        if values_changed:
            # Values changed → poll faster (10% decrease), cap at min
            new_interval = max(current * 0.9, self.min_interval)
        else:
            # No changes → poll slower (10% increase), cap at max
            new_interval = min(current * 1.1, self.max_interval)

        self.block_intervals[block_name] = new_interval
        self.block_last_poll[block_name] = now
        self.block_last_values[block_name] = new_values.copy()

        return values_changed

    def get_cached_values(self, block_name: str) -> Dict[str, Any]:
        """Get cached values for a block that wasn't polled this cycle."""
        return self.block_last_values.get(block_name, {})

    def get_block_interval(self, block_name: str) -> float:
        """Get current polling interval for a block."""
        return self.block_intervals.get(block_name, self.default_interval)

    def record_block_failure(self, block_name: str) -> int:
        """Record a failed block read. Returns consecutive failure count."""
        self.block_consecutive_failures[block_name] = \
            self.block_consecutive_failures.get(block_name, 0) + 1
        return self.block_consecutive_failures[block_name]

    def reset_block_failures(self, block_name: str) -> None:
        """Reset failure count on successful read."""
        self.block_consecutive_failures[block_name] = 0

    def get_block_failures(self, block_name: str) -> int:
        """Get consecutive failure count for a block."""
        return self.block_consecutive_failures.get(block_name, 0)


class RecoveryManager:
    """Manages auto-recovery from stuck states."""

    def __init__(
        self,
        max_consecutive_failures: int = DEFAULT_CONSECUTIVE_FAILURES,
        staleness_threshold_minutes: int = DEFAULT_STALENESS_THRESHOLD,
        cooldown_seconds: int = RECOVERY_COOLDOWN_SECONDS,
    ):
        """Initialize the recovery manager."""
        self.max_consecutive_failures = max_consecutive_failures
        self.staleness_threshold_minutes = staleness_threshold_minutes
        self.cooldown_seconds = cooldown_seconds

        self.consecutive_failures: int = 0
        self.last_successful_update: Optional[datetime] = None
        self.last_data_change: Optional[datetime] = None
        self.last_recovery: Optional[datetime] = None
        self.recovery_count: int = 0

    def record_success(self, data_changed: bool, now: datetime) -> None:
        """Record a successful update."""
        self.consecutive_failures = 0
        self.last_successful_update = now
        if data_changed:
            self.last_data_change = now

    def record_failure(self) -> None:
        """Record a failed update."""
        self.consecutive_failures += 1

    def should_trigger_recovery(self, now: datetime) -> tuple[bool, str]:
        """
        Check if recovery should be triggered.

        Returns (should_recover, reason).
        """
        # Check cooldown
        if self.last_recovery is not None:
            cooldown_elapsed = (now - self.last_recovery).total_seconds()
            if cooldown_elapsed < self.cooldown_seconds:
                return False, ""

        # Check consecutive failures
        if self.consecutive_failures >= self.max_consecutive_failures:
            return True, f"consecutive_failures ({self.consecutive_failures})"

        # Check data staleness
        if self.last_data_change is not None:
            staleness_seconds = (now - self.last_data_change).total_seconds()
            staleness_minutes = staleness_seconds / 60.0
            if staleness_minutes >= self.staleness_threshold_minutes:
                return True, f"data_stale ({staleness_minutes:.1f} minutes)"

        return False, ""

    def record_recovery_attempt(self, now: datetime) -> None:
        """Record that recovery was attempted."""
        self.recovery_count += 1
        self.last_recovery = now
        self.consecutive_failures = 0  # Reset failure counter


class NeovoltDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Neovolt data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.host = entry.data[CONF_HOST]
        self.port = entry.data[CONF_PORT]
        self.slave_id = entry.data[CONF_SLAVE_ID]

        self.client = NeovoltModbusClient(
            host=self.host,
            port=self.port,
            slave_id=self.slave_id,
        )

        # Get polling configuration from entry data (with defaults for migration)
        min_interval = entry.data.get(CONF_MIN_POLL_INTERVAL, DEFAULT_MIN_POLL_INTERVAL)
        max_interval = entry.data.get(CONF_MAX_POLL_INTERVAL, DEFAULT_MAX_POLL_INTERVAL)
        consecutive_failures = entry.data.get(
            CONF_CONSECUTIVE_FAILURE_THRESHOLD, DEFAULT_CONSECUTIVE_FAILURES
        )
        staleness_threshold = entry.data.get(
            CONF_STALENESS_THRESHOLD, DEFAULT_STALENESS_THRESHOLD
        )

        # Initialize adaptive polling manager
        self.polling_manager = AdaptivePollingManager(
            min_interval=min_interval,
            max_interval=max_interval,
            default_interval=DEFAULT_POLL_INTERVAL,
        )

        # Initialize recovery manager
        self.recovery_manager = RecoveryManager(
            max_consecutive_failures=consecutive_failures,
            staleness_threshold_minutes=staleness_threshold,
        )

        # Debouncing for persistent data saves
        self._last_save_time = None

        # Track last successful data fetch for stale data detection
        self._last_successful_data_time: Optional[datetime] = None
        self._last_known_data: Dict[str, Any] = {}

        # Load persistent values from config entry options
        # This ensures they survive Home Assistant restarts
        options = entry.options or {}

        # Load last reset date (stored as ISO string)
        last_reset_str = options.get(STORAGE_LAST_RESET_DATE)
        if last_reset_str:
            try:
                self._last_reset_date = datetime.fromisoformat(last_reset_str).date()
                _LOGGER.info(f"Restored last reset date: {self._last_reset_date}")
            except (ValueError, AttributeError):
                self._last_reset_date = None
                _LOGGER.warning(f"Invalid stored reset date: {last_reset_str}")
        else:
            self._last_reset_date = None

        # Load midnight baseline
        self._pv_inverter_energy_at_midnight = options.get(STORAGE_MIDNIGHT_BASELINE)
        if self._pv_inverter_energy_at_midnight is not None:
            _LOGGER.info(f"Restored midnight baseline: {self._pv_inverter_energy_at_midnight} kWh")

        # Load last known total
        self._last_known_total_energy = options.get(STORAGE_LAST_KNOWN_TOTAL)
        if self._last_known_total_energy is not None:
            _LOGGER.info(f"Restored last known total: {self._last_known_total_energy} kWh")

        # Load preserved daily value
        self._daily_energy_before_unavailable = options.get(STORAGE_DAILY_PRESERVED)
        if self._daily_energy_before_unavailable is not None:
            _LOGGER.info(f"Restored preserved daily: {self._daily_energy_before_unavailable} kWh")

        # Use min_interval as the base coordinator update interval
        update_interval = timedelta(seconds=min_interval)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.data[CONF_HOST]}",
            update_interval=update_interval,
        )

    def _save_persistent_data(self) -> None:
        """Save daily tracking data to config entry options with debouncing."""
        now = dt_util.now()

        # Debounce: only save if enough time has passed since last save
        if self._last_save_time and (now - self._last_save_time) < SAVE_DEBOUNCE_INTERVAL:
            _LOGGER.debug(
                f"Debouncing save - {(now - self._last_save_time).total_seconds():.0f}s since last save"
            )
            return

        # Update last save time
        self._last_save_time = now

        # Prepare data to save
        new_options = dict(self.entry.options or {})

        # Save reset date as ISO string
        if self._last_reset_date:
            new_options[STORAGE_LAST_RESET_DATE] = self._last_reset_date.isoformat()

        # Save numeric values
        if self._pv_inverter_energy_at_midnight is not None:
            new_options[STORAGE_MIDNIGHT_BASELINE] = self._pv_inverter_energy_at_midnight

        if self._last_known_total_energy is not None:
            new_options[STORAGE_LAST_KNOWN_TOTAL] = self._last_known_total_energy

        if self._daily_energy_before_unavailable is not None:
            new_options[STORAGE_DAILY_PRESERVED] = self._daily_energy_before_unavailable

        # Schedule the async config entry update on the event loop
        self.hass.async_create_task(
            self._async_save_persistent_data(new_options)
        )

    async def _async_save_persistent_data(self, new_options: dict) -> None:
        """Actually save the persistent data to config entry."""
        self.hass.config_entries.async_update_entry(
            self.entry,
            options=new_options
        )
        _LOGGER.debug("Saved persistent daily tracking data")

    async def _async_update_data(self):
        """Fetch data from the inverter with adaptive polling and auto-recovery."""
        now = dt_util.now()

        # Check if recovery is needed before polling
        should_recover, reason = self.recovery_manager.should_trigger_recovery(now)
        if should_recover:
            _LOGGER.warning(f"Auto-recovery triggered: {reason}")
            await self._perform_recovery()
            self.recovery_manager.record_recovery_attempt(now)

        try:
            # Fetch data with adaptive polling
            data, any_data_changed = await self.hass.async_add_executor_job(
                self._fetch_data_adaptive, now
            )

            # Record success for recovery manager
            self.recovery_manager.record_success(any_data_changed, now)

            # CRITICAL FIX: Merge new data with cache FIRST (before timestamp update)
            # This prevents race condition where timestamp is set but data isn't yet merged
            # Also preserves keys from successful prior reads even if some blocks failed
            self._last_known_data.update(data)
            
            # Now update timestamp for stale data detection (AFTER data merge)
            self._last_successful_data_time = now

            # Return merged cache to ensure all previously seen keys are available
            # even if some blocks failed to read this cycle
            return dict(self._last_known_data)

        except Exception as err:
            # Catch ALL exceptions to ensure cache-return logic always runs
            # This prevents uncaught exceptions (ValueError, AttributeError, etc.)
            # from bypassing our cached data fallback
            self.recovery_manager.record_failure()
            _LOGGER.warning(f"Failed to fetch data: {err}")

            # Return cached data if available and not too old (< 12 hours)
            if self._last_known_data and self._last_successful_data_time:
                age = now - self._last_successful_data_time
                if age < DATA_STALE_THRESHOLD:
                    _LOGGER.debug(
                        f"Using cached data ({age.total_seconds():.0f}s old, "
                        f"{age.total_seconds()/3600:.1f}h)"
                    )
                    return self._last_known_data
                else:
                    _LOGGER.warning(
                        f"Cached data too old ({age.total_seconds()/3600:.1f}h), "
                        f"marking entities unavailable"
                    )

            # Only raise UpdateFailed if no cached data or data is too old
            raise UpdateFailed(f"Error communicating with inverter: {err}") from err

    async def _perform_recovery(self) -> None:
        """Perform recovery by forcing a reconnection."""
        _LOGGER.info("Performing auto-recovery: forcing Modbus reconnection")
        try:
            # Add 30 second timeout to prevent hanging indefinitely
            success = await asyncio.wait_for(
                self.hass.async_add_executor_job(self.client.force_reconnect),
                timeout=30.0
            )
            if success:
                _LOGGER.info("Auto-recovery: reconnection successful")
            else:
                _LOGGER.warning("Auto-recovery: reconnection failed")
        except asyncio.TimeoutError:
            _LOGGER.error("Auto-recovery: reconnection timed out after 30s")
        except Exception as e:
            _LOGGER.error(f"Auto-recovery: error during reconnection: {e}")

    def _fetch_data_adaptive(self, now: datetime) -> tuple[Dict[str, Any], bool]:
        """
        Fetch data with adaptive polling per block.

        Returns:
            Tuple of (data dict, whether any data changed)
        """
        # CRITICAL FIX: Start with existing cached data instead of empty dict
        # This prevents gaps when individual blocks fail - their keys remain in cache
        data = dict(self._last_known_data)
        
        any_data_changed = False
        successful_reads = {"grid": False, "pv": False, "battery": False}
        critical_blocks = {"grid", "pv", "battery"}

        # Process each register block
        for block_name in REGISTER_BLOCKS:
            if self.polling_manager.should_poll_block(block_name, now):
                # Poll this block
                block_data = self._read_block(block_name)
                if block_data:
                    # Success - reset failure counter and update polling interval
                    self.polling_manager.reset_block_failures(block_name)
                    changed = self.polling_manager.update_after_poll(
                        block_name, block_data, now
                    )
                    if changed:
                        any_data_changed = True
                    # Overlay new data on existing cache
                    data.update(block_data)

                    # Track successful reads for critical blocks
                    if block_name in successful_reads:
                        successful_reads[block_name] = True
                else:
                    # Read failed - keep existing cached values (don't update with empty dict)
                    failure_count = self.polling_manager.record_block_failure(block_name)
                    
                    if block_name in critical_blocks:
                        _LOGGER.warning(
                            f"Block {block_name} read failed ({failure_count} consecutive), "
                            f"using cached values"
                        )
                    else:
                        _LOGGER.debug(f"Block {block_name} read failed, using cached values")
                    
                    # No data.update() needed - we started with existing cache
            else:
                # Block not polled this cycle - use cached values (already in data)
                # Check if we have cached values for dependency tracking
                cached = self.polling_manager.get_cached_values(block_name)
                if block_name in successful_reads and cached:
                    successful_reads[block_name] = True

        # Check if any critical block has too many failures - flag for recovery
        for block_name in critical_blocks:
            failures = self.polling_manager.get_block_failures(block_name)
            if failures >= self.recovery_manager.max_consecutive_failures:
                _LOGGER.warning(
                    f"Critical block {block_name} failed {failures} times, "
                    f"triggering recovery"
                )
                # Reset the block failure counter to avoid repeated triggers
                self.polling_manager.reset_block_failures(block_name)
                # Force recovery on next cycle
                self.recovery_manager.consecutive_failures = \
                    self.recovery_manager.max_consecutive_failures

        # Calculate derived values
        self._calculate_derived_values(data, successful_reads)

        _LOGGER.debug(
            f"Adaptive fetch: {len(data)} keys, changed={any_data_changed}, "
            f"intervals={self._get_interval_summary()}"
        )

        return data, any_data_changed

    def _get_interval_summary(self) -> str:
        """Get a summary of current block intervals for logging."""
        intervals = []
        for block_name in REGISTER_BLOCKS:
            interval = self.polling_manager.get_block_interval(block_name)
            intervals.append(f"{block_name[:3]}:{interval:.0f}s")
        return ", ".join(intervals)

    def _read_block(self, block_name: str) -> Dict[str, Any]:
        """Read a specific register block and return parsed data."""
        block = REGISTER_BLOCKS.get(block_name)
        if not block:
            return {}

        regs = self.client.read_holding_registers(block.address, block.count)
        if not regs:
            return {}

        # Parse registers based on block type
        if block_name == "grid":
            return self._parse_grid_registers(regs)
        elif block_name == "pv":
            return self._parse_pv_registers(regs)
        elif block_name == "battery":
            return self._parse_battery_registers(regs)
        elif block_name == "inverter":
            return self._parse_inverter_registers(regs)
        elif block_name == "pv_inverter_energy":
            return self._parse_pv_inverter_energy_registers(regs)
        elif block_name == "settings":
            return self._parse_settings_registers(regs)
        elif block_name == "dispatch":
            return self._parse_dispatch_registers(regs)

        return {}

    def _parse_grid_registers(self, regs: List[int]) -> Dict[str, Any]:
        """Parse grid register block (0x0010-0x0036)."""
        return {
            "grid_energy_feed": self._to_unsigned_32(regs[0], regs[1]) * 0.01,
            "grid_energy_consume": self._to_unsigned_32(regs[2], regs[3]) * 0.01,
            "grid_voltage_a": regs[4],
            "grid_voltage_b": regs[5],
            "grid_voltage_c": regs[6],
            "grid_current_a": self._to_signed(regs[7]) * 0.1,
            "grid_current_b": self._to_signed(regs[8]) * 0.1,
            "grid_current_c": self._to_signed(regs[9]) * 0.1,
            "grid_frequency": regs[10] * 0.01,
            "grid_power_a": self._to_signed_32(regs[11], regs[12]),
            "grid_power_b": self._to_signed_32(regs[13], regs[14]),
            "grid_power_c": self._to_signed_32(regs[15], regs[16]),
            "grid_power_total": self._to_signed_32(regs[17], regs[18]),
            "grid_power_factor": self._to_signed(regs[38]) * 0.01,
        }

    def _parse_pv_registers(self, regs: List[int]) -> Dict[str, Any]:
        """Parse PV register block (0x0090-0x00A3)."""
        return {
            "pv_energy_feed": self._to_unsigned_32(regs[0], regs[1]) * 0.01,
            "pv_voltage_a": regs[4],
            "pv_ac_power_total": self._to_signed_32(regs[17], regs[18]),
        }

    def _parse_battery_registers(self, regs: List[int]) -> Dict[str, Any]:
        """Parse battery register block (0x0100-0x0127)."""
        return {
            "battery_voltage": regs[0] * 0.1,
            "battery_current": self._to_signed(regs[1]) * 0.1,
            "battery_soc": regs[2] * 0.1,
            "battery_min_cell_voltage": regs[7] * 0.001,
            "battery_max_cell_voltage": regs[10] * 0.001,
            "battery_min_cell_temp": self._to_signed(regs[13]) * 0.1,
            "battery_max_cell_temp": self._to_signed(regs[16]) * 0.1,
            "battery_capacity": regs[25] * 0.1,
            "battery_soh": regs[27] * 0.1,
            "battery_charge_energy": self._to_unsigned_32(regs[32], regs[33]) * 0.1,
            "battery_discharge_energy": self._to_unsigned_32(regs[34], regs[35]) * 0.1,
            "battery_power": self._to_signed(regs[38]),
        }

    def _parse_inverter_registers(self, regs: List[int]) -> Dict[str, Any]:
        """Parse inverter register block (0x0500-0x056D)."""
        return {
            "inv_energy_output": self._to_unsigned_32(regs[2], regs[3]) * 0.1,
            "inv_energy_input": self._to_unsigned_32(regs[4], regs[5]) * 0.1,
            "total_pv_energy": self._to_unsigned_32(regs[10], regs[11]) * 0.1,
            "inv_module_temp": self._to_signed(regs[16]) * 0.1,
            "pv_boost_temp": self._to_signed(regs[17]) * 0.1,
            "battery_buck_boost_temp": self._to_signed(regs[18]) * 0.1,
            "bus_voltage": regs[32] * 0.1,
            "pv1_voltage": regs[36] * 0.1,
            "pv2_voltage": regs[37] * 0.1,
            "pv3_voltage": regs[38] * 0.1,
            "pv1_current": regs[39] * 0.01,
            "pv2_current": regs[40] * 0.01,
            "pv3_current": regs[41] * 0.01,
            "pv1_power": regs[42],
            "pv2_power": regs[43],
            "pv3_power": regs[44],
            "pv_dc_power_total": regs[45],
            "inv_power_active": self._to_signed_32(regs[69], regs[70]),
            "backup_power": self._to_signed_32(regs[91], regs[92]),
        }

    def _parse_pv_inverter_energy_registers(self, regs: List[int]) -> Dict[str, Any]:
        """Parse PV inverter energy register block (0x08D0)."""
        pv_inverter_total = self._to_unsigned_32(regs[0], regs[1]) * 0.01
        return {"pv_inverter_energy": pv_inverter_total}

    def _parse_settings_registers(self, regs: List[int]) -> Dict[str, Any]:
        """Parse settings register block (0x0800-0x0855)."""
        return {
            "max_feed_to_grid": regs[0],
            "pv_capacity": (regs[1] << 16) | regs[2],
            "charging_cutoff_soc": regs[85],
            "discharging_cutoff_soc": regs[80],
            "time_period_control_flag": regs[79],
        }

    def _parse_dispatch_registers(self, regs: List[int]) -> Dict[str, Any]:
        """Parse dispatch register block (0x0880-0x0888)."""
        power_raw = self._to_unsigned_32(regs[1], regs[2])
        return {
            "dispatch_start": regs[0],
            "dispatch_power": power_raw - 32000,
        }

    def _calculate_derived_values(
        self, data: Dict[str, Any], successful_reads: Dict[str, bool]
    ) -> None:
        """Calculate derived values from the fetched data."""
        # Combined PV power (DC + AC)
        pv_dc = data.get("pv_dc_power_total", 0)
        pv_ac = data.get("pv_ac_power_total", 0)
        data["pv_power_total"] = pv_dc + pv_ac

        # Current PV production (sum of all strings)
        data["current_pv_production"] = (
            data.get("pv1_power", 0) +
            data.get("pv2_power", 0) +
            data.get("pv3_power", 0)
        )

        # Daily PV energy calculation
        pv_inverter_total = data.get("pv_inverter_energy", 0)
        if pv_inverter_total:
            self._last_known_total_energy = pv_inverter_total

        dc_pv_energy = data.get("total_pv_energy", 0)
        ac_pv_energy = data.get("pv_inverter_energy", pv_inverter_total)
        combined_pv_energy = dc_pv_energy + ac_pv_energy

        if combined_pv_energy > 0:
            daily_energy, data_changed_today = self._calculate_daily_pv_energy(
                combined_pv_energy
            )
            data["pv_inverter_energy_today"] = daily_energy
            # If daily PV data changed, schedule a save
            if data_changed_today:
                self.hass.loop.call_soon_threadsafe(self._save_persistent_data)
        elif self._daily_energy_before_unavailable is not None:
            data["pv_inverter_energy_today"] = self._daily_energy_before_unavailable

        # House load calculation - calculate with available data
        pv_power = data.get("pv_power_total", 0)
        battery_power = data.get("battery_power", 0)
        grid_power = data.get("grid_power_total", 0)

        # Count available power sources
        available_sources = sum([
            successful_reads.get("pv", False),
            successful_reads.get("battery", False),
            successful_reads.get("grid", False),
        ])

        if available_sources >= 2:
            # Need at least 2 of 3 sources for a reasonable estimate
            house_load = pv_power + battery_power + grid_power

            if house_load < 0:
                _LOGGER.debug(
                    f"House load negative ({house_load}W) - expected in multi-inverter setups"
                )
                data["total_house_load"] = house_load
                data["excess_grid_export"] = abs(house_load)
            else:
                data["total_house_load"] = house_load
                data["excess_grid_export"] = 0

            # Flag if this is an estimated value (missing one source)
            data["house_load_estimated"] = available_sources < 3
        else:
            # Not enough data for reliable calculation - FIXED INDENTATION
            data["total_house_load"] = None
            data["house_load_estimated"] = None
            data["excess_grid_export"] = 0

    def _calculate_daily_pv_energy(self, total_energy: float) -> tuple[float, bool]:
        """
        Calculate daily PV inverter energy by resetting at midnight.
        IMPROVED: Handles source sensor unavailability without resetting.
        
        Args:
            total_energy: The lifetime total PV inverter energy in kWh
            
        Returns:
            Tuple of (today's PV inverter energy in kWh, whether data changed)
        """
        now = dt_util.now()
        current_date = now.date()
        data_changed = False
        
        # Check if we need to reset (new day)
        if self._last_reset_date != current_date:
            _LOGGER.info(
                f"Daily PV inverter energy reset - New day detected. "
                f"Previous date: {self._last_reset_date}, Current date: {current_date}. "
                f"Midnight baseline set to: {total_energy} kWh"
            )
            # Store the total energy at midnight
            self._pv_inverter_energy_at_midnight = total_energy
            self._last_reset_date = current_date
            
            # Clear preserved value from yesterday
            self._daily_energy_before_unavailable = None
            
            data_changed = True
            
            # First reading of the day = 0
            return 0.0, data_changed
        
        # Calculate energy since midnight
        if self._pv_inverter_energy_at_midnight is not None:
            daily_energy = total_energy - self._pv_inverter_energy_at_midnight
            
            # Handle counter rollover or decrease (shouldn't happen but be defensive)
            if daily_energy < 0:
                _LOGGER.warning(
                    f"PV inverter energy counter appears to have rolled over or decreased. "
                    f"Total: {total_energy}, Midnight: {self._pv_inverter_energy_at_midnight}. "
                    f"Difference: {daily_energy}"
                )
                # DON'T reset midnight baseline - preserve what we have
                # Just return the preserved value
                if self._daily_energy_before_unavailable is not None and self._daily_energy_before_unavailable > 0:
                    _LOGGER.info(f"Preserving daily value of {self._daily_energy_before_unavailable} kWh during counter anomaly")
                    return self._daily_energy_before_unavailable, False
                else:
                    # Last resort - reset baseline
                    _LOGGER.warning("No preserved value available - resetting midnight baseline")
                    self._pv_inverter_energy_at_midnight = total_energy
                    data_changed = True
                    return 0.0, data_changed
            
            # CRITICAL FIX: Preserve daily value for when source goes unavailable
            # Only update if we have a valid positive value
            if daily_energy > 0:
                old_preserved = self._daily_energy_before_unavailable
                self._daily_energy_before_unavailable = round(daily_energy, 2)
                if old_preserved != self._daily_energy_before_unavailable:
                    data_changed = True
                _LOGGER.debug(f"Updated preserved daily energy: {self._daily_energy_before_unavailable} kWh")
                
            return round(daily_energy, 2), data_changed
        else:
            # First run ever - establish baseline
            _LOGGER.info(f"Establishing PV inverter energy baseline: {total_energy} kWh")
            self._pv_inverter_energy_at_midnight = total_energy
            self._last_reset_date = current_date
            self._daily_energy_before_unavailable = 0.0
            data_changed = True
            return 0.0, data_changed

    @staticmethod
    def _to_signed(value: int) -> int:
        """Convert unsigned 16-bit to signed."""
        if value > 32767:
            return value - 65536
        return value

    @staticmethod
    def _to_signed_32(high: int, low: int) -> int:
        """Convert two 16-bit registers to signed 32-bit."""
        value = (high << 16) | low
        if value > 2147483647:
            return value - 4294967296
        return value

    @staticmethod
    def _to_unsigned_32(high: int, low: int) -> int:
        """Convert two 16-bit registers to unsigned 32-bit."""
        return (high << 16) | low

    @property
    def data_age_seconds(self) -> Optional[float]:
        """Return age of data in seconds, or None if never successfully updated."""
        if self._last_successful_data_time is None:
            return None
        return (dt_util.now() - self._last_successful_data_time).total_seconds()

    @property
    def is_data_stale(self) -> bool:
        """Return True if data is older than 12 hours."""
        age = self.data_age_seconds
        if age is None:
            return False  # No timestamp yet = not stale (startup state)
        return age > DATA_STALE_THRESHOLD.total_seconds()

    @property
    def has_valid_data(self) -> bool:
        """Return True if we have any cached data that's not stale.

        Used by entities to determine availability independently of last_update_success.
        This prevents brief "unavailable" flashes during connection hiccups.
        """
        # Must have cached data
        if not self._last_known_data:
            return False
        # If no timestamp yet (startup), data is valid as long as cache exists
        if self._last_successful_data_time is None:
            return True
        # Have data and timestamp - check 12-hour staleness
        return not self.is_data_stale

    def set_optimistic_value(self, key: str, value: Any) -> None:
        """Set a value optimistically after write command.

        Updates cache immediately so UI shows expected state before
        next poll confirms actual inverter state. If write failed,
        next poll will correct the cached value automatically.
        """
        self._last_known_data[key] = value