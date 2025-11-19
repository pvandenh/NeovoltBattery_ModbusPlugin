"""Constants for the Neovolt Solar Inverter integration."""

DOMAIN = "neovolt"

DEFAULT_NAME = "Neovolt"
DEFAULT_PORT = 502
DEFAULT_SLAVE_ID = 85

CONF_SLAVE_ID = "slave_id"

# Max power configuration
CONF_MAX_CHARGE_POWER = "max_charge_power"
CONF_MAX_DISCHARGE_POWER = "max_discharge_power"

# Default power limits (in kW)
DEFAULT_MAX_CHARGE_POWER = 5.0
DEFAULT_MAX_DISCHARGE_POWER = 5.0
MIN_POWER = 0.5
MAX_POWER_LIMIT = 100.0  # 100kW max for safety (supports parallel systems)