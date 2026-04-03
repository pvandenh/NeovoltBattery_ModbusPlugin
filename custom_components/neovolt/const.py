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
MIN_POWER = 0.05  # Lowered to allow gentle trickle export (50W) for zero-import bias correction
MAX_POWER_LIMIT = 100.0  # 100kW max for safety (supports parallel systems)

# Dynamic Export/Import mode configuration
CONF_DYNAMIC_EXPORT_TARGET = "dynamic_export_target"
DEFAULT_DYNAMIC_EXPORT_TARGET = 0.05  # 50W default — gentle trickle to stay on export side
DYNAMIC_EXPORT_MIN_POWER = 0.05       # 50W minimum — allows zero-import bias correction
DYNAMIC_EXPORT_MAX_POWER = 15.0  # 15kW max to support extended system configurations
DYNAMIC_EXPORT_UPDATE_INTERVAL = 10  # seconds — control loop poll rate (do not raise)
DYNAMIC_EXPORT_SETTLE_SECONDS = 30   # seconds to wait after a command before adjusting again
DYNAMIC_EXPORT_MAX_STEP_KW = 1.0     # kW — max power change per adjustment step

# SOC (State of Charge) conversion constants
# FIXED: According to Modbus protocol, dispatch SOC uses full 8-bit range (0-255)
# Reading battery SOC uses 0.1 multiplier (register 0x0102), but dispatch Para5 uses 0-255 range
# Conversion: SOC% × 2.55 = register value (0-255)
# Examples: 0% = 0, 50% = 127.5 ≈ 128, 100% = 255
SOC_CONVERSION_FACTOR = 2.55  # Multiplier to convert percentage to register value
MIN_SOC_PERCENT = 0.0
MAX_SOC_PERCENT = 100.0
MIN_SOC_REGISTER = 0
MAX_SOC_REGISTER = 255  # FIXED: Was 250, now 255 for full range

# Modbus dispatch command constants
# Power values are offset by 32000 in the dispatch protocol
# Positive offset (32000 + watts) = discharge, Negative offset (32000 - watts) = charge
MODBUS_OFFSET = 32000

# Dispatch control modes (Para4 values sent to the inverter hardware)
DISPATCH_MODE_POWER_ONLY = 0       # Control by power only
DISPATCH_MODE_POWER_WITH_SOC = 2   # Control by power with SOC limit
DISPATCH_MODE_NO_CHARGE = 19       # Mode 19: Prevent all battery charging (solar & grid)
#
# NOTE: Mode 20 was tested and found to trigger full-rate Force Charge on this firmware.
# It is NOT used. Do not send Mode 20 to the inverter.

# Internal-only tracking mode constants — NEVER sent to the inverter as Para4.
# These are stored in coordinator data (dispatch_mode key) to distinguish
# software-managed modes that share a hardware Para4 value with other modes.
# Values are chosen well outside the known valid hardware range (0-19).
DISPATCH_MODE_DYNAMIC_EXPORT = 99   # Dynamic Export  (hardware: Mode 2 + calculated power)
DISPATCH_MODE_DYNAMIC_IMPORT = 98   # Dynamic Import  (hardware: Mode 2 + calculated power)
DISPATCH_MODE_NO_DISCHARGE = 97     # No Battery Discharge (hardware: Mode 2 + zero power)

# Dispatch command duration default (seconds)
# Used when resetting dispatch - maintains previous command for 90 seconds
DISPATCH_DURATION_DEFAULT = 90

# Dispatch reset command (11 registers: Para1-Para8)
# Format: [Para1, Para2_hi, Para2_lo, Para3_hi, Para3_lo, Para4, Para5, Para6_hi, Para6_lo, Para7, Para8]
# This command resets to idle state with 90s timeout
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
# These are runtime data that should NOT trigger integration reload
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
    "parallel_versions": RegisterBlock("parallel_versions", 0x0640, 10),
    "pv_inverter_energy": RegisterBlock("pv_inverter_energy", 0x08D0, 6),  # Extended to include system_fault at 0x08D4
    "settings": RegisterBlock("settings", 0x0800, 99),
    "dispatch": RegisterBlock("dispatch", 0x0880, 11),  # Para1-Para8 (11 registers)
    "safety_config": RegisterBlock("safety_config", 0x1000, 1),
    "parallel_config": RegisterBlock("parallel_config", 0x3090, 3),
    "calibration": RegisterBlock("calibration", 0x11D3, 3),  # AlphaESS-shared: point1, coef1, offset1
}

