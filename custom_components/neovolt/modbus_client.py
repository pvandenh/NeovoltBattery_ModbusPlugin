"""Modbus client for Neovolt/Bytewatt inverter - FIXED FOR PYMODBUS 3.11.2"""
import logging
import threading
import time
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException, ConnectionException

_LOGGER = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 0.5  # seconds
MAX_RETRY_DELAY = 5.0  # seconds


class NeovoltModbusClient:
    """Modbus TCP client for Neovolt/Bytewatt inverter."""
    
    def __init__(self, host, port, slave_id):
        """Initialize the Modbus client."""
        self.host = host
        self.port = port
        self.slave_id = slave_id
        self.client = None
        self._lock = threading.Lock()  # Protect connection state
        self._last_error = None  # Track last error to avoid log spam
        self._consecutive_errors = 0  # Track error count
        _LOGGER.info(f"Initialized Modbus client for {host}:{port} (slave: {slave_id})")

    @staticmethod
    def _is_transient_error(exception):
        """
        Determine if an error is transient (can be retried) or permanent.

        Transient errors: Network issues, timeouts, temporary unavailability
        Permanent errors: Configuration errors, unsupported operations

        Args:
            exception: The exception to classify

        Returns:
            True if error is likely transient and should be retried
        """
        # Network and connection errors are typically transient
        if isinstance(exception, (ConnectionException, ConnectionError, TimeoutError, OSError)):
            return True

        # Modbus-specific transient errors
        if isinstance(exception, ModbusException):
            error_str = str(exception).lower()
            # These indicate temporary issues
            transient_keywords = ['timeout', 'connection', 'unreachable', 'refused', 'reset']
            if any(keyword in error_str for keyword in transient_keywords):
                return True

        # All other errors are considered permanent
        return False

    def _retry_operation(self, operation, operation_name, *args, **kwargs):
        """
        Execute an operation with retry logic for transient errors.

        Args:
            operation: The function to call
            operation_name: Name of operation for logging
            *args, **kwargs: Arguments to pass to the operation

        Returns:
            Result of the operation, or None if all retries fail
        """
        retry_delay = INITIAL_RETRY_DELAY
        last_exception = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = operation(*args, **kwargs)

                # Reset error tracking on success
                if self._consecutive_errors > 0:
                    _LOGGER.info(
                        f"{operation_name} succeeded after {self._consecutive_errors} consecutive errors"
                    )
                    self._consecutive_errors = 0
                    self._last_error = None

                return result

            except Exception as e:
                last_exception = e
                is_transient = self._is_transient_error(e)

                # Log appropriately based on error type and attempt
                if attempt < MAX_RETRIES and is_transient:
                    _LOGGER.warning(
                        f"{operation_name} failed (attempt {attempt}/{MAX_RETRIES}): {e}. "
                        f"Retrying in {retry_delay:.1f}s..."
                    )
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)  # Exponential backoff
                else:
                    # Permanent error or final attempt
                    error_type = "transient" if is_transient else "permanent"

                    # Only log if this is a new error or significant change
                    error_signature = f"{type(e).__name__}:{str(e)}"
                    if error_signature != self._last_error:
                        _LOGGER.error(
                            f"{operation_name} failed ({error_type} error): {e}"
                        )
                        self._last_error = error_signature
                        self._consecutive_errors = 1
                    else:
                        self._consecutive_errors += 1
                        # Only log every 10th consecutive error to reduce spam
                        if self._consecutive_errors % 10 == 0:
                            _LOGGER.error(
                                f"{operation_name} failed {self._consecutive_errors} consecutive times: {e}"
                            )
                    break

        return None

    def connect(self):
        """Establish connection to the Modbus device."""
        try:
            self.client = ModbusTcpClient(
                host=self.host,
                port=self.port,
                timeout=10
            )
            connected = self.client.connect()
            if connected:
                _LOGGER.info(f"Connected to Modbus device at {self.host}:{self.port}")
            else:
                _LOGGER.error(f"Failed to connect to Modbus device at {self.host}:{self.port}")
            return connected
        except Exception as e:
            _LOGGER.error(f"Connection error for {self.host}:{self.port}: {e}")
            return False
    
    def test_connection(self):
        """Test connection by reading Battery SOC register (0x0102)."""
        try:
            with self._lock:
                if not self.client:
                    if not self.connect():
                        return False

                _LOGGER.info(f"Testing connection to {self.host}:{self.port}")

                # Check if client is connected
                if not self.client.connected:
                    _LOGGER.info("TCP not connected, attempting connection...")
                    if not self.connect():
                        return False

            _LOGGER.info("TCP connected! Reading SOC register...")

            # CORRECT pymodbus 3.x API - uses device_id parameter (not slave/unit)
            result = self.client.read_holding_registers(
                address=0x0102,         # Battery SOC register
                count=1,                # Read 1 register
                device_id=self.slave_id # pymodbus 3.x uses 'device_id' not 'slave' or 'unit'
            )

            if result.isError():
                _LOGGER.error(f"Modbus error reading register: {result}")
                return False

            soc_value = result.registers[0]
            _LOGGER.info(f"Connection successful! Battery SOC: {soc_value * 0.1}%")
            return True

        except ModbusException as e:
            _LOGGER.error(f"Modbus exception during test: {e}")
            return False
        except AttributeError as e:
            _LOGGER.error(f"API compatibility error: {e}")
            _LOGGER.error("This may indicate pymodbus version incompatibility")
            return False
        except Exception as e:
            _LOGGER.error(f"Connection test failed: {e}")
            return False
    
    def read_holding_registers(self, address, count):
        """
        Read holding registers from the device with retry logic.

        Args:
            address: Starting register address (hex)
            count: Number of registers to read

        Returns:
            List of register values or None on error
        """
        def _read_operation():
            with self._lock:
                if not self.client or not self.client.connected:
                    if not self.connect():
                        raise ConnectionException(
                            f"Failed to establish connection to {self.host}:{self.port}"
                        )

            result = self.client.read_holding_registers(
                address=address,
                count=count,
                device_id=self.slave_id
            )

            if result.isError():
                raise ModbusException(f"Modbus error reading registers {hex(address)}: {result}")

            return result.registers

        operation_name = f"Read registers {hex(address)}"
        return self._retry_operation(_read_operation, operation_name)
    
    def write_register(self, address, value):
        """
        Write a single register to the device with retry logic.

        Args:
            address: Register address (hex)
            value: Value to write

        Returns:
            True if successful, False otherwise
        """
        def _write_operation():
            with self._lock:
                if not self.client or not self.client.connected:
                    if not self.connect():
                        raise ConnectionException(
                            f"Failed to establish connection to {self.host}:{self.port}"
                        )

            result = self.client.write_register(
                address=address,
                value=value,
                device_id=self.slave_id
            )

            if result.isError():
                raise ModbusException(f"Modbus error writing register {hex(address)}: {result}")

            _LOGGER.debug(f"Successfully wrote {value} to register {hex(address)}")
            return True

        operation_name = f"Write register {hex(address)}"
        result = self._retry_operation(_write_operation, operation_name)
        return result if result is not None else False
    
    def write_registers(self, address, values):
        """
        Write multiple registers to the device with retry logic.

        Args:
            address: Starting register address (hex)
            values: List of values to write

        Returns:
            True if successful, False otherwise
        """
        def _write_operation():
            with self._lock:
                if not self.client or not self.client.connected:
                    if not self.connect():
                        raise ConnectionException(
                            f"Failed to establish connection to {self.host}:{self.port}"
                        )

            result = self.client.write_registers(
                address=address,
                values=values,
                device_id=self.slave_id
            )

            if result.isError():
                raise ModbusException(f"Modbus error writing registers {hex(address)}: {result}")

            _LOGGER.debug(f"Successfully wrote {len(values)} values starting at {hex(address)}")
            return True

        operation_name = f"Write registers {hex(address)}"
        result = self._retry_operation(_write_operation, operation_name)
        return result if result is not None else False
    
    def close(self):
        """Close the Modbus connection."""
        if self.client:
            self.client.close()
            _LOGGER.info(f"Closed connection to {self.host}:{self.port}")