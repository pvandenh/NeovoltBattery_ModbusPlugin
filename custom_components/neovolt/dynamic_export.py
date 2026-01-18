"""Dynamic Export Manager for Neovolt Solar Inverter.

This module manages the Dynamic Export dispatch mode, which continuously
adjusts battery discharge to maintain load + target export power.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    CONF_MAX_DISCHARGE_POWER,
    DEFAULT_MAX_DISCHARGE_POWER,
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
    """Manages Dynamic Export mode - continuous adjustment of battery discharge."""

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

        # Get max discharge power from config entry
        entry = None
        for config_entry in hass.config_entries.async_entries("neovolt"):
            if config_entry.data.get("device_name") == device_name:
                entry = config_entry
                break

        if entry:
            self._max_discharge_power = entry.data.get(
                CONF_MAX_DISCHARGE_POWER, DEFAULT_MAX_DISCHARGE_POWER
            )
        else:
            self._max_discharge_power = DEFAULT_MAX_DISCHARGE_POWER

        _LOGGER.info(
            f"Initialized Dynamic Export Manager for {device_name} "
            f"(max discharge: {self._max_discharge_power}kW)"
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

        _LOGGER.info("Starting Dynamic Export mode")
        self._running = True
        self._last_update_time = None
        self._last_commanded_power = 0.0

        # Start the control loop
        self._task = asyncio.create_task(self._control_loop())

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
        try:
            while self._running:
                try:
                    await self._update_discharge_power()
                except Exception as e:
                    _LOGGER.error(f"Error in Dynamic Export control loop: {e}", exc_info=True)

                # Wait for next update interval
                await asyncio.sleep(DYNAMIC_EXPORT_UPDATE_INTERVAL)

        except asyncio.CancelledError:
            _LOGGER.debug("Dynamic Export control loop cancelled")
            raise

    async def _update_discharge_power(self) -> None:
        """Calculate and update discharge power based on current load and PV generation."""
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
        pv_production_w = data.get("current_pv_production", 0)

        # Validate we have load data
        if current_load_w is None:
            _LOGGER.warning("Cannot calculate Dynamic Export - house load unavailable")
            return

        # Calculate net load (load minus PV contribution)
        # PV offsets the load, so we need less battery discharge
        net_load_w = current_load_w - pv_production_w

        # Handle negative load (in multi-inverter setups, this can happen)
        if current_load_w < 0:
            _LOGGER.debug(
                f"House load is negative ({current_load_w}W) - common in multi-inverter setups. "
                f"PV: {pv_production_w}W, Net load: {net_load_w}W. "
                "Setting discharge to target export only."
            )
            # Just export the target amount
            target_discharge_kw = target_export_kw
        else:
            # Normal case: discharge = (load - PV) + target export
            # This ensures we export the target amount while PV covers what it can
            target_discharge_kw = (net_load_w / 1000.0) + target_export_kw
            
            # If net load is negative (PV producing more than load), 
            # we only need to discharge enough to reach target export
            if net_load_w < 0:
                # PV is already exporting, we just need to add enough to reach target
                target_discharge_kw = target_export_kw

        # Clamp to min/max discharge power
        # Note: minimum is 0 (not 0.5) to allow zero discharge when PV covers everything
        target_discharge_kw = max(0.0, min(target_discharge_kw, self._max_discharge_power))
        
        # If target is below minimum inverter discharge (0.5kW), stop discharging
        if target_discharge_kw < 0.5:
            _LOGGER.info(
                f"Calculated discharge {target_discharge_kw:.2f}kW is below minimum (0.5kW). "
                f"PV ({pv_production_w}W) is covering load. Stopping Dynamic Export."
            )
            # Stop dispatch to avoid unnecessary battery cycles
            await self._stop_dispatch()
            return

        # Check if update is needed (debouncing)
        power_change_kw = abs(target_discharge_kw - self._last_commanded_power)

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

        # Send discharge command
        await self._send_discharge_command(target_discharge_kw, soc_cutoff)

        # Update tracking
        self._last_commanded_power = target_discharge_kw
        self._last_update_time = now

        _LOGGER.info(
            f"Dynamic Export: Load={current_load_w}W, PV={pv_production_w}W, "
            f"Net Load={(current_load_w - pv_production_w)}W, Target Export={target_export_kw}kW, "
            f"Commanded Discharge={target_discharge_kw:.2f}kW, Cutoff SOC={soc_cutoff}%"
        )

    async def _send_discharge_command(self, power_kw: float, soc_cutoff: int) -> None:
        """Send force discharge command to inverter.

        Args:
            power_kw: Discharge power in kW
            soc_cutoff: SOC cutoff percentage (0-100)
        """
        power_watts = int(power_kw * 1000)
        soc_value = soc_percent_to_register(soc_cutoff)

        # Build dispatch command for force discharge
        # Use extended timeout (10 minutes) to prevent premature expiry
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

    async def _stop_dispatch(self) -> None:
        """Stop dispatch and exit Dynamic Export mode."""
        from .const import DISPATCH_RESET_VALUES
        
        _LOGGER.info("Stopping Dynamic Export - PV is covering load")
        
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