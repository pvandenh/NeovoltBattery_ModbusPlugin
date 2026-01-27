"""Modbus client for Neovolt/Bytewatt inverter - ENHANCED PROTOCOL COMPLIANCE"""
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
PROTOCOL_COMMAND_INTERVAL = 0.35  # INCREASED: 350ms between commands for safety margin
PROTOCOL_RESPONSE_TIMEOUT = 10.0  # 10 second timeout (>10S required)

# CRITICAL: Additional protocol delay after writes
PROTOCOL_WRITE_STABILIZATION_DELAY = 0.1  # 100ms for inverter to process write


class NeovoltModbusClient:
    """Modbus TCP client for Neovolt/Bytewatt inverter."""
    
    def __init__(self, host, port, slave_id):
        """Initialize the Modbus client."""
        self.host = host
        self.port = port
        self.slave_id = slave_id
        self.client = None
        self._lock = threading.Lock()  # Protect connection state AND command timing
        self._last_error = None
        self._consecutive_errors = 0
        self._is_closing = False
        self._last_command_time = 0
        self._last_write_time = 0  # Track writes separately for extra delay
        _LOGGER.info(f"Initialized Modbus client for {host}:{port} (slave: {slave_id})")

    def _enforce_command_interval(self, is_write=False):
        """
        Enforce minimum command interval required by protocol.

        BYTEWATT protocol requires >300ms between commands.
        Writes get additional stabilization delay to ensure inverter processes changes.
        
        Args:
            is_write: If True, enforces additional delay after last write command
        """
        with self._lock:
            current_time = time.time()
            
            # Calculate required delay based on last command type
            if is_write and self._last_write_time > 0:
                # After a write, enforce both command interval AND stabilization delay
                time_since_write = current_time - self._last_write_time
                min_delay = PROTOCOL_COMMAND_INTERVAL + PROTOCOL_WRITE_STABILIZATION_DELAY
                if time_since_write < min_delay:
                    sleep_time = min_delay - time_since_write
                else:
                    sleep_time = 0
            else:
                # Normal command interval
                time_since_last = current_time - self._last_command_time
                if time_since_last < PROTOCOL_COMMAND_INTERVAL:
                    sleep_time = PROTOCOL_COMMAND_INTERVAL - time_since_last
                else:
                    sleep_time = 0
            
            # Update timestamps while holding lock
            self._last_command_time = time.time()
            if is_write:
                self._last_write_time = time.time()

        # Sleep outside lock to avoid blocking other operations
        if sleep_time > 0:
            _LOGGER.debug(f"Enforcing protocol delay: {sleep_time:.3f}s ({'write' if is_write else 'read'})")
            time.sleep(sleep_time)

    @staticmethod
    def _is_transient_error(exception):
        """Determine if an error is transient (can be retried) or permanent."""
        if isinstance(exception, (ConnectionException, ConnectionError, TimeoutError, OSError)):
            return True

        if isinstance(exception, ModbusException):
            error_str = str(exception).lower()
            transient_keywords = ['timeout', 'connection', 'unreachable', 'refused', 'reset']
            if any(keyword in error_str for keyword in transient_keywords):
                return True

        return False

    def _retry_operation(self, operation, operation_name, *args, **kwargs):
        """Execute an operation with retry logic for transient errors."""
        retry_delay = INITIAL_RETRY_DELAY
        last_exception = None

        for attempt in range(1, MAX_RETRIES + 1):
            if self._is_closing:
                _LOGGER.debug(f"{operation_name} cancelled - client is closing")
                return None

            try:
                result = operation(*args, **kwargs)

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

                if attempt < MAX_RETRIES and is_transient:
                    log_level = _LOGGER.debug if attempt == 1 else _LOGGER.warning
                    log_level(
                        f"{operation_name} failed (attempt {attempt}/{MAX_RETRIES}): {e}. "
                        f"Retrying in {retry_delay:.1f}s..."
                    )
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
                else:
                    error_type = "transient" if is_transient else "permanent"
                    error_signature = f"{type(e).__name__}:{str(e)}"
                    
                    if error_signature != self._last_error:
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
                        if self._consecutive_errors % 10 == 0:
                            _LOGGER.error(
                                f"{operation_name} failed {self._consecutive_errors} consecutive times: {e}"
                            )
                    break

        return None

    def connect(self):
        """Establish connection to the Modbus device with improved restart handling."""
        try:
            if self.client:
                try:
                    self.client.close()
                    time.sleep(0.2)  # Gateway connection release delay
                except Exception:
                    pass
            
            self.client = ModbusTcpClient(
                host=self.host,
                port=self.port,
                timeout=PROTOCOL_RESPONSE_TIMEOUT
            )
            
            connected = False
            for attempt in range(2):
                try:
                    connected = self.client.connect()
                    if connected:
                        break
                except (ConnectionError, OSError) as e:
                    if attempt == 0:
                        _LOGGER.debug(f"Connection attempt {attempt + 1} failed, retrying: {e}")
                        time.sleep(0.3)
                    else:
                        raise
            
            if connected:
                _LOGGER.info(f"Connected to Modbus device at {self.host}:{self.port}")
                time.sleep(0.1)  # Device stabilization delay
            else:
                _LOGGER.error(f"Failed to connect to Modbus device at {self.host}:{self.port}")
                self.client = None

            return connected

        except Exception as e:
            _LOGGER.error(f"Connection error for {self.host}:{self.port}: {e}")
            self.client = None
            return False
    
    def test_connection(self):
        """Test connection by reading Battery SOC register (0x0102)."""
        try:
            with self._lock:
                if not self.client:
                    if not self.connect():
                        return False

                _LOGGER.info(f"Testing connection to {self.host}:{self.port}")

                if not self.client.connected:
                    _LOGGER.info("TCP not connected, attempting connection...")
                    if not self.connect():
                        return False

                client_ref = self.client

            _LOGGER.info("TCP connected! Reading SOC register...")

            self._enforce_command_interval(is_write=False)

            result = client_ref.read_holding_registers(
                address=0x0102,
                count=1,
                device_id=self.slave_id
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
        """Read holding registers from the device with retry logic."""
        def _read_operation():
            if self._is_closing:
                raise ConnectionException("Client is being closed")

            with self._lock:
                if self._is_closing:
                    raise ConnectionException("Client is being closed")
                    
                if not self.client or not self.client.connected:
                    if not self.connect():
                        raise ConnectionException(
                            f"Failed to establish connection to {self.host}:{self.port}"
                        )
                
                client_ref = self.client

            if not client_ref:
                raise ConnectionException("Client not initialized after connection attempt")
            
            if not isinstance(self.slave_id, int):
                raise ValueError(f"Invalid slave_id type: {type(self.slave_id)}. Expected int.")

            # Enforce protocol delay BEFORE read
            self._enforce_command_interval(is_write=False)

            result = client_ref.read_holding_registers(
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
        """Write a single register to the device with retry logic."""
        def _write_operation():
            if self._is_closing:
                raise ConnectionException("Client is being closed")

            with self._lock:
                if self._is_closing:
                    raise ConnectionException("Client is being closed")
                    
                if not self.client or not self.client.connected:
                    if not self.connect():
                        raise ConnectionException(
                            f"Failed to establish connection to {self.host}:{self.port}"
                        )
                
                client_ref = self.client

            if not client_ref:
                raise ConnectionException("Client not initialized after connection attempt")
            
            if not isinstance(self.slave_id, int):
                raise ValueError(f"Invalid slave_id type: {type(self.slave_id)}. Expected int.")

            # Enforce protocol delay BEFORE write (includes extra delay if previous was write)
            self._enforce_command_interval(is_write=True)

            result = client_ref.write_register(
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
        """Write multiple registers to the device with retry logic and improved logging."""
        def _write_operation():
            if self._is_closing:
                raise ConnectionException("Client is being closed")

            with self._lock:
                if self._is_closing:
                    raise ConnectionException("Client is being closed")
                    
                if not self.client or not self.client.connected:
                    if not self.connect():
                        raise ConnectionException(
                            f"Failed to establish connection to {self.host}:{self.port}"
                        )
                
                client_ref = self.client

            if not client_ref:
                raise ConnectionException("Client not initialized after connection attempt")
            
            if not isinstance(self.slave_id, int):
                raise ValueError(f"Invalid slave_id type: {type(self.slave_id)}. Expected int.")

            # Enhanced logging for dispatch commands
            if address == 0x0880:
                _LOGGER.info(
                    f"Writing dispatch command to {hex(address)}: "
                    f"Para1={values[0]}, Para2={values[1]:04X}{values[2]:04X}, "
                    f"Para4={values[5]}, Para5={values[6]}, Para6={values[7]:04X}{values[8]:04X}"
                )

            # Enforce protocol delay BEFORE write (includes extra delay if previous was write)
            self._enforce_command_interval(is_write=True)

            result = client_ref.write_registers(
                address=address,
                values=values,
                device_id=self.slave_id
            )

            if result.isError():
                raise ModbusException(f"Modbus error writing registers {hex(address)}: {result}")

            _LOGGER.debug(f"Successfully wrote {len(values)} values starting at {hex(address)}")
            
            # CRITICAL: Small delay after dispatch writes to let inverter process
            if address == 0x0880:
                time.sleep(0.05)  # 50ms post-write settling
                
            return True

        operation_name = f"Write registers {hex(address)}"
        result = self._retry_operation(_write_operation, operation_name)
        return result if result is not None else False
    
    def close(self):
        """Close the Modbus connection."""
        with self._lock:
            self._is_closing = True

            if self.client:
                try:
                    self.client.close()
                    _LOGGER.info(f"Closed connection to {self.host}:{self.port}")
                except Exception as e:
                    _LOGGER.debug(f"Error closing connection (ignored): {e}")
                finally:
                    self.client = None

            self._is_closing = False

    @property
    def is_connected(self) -> bool:
        """Check if client is currently connected."""
        with self._lock:
            return self.client is not None and self.client.connected

    def force_reconnect(self) -> bool:
        """Force close and reconnect the Modbus connection."""
        _LOGGER.info(f"Force reconnecting to {self.host}:{self.port}")

        with self._lock:
            self._is_closing = True

            if self.client:
                try:
                    self.client.close()
                except Exception as e:
                    _LOGGER.debug(f"Error closing client during force reconnect: {e}")
                self.client = None

            self._last_error = None
            self._consecutive_errors = 0
            self._is_closing = False

        return self.connect()