# ─── Combined (host + follower) data keys ────────────────────────────────────
# These keys are written into the host coordinator's data dict by
# _calculate_derived_values() when a follower coordinator is linked.
# They are used by Dynamic Export and exposed as sensors on the host device.
COMBINED_BATTERY_POWER = "combined_battery_power"       # W  — sum of both packs
COMBINED_BATTERY_SOC = "combined_battery_soc"           # %  — capacity-weighted average
COMBINED_BATTERY_SOH = "combined_battery_soh"           # %  — capacity-weighted average
COMBINED_BATTERY_CAPACITY = "combined_battery_capacity" # kWh — sum of both packs
COMBINED_HOUSE_LOAD = "combined_house_load"             # W  — true system house load
COMBINED_PV_POWER = "combined_pv_power"                 # W  — sum (follower usually 0)
COMBINED_BATTERY_MIN_CELL_V = "combined_battery_min_cell_voltage"   # V — min across both
COMBINED_BATTERY_MAX_CELL_V = "combined_battery_max_cell_voltage"   # V — max across both
COMBINED_BATTERY_MIN_CELL_T = "combined_battery_min_cell_temp"      # °C — min across both
COMBINED_BATTERY_MAX_CELL_T = "combined_battery_max_cell_temp"      # °C — max across both
COMBINED_BATTERY_CHARGE_E = "combined_battery_charge_energy"        # kWh — sum
COMBINED_BATTERY_DISCHARGE_E = "combined_battery_discharge_energy"  # kWh — sum

# Grid power calibration offset register (AlphaESS shared firmware, register 0x11D5)
# Signed 16-bit integer, 1W/bit resolution.
# Positive value → inverter thinks it is importing more → discharges harder → reduces grid import.
# This compensates for persistent grid balancing undershoot (small constant import at idle).
# Register is only present if the firmware exposes the AlphaESS calibration block.
# Use grid_power_offset_supported sensor to confirm the register responded before relying on it.
GRID_POWER_OFFSET_REGISTER = 0x11D5
GRID_POWER_OFFSET_MIN = -500   # W  (negative: shift balance toward import)
GRID_POWER_OFFSET_MAX = 500    # W  (positive: shift balance toward export / reduce import)


# ─── Fault / Warning / Status label maps ─────────────────────────────────────
# These map bit positions to human-readable descriptions for the diagnostic
# sensors decoded from the Modbus fault/warning registers.

# Note1: Battery status — decoded from register 0x0103
# The register encodes charge/discharge state in two fields.
BATTERY_STATUS_MAP = {
    0: "Idle",
    1: "Discharging",
    256: "Charging",
    257: "Charging & Discharging",
    512: "Charging (mode 2)",
    513: "Charging & Discharging (mode 2)",
}

# Note2: Battery relay status — decoded from register 0x0104
BATTERY_RELAY_STATUS_MAP = {
    0: "Both relays open",
    1: "Discharge relay closed",
    2: "Charge relay closed",
    3: "Both relays closed",
}

# Note4: Battery warning bits — register 0x011D (16-bit)
BATTERY_WARNING_BITS = {
    0: "Single Cell Low Voltage",
    1: "Single Cell High Voltage",
    2: "Discharge System Low Voltage",
    3: "Charge System High Voltage",
    4: "Charge Cell Low Temperature",
    5: "Charge Cell High Temperature",
    6: "Discharge Cell Low Temperature",
    7: "Discharge Cell High Temperature",
    8: "Charge Over Current",
    9: "Discharge Over Current",
    10: "Module Low Voltage",
    11: "Module High Voltage",
}

