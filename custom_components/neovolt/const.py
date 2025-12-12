"""Constants for the Neovolt Solar Inverter integration."""

DOMAIN = "neovolt"

DEFAULT_NAME = "Neovolt"
DEFAULT_PORT = 502
DEFAULT_SLAVE_ID = 85

CONF_SLAVE_ID = "slave_id"
CONF_DEVICE_NAME = "device_name"

# Max power configuration
CONF_MAX_CHARGE_POWER = "max_charge_power"
CONF_MAX_DISCHARGE_POWER = "max_discharge_power"

# Default power limits (in kW)
DEFAULT_MAX_CHARGE_POWER = 5.0
DEFAULT_MAX_DISCHARGE_POWER = 5.0
MIN_POWER = 0.5
MAX_POWER_LIMIT = 100.0  # 100kW max for safety (supports parallel systems)

# SOC (State of Charge) conversion constants
# The inverter stores SOC as a value from 0-255, where 255 = 100%
# Conversion factor: SOC% / 0.392157 = register value (0-255)
SOC_CONVERSION_FACTOR = 0.392157
MIN_SOC_PERCENT = 0.0
MAX_SOC_PERCENT = 100.0
MIN_SOC_REGISTER = 0
MAX_SOC_REGISTER = 255

# Modbus dispatch command constants
# Power values are offset by 32000 in the dispatch protocol
# Positive offset (32000 + watts) = charge, Negative offset (32000 - watts) = discharge
MODBUS_OFFSET = 32000

# Dispatch control modes
DISPATCH_MODE_POWER_ONLY = 0  # Control by power only
DISPATCH_MODE_POWER_WITH_SOC = 2  # Control by power with SOC limit

# Dispatch command duration default (seconds)
# Used when resetting dispatch - maintains previous command for 90 seconds
DISPATCH_DURATION_DEFAULT = 90

# Dispatch reset command
# Format: [mode, reserved, charge_power, reserved, discharge_power, soc_mode, soc_value, reserved, duration]
# This command resets to idle state with 90s timeout
DISPATCH_RESET_VALUES = [0, 0, MODBUS_OFFSET, 0, MODBUS_OFFSET, 0, 0, 0, DISPATCH_DURATION_DEFAULT]