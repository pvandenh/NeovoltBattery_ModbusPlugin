"""Button platform for Neovolt Solar Inverter."""
from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DEVICE_ROLE_FOLLOWER,
    DISPATCH_RESET_VALUES,
    DOMAIN,
    SYSTEM_TIME_YYMM_REGISTER,
    SYSTEM_TIME_DDHH_REGISTER,
    SYSTEM_TIME_MMSS_REGISTER,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Neovolt buttons."""
    device_role = hass.data[DOMAIN][entry.entry_id]["device_role"]

    # Skip control entities for follower devices
    if device_role == DEVICE_ROLE_FOLLOWER:
        return

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    device_name = hass.data[DOMAIN][entry.entry_id]["device_name"]

    buttons = [
        NeovoltStopForceChargeDischargeButton(coordinator, device_info, device_name, client, hass),
        NeovoltSyncSystemClockButton(coordinator, device_info, device_name, client, hass),
    ]

    async_add_entities(buttons)


class NeovoltStopForceChargeDischargeButton(CoordinatorEntity, ButtonEntity):
    """Stop Force Charge/Discharge button - stops all force charge/discharge operations."""

    def __init__(self, coordinator, device_info, device_name, client, hass):
        """Initialize the button."""
        super().__init__(coordinator)
        self._client = client
        self._hass = hass
        self._attr_name = f"Neovolt {device_name} Stop Force Charge/Discharge"
        self._attr_unique_id = f"neovolt_{device_name}_stop_force_charge_discharge"
        self._attr_icon = "mdi:stop-circle"
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Return True if coordinator has valid cached data."""
        return self.coordinator.has_valid_data

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            _LOGGER.info("Stopping all force charge/discharge operations")

            # Stop dynamic export manager if running
            if hasattr(self.coordinator, 'dynamic_export_manager'):
                try:
                    await self.coordinator.dynamic_export_manager.stop()
                    _LOGGER.info("Stopped Dynamic Export manager")
                except Exception as e:
                    _LOGGER.debug(f"Dynamic Export manager not running or already stopped: {e}")

            # Stop dynamic import manager if running
            if hasattr(self.coordinator, 'dynamic_import_manager'):
                try:
                    await self.coordinator.dynamic_import_manager.stop()
                    _LOGGER.info("Stopped Dynamic Import manager")
                except Exception as e:
                    _LOGGER.debug(f"Dynamic Import manager not running or already stopped: {e}")

            await self._hass.async_add_executor_job(
                self._client.write_registers, 0x0880, DISPATCH_RESET_VALUES
            )
            # Optimistic update - show stopped state immediately
            self.coordinator.set_optimistic_value("dispatch_start", 0)
            self.coordinator.set_optimistic_value("dispatch_power", 0)
            self.coordinator.set_optimistic_value("dispatch_mode", 0)
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error(f"Failed to stop force charge/discharge: {e}")


class NeovoltSyncSystemClockButton(CoordinatorEntity, ButtonEntity):
    """Synchronise inverter system clock to Home Assistant time.

    Writes the current local time into the three packed-hex system-clock
    registers (0x0740–0x0742), using exactly the same encoding that the
    AlphaESS integration uses:

      0x0740  →  0xYYMM  (year offset from 2000, month)
      0x0741  →  0xDDHH  (day of month, hour)
      0x0742  →  0xmmss  (minute, second)

    Each 16-bit register packs two decimal fields into the high and low
    bytes as plain decimal values — e.g. year 2025, month 4 → 0x2504 = 9476.
    """

    def __init__(self, coordinator, device_info, device_name, client, hass):
        """Initialize the button."""
        super().__init__(coordinator)
        self._client = client
        self._hass = hass
        self._attr_name = f"Neovolt {device_name} Sync System Clock"
        self._attr_unique_id = f"neovolt_{device_name}_sync_system_clock"
        self._attr_icon = "mdi:clock-check-outline"
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Return True if coordinator has valid cached data."""
        return self.coordinator.has_valid_data

    async def async_press(self) -> None:
        """Write the current HA local time to the inverter clock registers."""
        try:
            now: datetime = dt_util.now()

            year_offset = now.year - 2000  # e.g. 2025 → 25

            # Pack two decimal values into one 16-bit register using the same
            # formula as the AlphaESS YAML:
            #   int( hex(HH) + hex(LL), base=16 )
            # where HH and LL are zero-padded two-digit decimal strings.
            def pack(high: int, low: int) -> int:
                """Pack two decimal fields into a single 16-bit register value."""
                return int(f"{high:02d}{low:02d}", 16)

            yymm = pack(year_offset, now.month)
            ddhh = pack(now.day,     now.hour)
            mmss = pack(now.minute,  now.second)

            _LOGGER.info(
                f"Syncing inverter clock to {now.strftime('%Y-%m-%d %H:%M:%S')} "
                f"(YYMM=0x{yymm:04X}, DDHH=0x{ddhh:04X}, MMSS=0x{mmss:04X})"
            )

            # Write each register individually — matches the AlphaESS approach
            # of three separate modbus.write_register calls, ensuring each
            # write is acknowledged before the next one is sent.
            await self._hass.async_add_executor_job(
                self._client.write_register, SYSTEM_TIME_YYMM_REGISTER, yymm
            )
            await self._hass.async_add_executor_job(
                self._client.write_register, SYSTEM_TIME_DDHH_REGISTER, ddhh
            )
            await self._hass.async_add_executor_job(
                self._client.write_register, SYSTEM_TIME_MMSS_REGISTER, mmss
            )

            _LOGGER.info("Inverter system clock synchronised successfully")

        except Exception as e:
            _LOGGER.error(f"Failed to sync inverter system clock: {e}")