"""DataUpdateCoordinator for Neovolt Solar Inverter."""
from __future__ import annotations

import logging
from datetime import timedelta, datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, CONF_SLAVE_ID
from .modbus_client import NeovoltModbusClient

_LOGGER = logging.getLogger(__name__)

# Update interval - how often to poll the inverter
UPDATE_INTERVAL = timedelta(seconds=10)

# Minimum time between persistent data saves (prevents excessive writes)
SAVE_DEBOUNCE_INTERVAL = timedelta(minutes=5)

# Keys for storing persistent data in config entry
STORAGE_LAST_RESET_DATE = "last_reset_date"
STORAGE_MIDNIGHT_BASELINE = "pv_inverter_energy_at_midnight"
STORAGE_LAST_KNOWN_TOTAL = "last_known_total_energy"
STORAGE_DAILY_PRESERVED = "daily_energy_before_unavailable"


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

        # Debouncing for persistent data saves
        self._last_save_time = None
        self._pending_save = False

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

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.data[CONF_HOST]}",
            update_interval=UPDATE_INTERVAL,
        )

    def _save_persistent_data(self) -> None:
        """Save daily tracking data to config entry options with debouncing."""
        now = datetime.now()
        
        # Debounce: only save if enough time has passed since last save
        if self._last_save_time and (now - self._last_save_time) < SAVE_DEBOUNCE_INTERVAL:
            # Mark that a save is pending but don't execute yet
            self._pending_save = True
            _LOGGER.debug(f"Debouncing save - {(now - self._last_save_time).seconds}s since last save")
            return
        
        # Reset pending flag and update last save time
        self._pending_save = False
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
        
        # Update config entry (this persists to storage)
        self.hass.config_entries.async_update_entry(
            self.entry,
            options=new_options
        )
        _LOGGER.debug("Saved persistent daily tracking data")

    async def _async_update_data(self):
        """Fetch data from the inverter."""
        try:
            return await self.hass.async_add_executor_job(self._fetch_data)
        except Exception as err:
            raise UpdateFailed(f"Error communicating with inverter: {err}") from err

    def _fetch_data(self):
        """Fetch data from Modbus (runs in executor)."""
        data = {}

        # Track which critical register blocks were successfully read
        # Used to ensure data consistency for calculated values
        successful_reads = {
            "grid": False,
            "pv": False,
            "battery": False,
        }

        try:
            # Grid data (0x0010-0x0036) - Using YAML addresses
            grid_regs = self.client.read_holding_registers(0x0010, 39)
            if grid_regs:
                # 0x0010-0x0011: Total Energy Feed to Grid
                data["grid_energy_feed"] = self._to_unsigned_32(grid_regs[0], grid_regs[1]) * 0.01
                # 0x0012-0x0013: Total Energy Consume from Grid
                data["grid_energy_consume"] = self._to_unsigned_32(grid_regs[2], grid_regs[3]) * 0.01
                # 0x0014-0x0016: Grid Voltage Phase A, B, C (no scaling)
                data["grid_voltage_a"] = grid_regs[4]
                data["grid_voltage_b"] = grid_regs[5]
                data["grid_voltage_c"] = grid_regs[6]
                # 0x0017-0x0019: Grid Current Phase A, B, C (signed, scale 0.1)
                data["grid_current_a"] = self._to_signed(grid_regs[7]) * 0.1
                data["grid_current_b"] = self._to_signed(grid_regs[8]) * 0.1
                data["grid_current_c"] = self._to_signed(grid_regs[9]) * 0.1
                # 0x001A: Grid Frequency (scale 0.01)
                data["grid_frequency"] = grid_regs[10] * 0.01
                # 0x001B-0x001C: Grid Active Power Phase A (int32)
                data["grid_power_a"] = self._to_signed_32(grid_regs[11], grid_regs[12])
                # 0x001D-0x001E: Grid Active Power Phase B (int32)
                data["grid_power_b"] = self._to_signed_32(grid_regs[13], grid_regs[14])
                # 0x001F-0x0020: Grid Active Power Phase C (int32)
                data["grid_power_c"] = self._to_signed_32(grid_regs[15], grid_regs[16])
                # 0x0021-0x0022: Grid Total Active Power (int32)
                data["grid_power_total"] = self._to_signed_32(grid_regs[17], grid_regs[18])
                # 0x0036: Grid Power Factor (signed, scale 0.01)
                data["grid_power_factor"] = self._to_signed(grid_regs[38]) * 0.01
                successful_reads["grid"] = True
            else:
                _LOGGER.warning("Failed to read grid registers - grid data unavailable")

            # PV data (0x0090-0x00A3) - AC-coupled PV meter
            pv_regs = self.client.read_holding_registers(0x0090, 20)
            if pv_regs:
                # 0x0090-0x0091: PV Total Energy Feed to Grid (scale 0.01)
                data["pv_energy_feed"] = self._to_unsigned_32(pv_regs[0], pv_regs[1]) * 0.01
                # 0x0094: PV Voltage Phase A (no scaling)
                data["pv_voltage_a"] = pv_regs[4]
                # 0x00A1-0x00A2: PV Total Active Power (int32, no scaling) - AC-coupled only
                data["pv_ac_power_total"] = self._to_signed_32(pv_regs[17], pv_regs[18])
                successful_reads["pv"] = True
            else:
                _LOGGER.warning("Failed to read PV registers - PV data unavailable")
                data["pv_ac_power_total"] = 0

            # Battery data (0x0100-0x0127)
            battery_regs = self.client.read_holding_registers(0x0100, 40)
            if battery_regs:
                # 0x0100: Battery Voltage (scale 0.1)
                data["battery_voltage"] = battery_regs[0] * 0.1
                # 0x0101: Battery Current (signed, scale 0.1)
                data["battery_current"] = self._to_signed(battery_regs[1]) * 0.1
                # 0x0102: Battery SOC (scale 0.1)
                data["battery_soc"] = battery_regs[2] * 0.1
                # 0x0107: Battery Min Cell Voltage (scale 0.001)
                data["battery_min_cell_voltage"] = battery_regs[7] * 0.001
                # 0x010A: Battery Max Cell Voltage (scale 0.001)
                data["battery_max_cell_voltage"] = battery_regs[10] * 0.001
                # NOTE: The Modbus reference documentation incorrectly states temperature
                # scale as 0.01°C, but testing confirms the actual scale is 0.1°C.
                # 0x010D: Battery Min Cell Temperature (signed, scale 0.1)
                data["battery_min_cell_temp"] = self._to_signed(battery_regs[13]) * 0.1
                # 0x0110: Battery Max Cell Temperature (signed, scale 0.1)
                data["battery_max_cell_temp"] = self._to_signed(battery_regs[16]) * 0.1
                # 0x0119: Battery Capacity (scale 0.1)
                data["battery_capacity"] = battery_regs[25] * 0.1
                # 0x011B: Battery SOH (scale 0.1)
                data["battery_soh"] = battery_regs[27] * 0.1
                # 0x0120-0x0121: Battery Charge Energy (scale 0.1)
                data["battery_charge_energy"] = self._to_unsigned_32(battery_regs[32], battery_regs[33]) * 0.1
                # 0x0122-0x0123: Battery Discharge Energy (scale 0.1)
                data["battery_discharge_energy"] = self._to_unsigned_32(battery_regs[34], battery_regs[35]) * 0.1
                # 0x0126: Battery Power (signed, no scaling)
                data["battery_power"] = self._to_signed(battery_regs[38])
                successful_reads["battery"] = True
            else:
                _LOGGER.warning("Failed to read battery registers - battery data unavailable")

            # Inverter data (0x0500-0x056D)
            inv_regs = self.client.read_holding_registers(0x0500, 110)
            if inv_regs:
                # 0x0502-0x0503: Total Energy INV Output (scale 0.1)
                data["inv_energy_output"] = self._to_unsigned_32(inv_regs[2], inv_regs[3]) * 0.1
                # 0x0504-0x0505: Total Energy INV Input (scale 0.1)
                data["inv_energy_input"] = self._to_unsigned_32(inv_regs[4], inv_regs[5]) * 0.1
                # 0x050A-0x050B: Total PV Energy (scale 0.1)
                data["total_pv_energy"] = self._to_unsigned_32(inv_regs[10], inv_regs[11]) * 0.1
                # 0x0510: Inverter Module Temperature (signed, scale 0.1)
                data["inv_module_temp"] = self._to_signed(inv_regs[16]) * 0.1
                # 0x0511: PV Boost Temperature (signed, scale 0.1)
                data["pv_boost_temp"] = self._to_signed(inv_regs[17]) * 0.1
                # 0x0512: Battery Buck Boost Temperature (signed, scale 0.1)
                data["battery_buck_boost_temp"] = self._to_signed(inv_regs[18]) * 0.1
                # 0x0520: Bus Voltage (scale 0.1)
                data["bus_voltage"] = inv_regs[32] * 0.1
                # 0x0524-0x0526: PV1/2/3 Voltage (scale 0.1)
                data["pv1_voltage"] = inv_regs[36] * 0.1
                data["pv2_voltage"] = inv_regs[37] * 0.1
                data["pv3_voltage"] = inv_regs[38] * 0.1
                # 0x0527-0x0529: PV1/2/3 Current (scale 0.01)
                data["pv1_current"] = inv_regs[39] * 0.01
                data["pv2_current"] = inv_regs[40] * 0.01
                data["pv3_current"] = inv_regs[41] * 0.01
                # 0x052A-0x052C: PV1/2/3 Power (no scaling)
                data["pv1_power"] = inv_regs[42]
                data["pv2_power"] = inv_regs[43]
                data["pv3_power"] = inv_regs[44]
                # 0x052D: Total DC PV Power (no scaling) - DC-coupled PV total
                data["pv_dc_power_total"] = inv_regs[45]

                # Combine DC + AC PV power for true total
                # DC from 0x052D, AC from 0x00A1-0x00A2
                data["pv_power_total"] = data.get("pv_dc_power_total", 0) + data.get("pv_ac_power_total", 0)

                # 0x0545-0x0546: INV Active Power (int32, no scaling)
                data["inv_power_active"] = self._to_signed_32(inv_regs[69], inv_regs[70])
                # 0x055B-0x055C: Backup Power (int32, no scaling)
                data["backup_power"] = self._to_signed_32(inv_regs[91], inv_regs[92])
            else:
                # Fallback: if inverter registers fail, use AC-only for pv_power_total
                data["pv_dc_power_total"] = 0
                data["pv_power_total"] = data.get("pv_ac_power_total", 0)

            # AC-coupled PV (0x08D0) - CRITICAL FIX
            pv_inv_regs = self.client.read_holding_registers(0x08D0, 2)
            ac_pv_energy = None  # Track if we got a valid reading
            
            if pv_inv_regs:
                # Successfully read register - use the value
                ac_pv_energy = self._to_unsigned_32(pv_inv_regs[0], pv_inv_regs[1]) * 0.01
                data["pv_inverter_energy"] = ac_pv_energy
                # Update last known value
                self._last_known_total_energy = ac_pv_energy
                _LOGGER.debug(f"Read PV inverter energy: {ac_pv_energy} kWh")
            else:
                # Failed to read - use preserved value
                _LOGGER.warning("Failed to read PV inverter energy register - using preserved value")
                if self._last_known_total_energy is not None:
                    ac_pv_energy = self._last_known_total_energy
                    data["pv_inverter_energy"] = self._last_known_total_energy
                    _LOGGER.info(f"Using last known PV inverter energy: {self._last_known_total_energy} kWh")
                else:
                    # No preserved value - first run after restart during outage
                    ac_pv_energy = 0
                    data["pv_inverter_energy"] = 0
                    _LOGGER.warning("No preserved PV energy value available - using 0")

            # Calculate combined daily PV energy (DC + AC)
            # DC from total_pv_energy (0x050A), AC from pv_inverter_energy (0x08D0)
            dc_pv_energy = data.get("total_pv_energy", 0)
            combined_pv_energy = dc_pv_energy + (ac_pv_energy if ac_pv_energy is not None else 0)

            # Track if we need to save persistent data
            save_needed = False

            # Calculate daily energy with proper handling of unavailability
            if combined_pv_energy > 0:
                daily_pv, data_changed = self._calculate_daily_pv_energy(combined_pv_energy)
                data["pv_inverter_energy_today"] = daily_pv
                if data_changed:
                    save_needed = True
                _LOGGER.debug(f"Calculated daily PV: {daily_pv} kWh (from combined: {combined_pv_energy} kWh)")
            elif self._daily_energy_before_unavailable is not None:
                # Source unavailable but we have preserved value
                data["pv_inverter_energy_today"] = self._daily_energy_before_unavailable
                _LOGGER.info(f"Preserving daily PV energy during unavailability: {self._daily_energy_before_unavailable} kWh")
            else:
                # No data at all - shouldn't happen but be defensive
                data["pv_inverter_energy_today"] = 0
                _LOGGER.warning("No PV energy data available - setting daily to 0")

            # Save persistent data if anything changed (with debouncing)
            if save_needed:
                # Schedule save on the event loop (we're in executor thread)
                self.hass.loop.call_soon_threadsafe(self._save_persistent_data)

            # Settings (0x0800-0x0855)
            settings_regs = self.client.read_holding_registers(0x0800, 86)
            if settings_regs:
                data["max_feed_to_grid"] = settings_regs[0]
                # PV Capacity (0x0801-0x0802, 32-bit in Watts)
                data["pv_capacity"] = (settings_regs[1] << 16) | settings_regs[2]
                data["charging_cutoff_soc"] = settings_regs[85]
                data["discharging_cutoff_soc"] = settings_regs[80]
                data["time_period_control_flag"] = settings_regs[79]

            # Dispatch status (0x0880-0x0888)
            dispatch_regs = self.client.read_holding_registers(0x0880, 9)
            if dispatch_regs:
                data["dispatch_start"] = dispatch_regs[0]
                # Power is offset by 32000 (negative = charging, positive = discharging)
                power_raw = self._to_unsigned_32(dispatch_regs[1], dispatch_regs[2])
                data["dispatch_power"] = power_raw - 32000

            # Calculate house load only if we have all critical data
            if all([successful_reads["pv"], successful_reads["battery"], successful_reads["grid"]]):
                pv_power = data.get("pv_power_total", 0)
                battery_power = data.get("battery_power", 0)
                grid_power = data.get("grid_power_total", 0)

                house_load = pv_power + battery_power + grid_power

                # Handle negative house load (valid in multi-inverter systems)
                if house_load < 0:
                    _LOGGER.debug(
                        f"House load calculation resulted in negative value ({house_load}W). "
                        f"PV={pv_power}W, Battery={battery_power}W, Grid={grid_power}W. "
                        "This is expected in multi-inverter setups where grid meter is system-wide."
                    )
                    data["total_house_load"] = house_load
                    # Track excess export from unmonitored sources (e.g., slave inverter)
                    data["excess_grid_export"] = abs(house_load)
                else:
                    data["total_house_load"] = house_load
                    data["excess_grid_export"] = 0
            else:
                # Don't calculate house load if we're missing critical data
                _LOGGER.debug("Insufficient data for house load calculation - setting to None")
                data["total_house_load"] = None
            
            # Current PV production (sum of all strings)
            data["current_pv_production"] = data.get("pv1_power", 0) + data.get("pv2_power", 0) + data.get("pv3_power", 0)

            _LOGGER.debug(f"Successfully fetched data: {len(data)} keys")
            return data

        except Exception as err:
            _LOGGER.error(f"Error fetching data: {err}")
            raise

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
    def _to_signed(value):
        """Convert unsigned 16-bit to signed."""
        if value > 32767:
            return value - 65536
        return value

    @staticmethod
    def _to_signed_32(high, low):
        """Convert two 16-bit registers to signed 32-bit."""
        value = (high << 16) | low
        if value > 2147483647:
            return value - 4294967296
        return value

    @staticmethod
    def _to_unsigned_32(high, low):
        """Convert two 16-bit registers to unsigned 32-bit."""
        return (high << 16) | low