# Note5: Battery fault bits — registers 0x011E-0x011F (32-bit)
BATTERY_FAULT_BITS = {
    0: "Voltage Sensor Fault",
    1: "Temperature Sensor Error",
    2: "Internal Communication Error",
    3: "Input Over Voltage Error",
    4: "Input Transposition Error",
    5: "Relay Check Error",
    6: "Battery Cell Error (over-discharge)",
    7: "Shutdown Circuit Abnormal",
    8: "BMIC Error",
    9: "Internal Bus Error",
    10: "Self-Test Error",
    11: "Safety Function / Chip Error",
    16: "CAN External Communication Fault",
    17: "Insulation Fault",
    18: "Pre-Charge Fault",
    19: "Hardware Over Voltage",
    20: "Hardware Over Temperature",
    21: "Hardware Charge Over Current",
    22: "Hardware Discharge Over Current",
    23: "PCBA Over Temperature",
}

# Note6: Battery protection bits — register 0x011C (16-bit → treated as 32-bit in protocol)
BATTERY_PROTECTION_BITS = {
    0: "Single Cell Under Voltage Protect",
    1: "Single Cell Over Voltage Protect",
    2: "Discharge System Under Voltage Protect",
    3: "Charge System Over Voltage Protect",
    4: "Charge Cell Under Temperature Protect",
    5: "Charge Cell Over Temperature Protect",
    6: "Discharge Cell Under Temperature Protect",
    7: "Discharge Cell Over Temperature Protect",
    8: "Charge Over Current Protect",
    9: "Discharge Over Current Protect",
    10: "Module Under Voltage Protect",
    11: "Module Over Voltage Protect",
    12: "Single Cell Under Voltage Protect 2",
}

# Note7: Inverter work mode — register 0x050E
INVERTER_WORK_MODE_MAP = {
    0: "Wait",
    1: "Self-Test",
    2: "Check",
    3: "Normal",
    4: "UPS",
    5: "Bypass",
    6: "DC Mode",
    7: "Fault",
    8: "Update Master",
    9: "Update Slave",
    10: "Update ARM",
}

# Note8: System fault bits — registers 0x08D4-0x08D5 (32-bit)
SYSTEM_FAULT_BITS = {
    0: "Network Card Fault",
    1: "RTC Fault",
    2: "EEPROM Fault",
    3: "Inverter Comms Error",
    4: "Grid Meter Lost",
    5: "PV Meter Lost",
    6: "BMS Lost",
    7: "UPS Battery Voltage Low",
    8: "Backup Overload",
    9: "Inverter Slave Lost",
    10: "Inverter Master Lost",
    11: "Parallel Comm Error",
    12: "Parallel Mode Mismatch",
    13: "Flash Fault",
    14: "SDRAM Error",
    15: "Extension CAN Error",
    16: "Inverter Type Not Specified",
    17: "Inverter Lost - Battery Shutdown",
    18: "Sampling Anomaly",
    19: "Force Battery Shutdown",
}

# Note10: Inverter warning bits — registers 0x055E-0x0561 (64-bit across 4 registers)
# Only the most actionable bits are listed here; remainder are logged as raw values.
INVERTER_WARNING_BITS = {
    0: "Battery Over Voltage",
    1: "Battery Under Voltage",
    2: "Overload",
    3: "Temperature Sensor Abnormal",
    5: "Battery Stop Running",
    6: "Over Temperature",
    7: "PV Voltage High",
    8: "Battery Open Circuit",
    9: "Battery Reverse Polarity",
    10: "Bus Over Voltage",
    11: "Grid Lost",
    12: "Grid Voltage Abnormal",
    13: "Grid Frequency Abnormal",
    16: "Ground Wire Lost",
    17: "Live/Neutral Reversed",
    18: "Low Temperature",
    24: "Fan Abnormal",
    25: "Neutral Wire Lost",
    51: "Parallel Warning",
    52: "Parallel ID Error",
    54: "Parallel ID Duplicate",
    59: "Battery Count Abnormal",
}

