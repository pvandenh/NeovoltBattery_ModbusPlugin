"""Modbus client for Neovolt/Bytewatt inverter - FIXED FOR PYMODBUS 3.11.2"""
import logging
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

_LOGGER = logging.getLogger(__name__)


class NeovoltModbusClient:
    """Modbus TCP client for Neovolt/Bytewatt inverter."""
    
    def __init__(self, host, port, slave_id):
        """Initialize the Modbus client."""
        self.host = host
        self.port = port
        self.slave_id = slave_id
        self.client = None
        _LOGGER.info(f"Initialized Modbus client for {host}:{port} (slave: {slave_id})")
    
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
                _LOGGER.info(f"Successfully connected to {self.host}:{self.port}")
            else:
                _LOGGER.error(f"Failed to connect to {self.host}:{self.port}")
            return connected
        except Exception as e:
            _LOGGER.error(f"Connection error: {e}")
            return False
    
    def test_connection(self):
        """Test connection by reading Battery SOC register (0x0102)."""
        try:
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
        Read holding registers from the device.
        
        Args:
            address: Starting register address (hex)
            count: Number of registers to read
            
        Returns:
            List of register values or None on error
        """
        try:
            if not self.client or not self.client.connected:
                if not self.connect():
                    return None
            
            result = self.client.read_holding_registers(
                address=address,
                count=count,
                device_id=self.slave_id  # pymodbus 3.x parameter
            )
            
            if result.isError():
                _LOGGER.error(f"Error reading registers {hex(address)}: {result}")
                return None
            
            return result.registers
            
        except Exception as e:
            _LOGGER.error(f"Exception reading registers {hex(address)}: {e}")
            return None
    
    def write_register(self, address, value):
        """
        Write a single register to the device.
        
        Args:
            address: Register address (hex)
            value: Value to write
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.client or not self.client.connected:
                if not self.connect():
                    return False
            
            result = self.client.write_register(
                address=address,
                value=value,
                device_id=self.slave_id  # pymodbus 3.x parameter
            )
            
            if result.isError():
                _LOGGER.error(f"Error writing register {hex(address)}: {result}")
                return False
            
            _LOGGER.debug(f"Successfully wrote {value} to register {hex(address)}")
            return True
            
        except Exception as e:
            _LOGGER.error(f"Exception writing register {hex(address)}: {e}")
            return False
    
    def write_registers(self, address, values):
        """
        Write multiple registers to the device.
        
        Args:
            address: Starting register address (hex)
            values: List of values to write
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.client or not self.client.connected:
                if not self.connect():
                    return False
            
            result = self.client.write_registers(
                address=address,
                values=values,
                device_id=self.slave_id  # pymodbus 3.x parameter
            )
            
            if result.isError():
                _LOGGER.error(f"Error writing registers {hex(address)}: {result}")
                return False
            
            _LOGGER.debug(f"Successfully wrote {len(values)} values starting at {hex(address)}")
            return True
            
        except Exception as e:
            _LOGGER.error(f"Exception writing registers {hex(address)}: {e}")
            return False
    
    def close(self):
        """Close the Modbus connection."""
        if self.client:
            self.client.close()
            _LOGGER.info(f"Closed connection to {self.host}:{self.port}")