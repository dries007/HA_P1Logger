"""Config flow for P1 Logger integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from serial import SerialException

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from .const import CFG_SERIAL_PORT, DOMAIN
from .p1logger import P1Logger

_LOGGER = logging.getLogger(DOMAIN).getChild("config_flow")

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CFG_SERIAL_PORT): str,
    }
)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    p1logger = P1Logger(hass, data[CFG_SERIAL_PORT])
    await p1logger.connect()
    await p1logger.disconnect()
    return {"title": "P1 Logger"}


class P1ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for P1 Logger."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except SerialException:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)