# Note11 + Note12: Inverter fault bits — registers 0x0562-0x0569 (64-bit each block)
INVERTER_FAULT_BITS = {
    0: "Grid Over Voltage",
    1: "Grid Under Voltage",
    2: "Grid Over Frequency",
    3: "Grid Under Frequency",
    4: "Phase Lock Fault",
    5: "Bus Over Voltage (1)",
    6: "Bus Over Voltage (2)",
    7: "Insulation Fault",
    8: "GFCI Fault",
    9: "GFCI Test Fault",
    10: "Grid Relay Fault",
    11: "Over Temperature",
    12: "PV Reverse Polarity (1)",
    13: "PV Reverse Polarity (2)",
    14: "Master/Slave Comms Fault",
    15: "Display Comms Fault",
    17: "MPPT1 Over Voltage",
    18: "MPPT1 SW Over Current",
    19: "MPPT1 HW Over Current",
    20: "MPPT1 Over Temperature",
    21: "MPPT2 Over Voltage",
    23: "MPPT2 HW Over Current",
    24: "MPPT2 Over Temperature",
    25: "Battery Over Voltage",
    26: "Battery Under Voltage",
    27: "Battery Lost",
    28: "Battery Over Temperature",
    29: "Bat1 Charge Over Current",
    30: "Bat1 Discharge Over Current",
    31: "Bat2 Charge Over Current",
    32: "Bat2 Discharge Over Current",
    33: "Bat1 HW Over Current",
    34: "Bat2 HW Over Current",
    35: "Inverter Over Temperature",
    36: "Inverter Over Voltage",
    37: "Inverter Under Voltage",
    38: "Output DC Over Current",
    39: "Inverter Over Current",
    40: "Inverter HW Over Current",
    41: "Output DC Over Voltage",
    42: "Output Short Circuit",
    43: "Output Overload",
    45: "Battery Relay Fault",
    47: "Grid Disturbance",
    48: "Grid Unbalance",
    56: "IGBT Over Current",
    60: "DSP Self-Check Fault",
    62: "Battery Over Voltage HW Fault",
    63: "Zero-Ground Fault",
}

# Note12 extended fault bits (second 64-bit fault register block, 0x0566-0x0569)
# Complete mapping of all bits from the Bytewatt Modbus RTU protocol Note12.
INVERTER_FAULT_EXT_BITS = {
    0: "AC HCT Check Failure",
    1: "DCI Consistency Failure",
    2: "GFCI Consistency Failure",
    3: "Relay Device Failure",
    4: "AC HCT Failure",
    5: "Ground Current Failure",
    6: "Utility Phase Failure",
    7: "Utility Loss",
    8: "Internal Fan Failure",
    9: "FAC Consistency Failure",
    10: "VAC Consistency Failure",
    11: "Phase Angle Failure",
    12: "DSP Communication Failure",
    13: "EEPROM R/W Failure",
    14: "VAC Failure",
    15: "FAC Failure",
    16: "External Fan Failure",
    17: "AFCI Device Failure",
    18: "Bus Soft-Start Timeout",
    19: "Bus Short Circuit",
    20: "Inverter Soft-Start Timeout",
    21: "Backup/Grid Reverse Polarity",
    22: "Live/Ground Reverse Polarity",
    23: "EMS Serial Comms Error",
    24: "EMS CAN Comms Error",
    25: "12V Auxiliary Power Reference Error",
    26: "1.5V Power Error",
    27: "0.5V Power Error",
    28: "Thermistor Lost",
    29: "Inverter HCT Error",
    30: "Load CT Error",
    31: "PV1 CT Error",
    32: "PV2 CT Error",
    33: "Bat1 CT Error",
    34: "Bat2 CT Error",
    35: "Bypass Relay Error",
    36: "Load Relay Error",
    37: "NPE Relay Error",
    38: "DC Current Component Error",
    39: "Watchdog Error",
    40: "Inverter Open-Loop Error",
    41: "SW Consistency Error",
    42: "N-N Reverse Lost",
    43: "Initialisation Fault",
    44: "DSP-B Fault",
    45: "Inverter Line Abnormal",
    46: "Boost Line Abnormal / DC Soft-Start Abnormal",
    47: "Data Storage Fault",
    48: "Parallel CAN Fault",
    49: "Parallel Sync Signal Error",
    50: "Parallel Software Mismatch",
    51: "Module Mode Error",
    52: "Negative Power Fault",
    53: "Multiple Masters",
    54: "Power-On Abnormal",
    55: "Hardware Version Mismatch",
    56: "Bus Unbalance",
    57: "Inverter Line Short",
    58: "Inverter CBC Over",
    59: "Middle Bridge HW OCP",
    60: "BDC SW OCP",
    61: "BDC Pre-Charge Failure",
    62: "BDC Self-Check Failure",
    63: "PE Fault",
}
