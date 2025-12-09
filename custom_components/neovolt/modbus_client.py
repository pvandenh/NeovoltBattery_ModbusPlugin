"""Modbus client for Neovolt/Bytewatt inverter - FIXED FOR PROTOCOL COMPLIANCE"""
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

# Protocol requirements from BYTEWATT Modbus_RTU Protocol (V1.12)
PROTOCOL_COMMAND_INTERVAL = 0.3  # 300ms minimum between commands (>300ms required)
PROTOCOL_RESPONSE_TIMEOUT = 10.0  # 10 second timeout (>10S required)


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
        self._is_closing = False  # Track if we're deliberately closing
        self._last_command_time = 0  # Track time of last command for protocol compliance
        _LOGGER.info(f"Initialized Modbus client for {host}:{port} (slave: {slave_id})")

    def _enforce_command_interval(self):
        """
        Enforce minimum command interval required by protocol.
        
        BYTEWATT protocol requires >300ms between commands.
        This prevents overwhelming the device and ensures reliable communication.
        """
        current_time = time.time()
        time_since_last = current_time - self._last_command_time
        
        if time_since_last < PROTOCOL_COMMAND_INTERVAL:
            sleep_time = PROTOCOL_COMMAND_INTERVAL - time_since_last
            _LOGGER.debug(f"Enforcing protocol delay: {sleep_time:.3f}s")
            time.sleep(sleep_time)
        
        self._last_command_time = time.time()

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
            # Check if we're being closed
            if self._is_closing:
                _LOGGER.debug(f"{operation_name} cancelled - client is closing")
                return None

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
                    # Use debug level for first retry during restarts to reduce log noise
                    log_level = _LOGGER.debug if attempt == 1 else _LOGGER.warning
                    log_level(
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
                        # Use warning instead of error for transient failures during restarts
                        if is_transient and self._consecutive_errors == 0:
                            _LOGGER.warning(
                                f"{operation_name} temporarily unavailable ({error_type} error): {e}"
                            )
                        else:
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
        """Establish connection to the Modbus device with improved restart handling."""
        try:
            # Close existing connection if any
            if self.client:
                try:
                    self.client.close()
                    # Give device time to release the connection (critical for EW11A gateways)
                    time.sleep(0.2)
                except Exception:
                    pass  # Ignore errors during cleanup
            
            # Create new client with protocol-compliant timeout
            self.client = ModbusTcpClient(
                host=self.host,
                port=self.port,
                timeout=PROTOCOL_RESPONSE_TIMEOUT
            )
            
            # Try connection with brief retry for gateway connection limits
            connected = False
            for attempt in range(2):
                try:
                    connected = self.client.connect()
                    if connected:
                        break
                except (ConnectionError, OSError) as e:
                    if attempt == 0:
                        _LOGGER.debug(f"Connection attempt {attempt + 1} failed, retrying: {e}")
                        time.sleep(0.3)  # Brief wait for gateway to be ready
                    else:
                        raise
            
            if connected:
                _LOGGER.info(f"Connected to Modbus device at {self.host}:{self.port}")
                # Small delay after connection to let device stabilize
                time.sleep(0.1)
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

            # Enforce protocol delay before reading
            self._enforce_command_interval()

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
            # Check if we're being closed
            if self._is_closing:
                raise ConnectionException("Client is being closed")

            # Lock is held only during connection check to avoid blocking during I/O
            # pymodbus client itself is thread-safe for concurrent reads/writes
            # We only need to protect the connection state check/establishment
            with self._lock:
                # Additional check after acquiring lock
                if self._is_closing:
                    raise ConnectionException("Client is being closed")
                    
                if not self.client or not self.client.connected:
                    if not self.connect():
                        raise ConnectionException(
                            f"Failed to establish connection to {self.host}:{self.port}"
                        )

            # Validate client and slave_id before making the call
            if not self.client:
                raise ConnectionException("Client not initialized")
            
            if not isinstance(self.slave_id, int):
                raise ValueError(f"Invalid slave_id type: {type(self.slave_id)}. Expected int.")

            # CRITICAL: Enforce protocol command interval (>300ms between commands)
            self._enforce_command_interval()

            # I/O operation performed outside lock to allow concurrent operations
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
            # Check if we're being closed
            if self._is_closing:
                raise ConnectionException("Client is being closed")

            # Lock held only during connection check (see read_holding_registers for rationale)
            with self._lock:
                # Additional check after acquiring lock
                if self._is_closing:
                    raise ConnectionException("Client is being closed")
                    
                if not self.client or not self.client.connected:
                    if not self.connect():
                        raise ConnectionException(
                            f"Failed to establish connection to {self.host}:{self.port}"
                        )

            # Validate client and slave_id before making the call
            if not self.client:
                raise ConnectionException("Client not initialized")
            
            if not isinstance(self.slave_id, int):
                raise ValueError(f"Invalid slave_id type: {type(self.slave_id)}. Expected int.")

            # CRITICAL: Enforce protocol command interval (>300ms between commands)
            self._enforce_command_interval()

            # I/O operation performed outside lock to allow concurrent operations
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
            # Check if we're being closed
            if self._is_closing:
                raise ConnectionException("Client is being closed")

            # Lock held only during connection check (see read_holding_registers for rationale)
            with self._lock:
                # Additional check after acquiring lock
                if self._is_closing:
                    raise ConnectionException("Client is being closed")
                    
                if not self.client or not self.client.connected:
                    if not self.connect():
                        raise ConnectionException(
                            f"Failed to establish connection to {self.host}:{self.port}"
                        )

            # Validate client and slave_id before making the call
            if not self.client:
                raise ConnectionException("Client not initialized")
            
            if not isinstance(self.slave_id, int):
                raise ValueError(f"Invalid slave_id type: {type(self.slave_id)}. Expected int.")

            # CRITICAL: Enforce protocol command interval (>300ms between commands)
            self._enforce_command_interval()

            # I/O operation performed outside lock to allow concurrent operations
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
        with self._lock:
            self._is_closing = True  # Signal that we're closing
            
            if self.client:
                try:
                    self.client.close()
                    _LOGGER.info(f"Closed connection to {self.host}:{self.port}")
                except Exception as e:
                    _LOGGER.debug(f"Error closing connection (ignored): {e}")
                finally:
                    self.client = None
            
            self._is_closing = False  # Reset flag after cleanup