"""Constants for the Neovolt Solar Inverter integration."""
from dataclasses import dataclass

DOMAIN = "neovolt"

DEFAULT_NAME = "Neovolt"
DEFAULT_PORT = 502
DEFAULT_SLAVE_ID = 85

CONF_SLAVE_ID = "slave_id"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_ROLE = "device_role"

# Device roles
DEVICE_ROLE_HOST = "host"
DEVICE_ROLE_FOLLOWER = "follower"

# Max power configuration
CONF_MAX_CHARGE_POWER = "max_charge_power"
CONF_MAX_DISCHARGE_POWER = "max_discharge_power"

# Default power limits (in kW)
DEFAULT_MAX_CHARGE_POWER = 5.0
DEFAULT_MAX_DISCHARGE_POWER = 5.0
MIN_POWER = 0.5
MAX_POWER_LIMIT = 100.0  # 100kW max for safety (supports parallel systems)

# Dynamic Export mode configuration
CONF_DYNAMIC_EXPORT_TARGET = "dynamic_export_target"
DEFAULT_DYNAMIC_EXPORT_TARGET = 1.0  # 1kW above load by default
DYNAMIC_EXPORT_UPDATE_INTERVAL = 10  # seconds between power adjustments
DYNAMIC_EXPORT_DEBOUNCE_THRESHOLD = 0.3  # kW - only update if change > this

# CRITICAL: Command refresh interval for dispatch operations
# This controls how frequently dispatch commands are re-sent to maintain state
# Shorter = more responsive to manual changes, longer = less Modbus traffic
DISPATCH_COMMAND_REFRESH_INTERVAL = 30  # seconds (re-send command every 30s)

# CRITICAL: Command timeout must be LONGER than refresh interval to prevent gaps
# Timeout = refresh interval + safety buffer to ensure continuous operation
DISPATCH_COMMAND_TIMEOUT = 90  # seconds (3x refresh interval for safety)

# SOC (State of Charge) conversion constants
SOC_CONVERSION_FACTOR = 2.55  # Multiplier to convert percentage to register value
MIN_SOC_PERCENT = 0.0
MAX_SOC_PERCENT = 100.0
MIN_SOC_REGISTER = 0
MAX_SOC_REGISTER = 255  # Full 8-bit range

# Modbus dispatch command constants
MODBUS_OFFSET = 32000

# Dispatch control modes
DISPATCH_MODE_POWER_ONLY = 0  # Control by power only
DISPATCH_MODE_POWER_WITH_SOC = 2  # Control by power with SOC limit
DISPATCH_MODE_DYNAMIC_EXPORT = 99  # Custom mode for dynamic export (internal only)

# Dispatch command duration default (seconds)
# IMPORTANT: Must be longer than refresh interval to maintain continuous operation
DISPATCH_DURATION_DEFAULT = DISPATCH_COMMAND_TIMEOUT

# Dispatch reset command (11 registers: Para1-Para8)
DISPATCH_RESET_VALUES = [0, 0, MODBUS_OFFSET, 0, MODBUS_OFFSET, 0, 0, 0, DISPATCH_DURATION_DEFAULT, 255, 0]

# Polling configuration
CONF_MIN_POLL_INTERVAL = "min_poll_interval"
CONF_MAX_POLL_INTERVAL = "max_poll_interval"
CONF_CONSECUTIVE_FAILURE_THRESHOLD = "consecutive_failure_threshold"
CONF_STALENESS_THRESHOLD = "staleness_threshold"

# Polling defaults
DEFAULT_MIN_POLL_INTERVAL = 10    # seconds (hard minimum)
DEFAULT_MAX_POLL_INTERVAL = 300   # 5 minutes
DEFAULT_POLL_INTERVAL = 30        # starting interval for all blocks
DEFAULT_CONSECUTIVE_FAILURES = 5
DEFAULT_STALENESS_THRESHOLD = 10  # minutes
RECOVERY_COOLDOWN_SECONDS = 60    # cooldown between recovery attempts

# Hard limits for polling configuration
MIN_POLL_INTERVAL_LIMIT = 10      # Cannot go below 10 seconds
MAX_POLL_INTERVAL_LIMIT = 3600    # Cannot exceed 1 hour

# Keys for storing persistent data in config entry options
STORAGE_LAST_RESET_DATE = "last_reset_date"
STORAGE_MIDNIGHT_BASELINE = "pv_inverter_energy_at_midnight"
STORAGE_LAST_KNOWN_TOTAL = "last_known_total_energy"
STORAGE_DAILY_PRESERVED = "daily_energy_before_unavailable"


@dataclass
class RegisterBlock:
    """Definition of a Modbus register block for polling."""
    name: str
    address: int
    count: int


# Register blocks for adaptive polling
# Each block is polled independently with its own adaptive interval
REGISTER_BLOCKS = {
    "grid": RegisterBlock("grid", 0x0010, 39),
    "pv": RegisterBlock("pv", 0x0090, 20),
    "battery": RegisterBlock("battery", 0x0100, 40),
    "inverter": RegisterBlock("inverter", 0x0500, 110),
    "pv_inverter_energy": RegisterBlock("pv_inverter_energy", 0x08D0, 2),
    "settings": RegisterBlock("settings", 0x0800, 86),
    "dispatch": RegisterBlock("dispatch", 0x0880, 11),  # Para1-Para8 (11 registers)
}