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
)
from .modbus_client import NeovoltModbusClient

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Required(CONF_SLAVE_ID, default=DEFAULT_SLAVE_ID): cv.positive_int,
        vol.Required(CONF_MAX_CHARGE_POWER, default=DEFAULT_MAX_CHARGE_POWER): vol.All(
            vol.Coerce(float),
            vol.Range(min=MIN_POWER, max=MAX_POWER_LIMIT)
        ),
        vol.Required(CONF_MAX_DISCHARGE_POWER, default=DEFAULT_MAX_DISCHARGE_POWER): vol.All(
            vol.Coerce(float),
            vol.Range(min=MIN_POWER, max=MAX_POWER_LIMIT)
        ),
    }
)


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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}
        
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                
                # Set unique ID to prevent duplicate entries
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}_{user_input[CONF_SLAVE_ID]}"
                )
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(title=info["title"], data=user_input)
                
            except CannotConnect as err:
                _LOGGER.warning("Cannot connect to Neovolt inverter: %s", err)
                errors["base"] = "cannot_connect"
                description_placeholders["error"] = str(err)
                
            except Exception as err:
                _LOGGER.exception("Unexpected exception during setup")
                errors["base"] = "unknown"
                description_placeholders["error"] = str(err)

        return self.async_show_form(
            step_id="user", 
            data_schema=STEP_USER_DATA_SCHEMA, 
            errors=errors,
            description_placeholders=description_placeholders,
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
            new_data[CONF_MAX_CHARGE_POWER] = user_input[CONF_MAX_CHARGE_POWER]
            new_data[CONF_MAX_DISCHARGE_POWER] = user_input[CONF_MAX_DISCHARGE_POWER]
            
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )
            
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MAX_CHARGE_POWER,
                        default=self.config_entry.data.get(
                            CONF_MAX_CHARGE_POWER, DEFAULT_MAX_CHARGE_POWER
                        ),
                    ): vol.All(
                        vol.Coerce(float), 
                        vol.Range(min=MIN_POWER, max=MAX_POWER_LIMIT)
                    ),
                    vol.Required(
                        CONF_MAX_DISCHARGE_POWER,
                        default=self.config_entry.data.get(
                            CONF_MAX_DISCHARGE_POWER, DEFAULT_MAX_DISCHARGE_POWER
                        ),
                    ): vol.All(
                        vol.Coerce(float), 
                        vol.Range(min=MIN_POWER, max=MAX_POWER_LIMIT)
                    ),
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""