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
    CONF_DEVICE_NAME,
    CONF_DEVICE_ROLE,
    DEVICE_ROLE_HOST,
    DEVICE_ROLE_FOLLOWER,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_DISCHARGE_POWER,
    DEFAULT_MAX_CHARGE_POWER,
    DEFAULT_MAX_DISCHARGE_POWER,
    MIN_POWER,
    MAX_POWER_LIMIT,
)
from .modbus_client import NeovoltModbusClient

_LOGGER = logging.getLogger(__name__)

# Step 1: Connection and role
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Required(CONF_SLAVE_ID, default=DEFAULT_SLAVE_ID): cv.positive_int,
        vol.Optional(CONF_DEVICE_NAME, default=""): cv.string,
        vol.Required(CONF_DEVICE_ROLE, default=DEVICE_ROLE_HOST): vol.In([
            DEVICE_ROLE_HOST,
            DEVICE_ROLE_FOLLOWER,
        ]),
    }
)

# Step 2: Power limits (host only)
STEP_POWER_DATA_SCHEMA = vol.Schema(
    {
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

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._user_data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - connection and role."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)

                # Set unique ID to prevent duplicate entries
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}_{user_input[CONF_PORT]}_{user_input[CONF_SLAVE_ID]}"
                )
                self._abort_if_unique_id_configured()

                # Generate device name if not provided
                device_name = user_input.get(CONF_DEVICE_NAME, "").strip()
                if not device_name:
                    existing_entries = [
                        entry for entry in self.hass.config_entries.async_entries(DOMAIN)
                    ]
                    device_name = str(len(existing_entries) + 1)

                user_input[CONF_DEVICE_NAME] = device_name

                # Store user data for potential next step
                self._user_data = user_input

                # If host, proceed to power step; if follower, create entry directly
                if user_input[CONF_DEVICE_ROLE] == DEVICE_ROLE_HOST:
                    return await self.async_step_power()
                else:
                    # Follower - create entry without power settings
                    title = f"Neovolt {device_name}"
                    return self.async_create_entry(title=title, data=user_input)

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

    async def async_step_power(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the power configuration step (host only)."""
        if user_input is not None:
            # Merge power settings with user data
            self._user_data[CONF_MAX_CHARGE_POWER] = user_input[CONF_MAX_CHARGE_POWER]
            self._user_data[CONF_MAX_DISCHARGE_POWER] = user_input[CONF_MAX_DISCHARGE_POWER]

            device_name = self._user_data[CONF_DEVICE_NAME]
            title = f"Neovolt {device_name}"

            return self.async_create_entry(title=title, data=self._user_data)

        return self.async_show_form(
            step_id="power",
            data_schema=STEP_POWER_DATA_SCHEMA,
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
        self._new_role: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options - step 1: role selection."""
        current_role = self.config_entry.data.get(CONF_DEVICE_ROLE, DEVICE_ROLE_HOST)

        if user_input is not None:
            new_role = user_input[CONF_DEVICE_ROLE]
            self._new_role = new_role

            # If changing to host or staying host, show power options
            if new_role == DEVICE_ROLE_HOST:
                return await self.async_step_power()
            else:
                # Changing to follower - just update the role
                new_data = {**self.config_entry.data}
                new_data[CONF_DEVICE_ROLE] = new_role
                # Remove power settings for followers (optional cleanup)
                new_data.pop(CONF_MAX_CHARGE_POWER, None)
                new_data.pop(CONF_MAX_DISCHARGE_POWER, None)

                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=new_data,
                )

                return self.async_create_entry(title="", data={})

        # Show role selector
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_DEVICE_ROLE,
                        default=current_role,
                    ): vol.In([DEVICE_ROLE_HOST, DEVICE_ROLE_FOLLOWER]),
                }
            ),
        )

    async def async_step_power(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options - step 2: power settings (host only)."""
        if user_input is not None:
            new_data = {**self.config_entry.data}
            new_data[CONF_DEVICE_ROLE] = self._new_role or DEVICE_ROLE_HOST
            new_data[CONF_MAX_CHARGE_POWER] = user_input[CONF_MAX_CHARGE_POWER]
            new_data[CONF_MAX_DISCHARGE_POWER] = user_input[CONF_MAX_DISCHARGE_POWER]

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )

            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="power",
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
