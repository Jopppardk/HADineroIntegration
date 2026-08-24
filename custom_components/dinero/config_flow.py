"""Config flow for Dinero."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from .api import DineroApiClient, DineroApiError, DineroAuthenticationError
from .const import (
    CONF_API_KEY,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_ORGANIZATION_ID,
    DOMAIN,
)


class DineroConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Dinero config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Collect personal integration credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(str(user_input[CONF_ORGANIZATION_ID]))
            self._abort_if_unique_id_configured()
            client = DineroApiClient(
                self.hass,
                client_id=user_input[CONF_CLIENT_ID],
                client_secret=user_input[CONF_CLIENT_SECRET],
                api_key=user_input[CONF_API_KEY],
                organization_id=str(user_input[CONF_ORGANIZATION_ID]),
            )
            try:
                await client.async_validate()
            except DineroAuthenticationError:
                errors["base"] = "invalid_auth"
            except DineroApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or f"Dinero {user_input[CONF_ORGANIZATION_ID]}",
                    data={key: str(value) for key, value in user_input.items() if key != CONF_NAME},
                )

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default="Dinero"): str,
                vol.Required(CONF_ORGANIZATION_ID): str,
                vol.Required(CONF_CLIENT_ID): str,
                vol.Required(CONF_CLIENT_SECRET): str,
                vol.Required(CONF_API_KEY): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

