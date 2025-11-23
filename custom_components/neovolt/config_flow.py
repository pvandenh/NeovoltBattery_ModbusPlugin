"""Config flow for Neovolt Solar Inverter integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    DEFAULT_SLAVE_ID,
    CONF_SLAVE_ID,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    DEFAULT_MAX_CHARGE_POWER,
    DEFAULT_MAX_DISCHARGE_POWER,
    MIN_POWER,
    MAX_POWER_LIMIT,
    CONF_NUM_INVERTERS,
    CONF_INVERTER_NAME,
    CONF_INVERTERS,
    CONF_MASTER,
    CONF_SLAVES,
    DEFAULT_INVERTER_NAME,
    MIN_INVERTERS,
    MAX_INVERTERS,
)
from .modbus_client import NeovoltModbusClient

_LOGGER = logging.getLogger(__name__)

STEP_NUM_INVERTERS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NUM_INVERTERS, default=MIN_INVERTERS): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_INVERTERS, max=MAX_INVERTERS)
        ),
    }
)

def get_inverter_schema(inverter_name: str, is_master: bool = False) -> vol.Schema:
    """Get schema for configuring a single inverter."""
    schema_dict = {
        vol.Required(CONF_INVERTER_NAME, default=inverter_name): cv.string,
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Required(CONF_SLAVE_ID, default=DEFAULT_SLAVE_ID): cv.positive_int,
    }

    # Only master inverter has power configuration
    if is_master:
        schema_dict.update({
            vol.Required(CONF_MAX_CHARGE_POWER, default=DEFAULT_MAX_CHARGE_POWER): vol.All(
                vol.Coerce(float),
                vol.Range(min=MIN_POWER, max=MAX_POWER_LIMIT)
            ),
            vol.Required(CONF_MAX_DISCHARGE_POWER, default=DEFAULT_MAX_DISCHARGE_POWER): vol.All(
                vol.Coerce(float),
                vol.Range(min=MIN_POWER, max=MAX_POWER_LIMIT)
            ),
        })

    return vol.Schema(schema_dict)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    
    host = data[CONF_HOST]
    port = data[CONF_PORT]
    slave_id = data[CONF_SLAVE_ID]
    
    _LOGGER.info(
        "Testing connection to Neovolt inverter at %s:%s (slave_id: %s)",
        host, port, slave_id
    )
    
    client = NeovoltModbusClient(host, port, slave_id)
    
    # Test connection with detailed error handling
    try:
        result = await hass.async_add_executor_job(client.test_connection)
        if not result:
            _LOGGER.error("Connection test returned False")
            raise CannotConnect("Connection test failed without specific error")
        
        _LOGGER.info("Successfully connected to Neovolt inverter at %s:%s", host, port)
        
    except ConnectionError as err:
        _LOGGER.error("Connection error: %s", err)
        raise CannotConnect(f"Cannot connect to device: {err}") from err
    
    except TimeoutError as err:
        _LOGGER.error("Connection timeout: %s", err)
        raise CannotConnect(f"Connection timeout - device not responding: {err}") from err
    
    except Exception as err:
        _LOGGER.error("Unexpected error during connection test: %s", err, exc_info=True)
        raise CannotConnect(f"Unexpected error: {err}") from err
    
    # Return info that you want to store in the config entry
    return {"title": f"Neovolt {host}"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Neovolt Solar Inverter."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._num_inverters = 1
        self._master_data: dict[str, Any] = {}
        self._slaves_data: list[dict[str, Any]] = []
        self._current_slave_index = 0

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - ask how many inverters."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._num_inverters = user_input[CONF_NUM_INVERTERS]
            # Proceed to configure master inverter
            return await self.async_step_master()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_NUM_INVERTERS_SCHEMA,
            errors=errors,
            description_placeholders={
                "info": "Configure your Neovolt inverter system. Select the total number of inverters (1 master + slaves)."
            },
        )

    async def async_step_master(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle master inverter configuration."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                self._master_data = user_input.copy()

                # If only one inverter, create entry now
                if self._num_inverters == 1:
                    # Use single-inverter format for backwards compatibility
                    await self.async_set_unique_id(
                        f"{user_input[CONF_HOST]}_{user_input[CONF_PORT]}_{user_input[CONF_SLAVE_ID]}"
                    )
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=user_input.get(CONF_INVERTER_NAME, info["title"]),
                        data=user_input
                    )

                # Multiple inverters - proceed to configure first slave
                return await self.async_step_slave()

            except CannotConnect as err:
                _LOGGER.warning("Cannot connect to master inverter: %s", err)
                errors["base"] = "cannot_connect"
                description_placeholders["error"] = str(err)

            except Exception as err:
                _LOGGER.exception("Unexpected exception during master setup")
                errors["base"] = "unknown"
                description_placeholders["error"] = str(err)

        return self.async_show_form(
            step_id="master",
            data_schema=get_inverter_schema("Master", is_master=True),
            errors=errors,
            description_placeholders={
                "info": "Configure the master inverter (controls dispatch and has grid sensors).",
                **description_placeholders,
            },
        )

    async def async_step_slave(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle slave inverter configuration."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                self._slaves_data.append(user_input.copy())
                self._current_slave_index += 1

                # If we've configured all slaves, create the entry
                if self._current_slave_index >= self._num_inverters - 1:
                    # Create unique ID based on master inverter
                    master = self._master_data
                    await self.async_set_unique_id(
                        f"{master[CONF_HOST]}_{master[CONF_PORT]}_{master[CONF_SLAVE_ID]}_multi"
                    )
                    self._abort_if_unique_id_configured()

                    # Build config data structure
                    config_data = {
                        CONF_NUM_INVERTERS: self._num_inverters,
                        CONF_MASTER: self._master_data,
                        CONF_SLAVES: self._slaves_data,
                    }

                    title = f"Neovolt System ({self._num_inverters} inverters)"
                    return self.async_create_entry(title=title, data=config_data)

                # More slaves to configure
                return await self.async_step_slave()

            except CannotConnect as err:
                _LOGGER.warning("Cannot connect to slave inverter: %s", err)
                errors["base"] = "cannot_connect"
                description_placeholders["error"] = str(err)

            except Exception as err:
                _LOGGER.exception("Unexpected exception during slave setup")
                errors["base"] = "unknown"
                description_placeholders["error"] = str(err)

        slave_number = self._current_slave_index + 1
        return self.async_show_form(
            step_id="slave",
            data_schema=get_inverter_schema(f"Slave {slave_number}", is_master=False),
            errors=errors,
            description_placeholders={
                "info": f"Configure slave inverter {slave_number} of {self._num_inverters - 1}.",
                **description_placeholders,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> NeovoltOptionsFlowHandler:
        """Get the options flow for this handler."""
        return NeovoltOptionsFlowHandler(config_entry)


class NeovoltOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Neovolt Inverter."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Update config entry data with new values
            new_data = {**self.config_entry.data}

            # Check if this is a multi-inverter setup
            if CONF_MASTER in new_data:
                # Update master inverter power settings
                new_data[CONF_MASTER][CONF_MAX_CHARGE_POWER] = user_input[CONF_MAX_CHARGE_POWER]
                new_data[CONF_MASTER][CONF_MAX_DISCHARGE_POWER] = user_input[CONF_MAX_DISCHARGE_POWER]
            else:
                # Single inverter setup
                new_data[CONF_MAX_CHARGE_POWER] = user_input[CONF_MAX_CHARGE_POWER]
                new_data[CONF_MAX_DISCHARGE_POWER] = user_input[CONF_MAX_DISCHARGE_POWER]

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )

            return self.async_create_entry(title="", data={})

        # Get current power settings from config
        if CONF_MASTER in self.config_entry.data:
            # Multi-inverter setup - get from master
            master_data = self.config_entry.data[CONF_MASTER]
            current_charge = master_data.get(CONF_MAX_CHARGE_POWER, DEFAULT_MAX_CHARGE_POWER)
            current_discharge = master_data.get(CONF_MAX_DISCHARGE_POWER, DEFAULT_MAX_DISCHARGE_POWER)
        else:
            # Single inverter setup
            current_charge = self.config_entry.data.get(CONF_MAX_CHARGE_POWER, DEFAULT_MAX_CHARGE_POWER)
            current_discharge = self.config_entry.data.get(CONF_MAX_DISCHARGE_POWER, DEFAULT_MAX_DISCHARGE_POWER)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MAX_CHARGE_POWER,
                        default=current_charge,
                    ): vol.All(
                        vol.Coerce(float),
                        vol.Range(min=MIN_POWER, max=MAX_POWER_LIMIT)
                    ),
                    vol.Required(
                        CONF_MAX_DISCHARGE_POWER,
                        default=current_discharge,
                    ): vol.All(
                        vol.Coerce(float),
                        vol.Range(min=MIN_POWER, max=MAX_POWER_LIMIT)
                    ),
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""