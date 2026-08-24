"""Config flow for Dinero."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector
from .api import DineroApiClient, DineroApiError, DineroAuthenticationError
from .const import (
    CONF_API_KEY,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_INVENTORY_ACCOUNT,
    CONF_INVENTORY_ADJUSTMENT_ACCOUNT,
    CONF_INVENTORY_SOURCE_ENTITY,
    CONF_ORGANIZATION_ID,
    DEFAULT_INVENTORY_ACCOUNT,
    DEFAULT_INVENTORY_ADJUSTMENT_ACCOUNT,
    DOMAIN,
)


class DineroConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Dinero config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the inventory settings flow."""
        return DineroOptionsFlow()

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
                inventory_account=int(user_input[CONF_INVENTORY_ACCOUNT]),
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
                vol.Required(
                    CONF_INVENTORY_ACCOUNT, default=DEFAULT_INVENTORY_ACCOUNT
                ): vol.Coerce(int),
                vol.Required(
                    CONF_INVENTORY_ADJUSTMENT_ACCOUNT,
                    default=DEFAULT_INVENTORY_ADJUSTMENT_ACCOUNT,
                ): vol.Coerce(int),
                vol.Optional(CONF_INVENTORY_SOURCE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class DineroOptionsFlow(config_entries.OptionsFlow):
    """Configure inventory posting for an existing Dinero entry."""

    async def async_step_init(self, user_input=None):
        """Collect accounts and the Home Assistant inventory source."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        fields = {
                vol.Required(
                    CONF_INVENTORY_ACCOUNT,
                    default=int(
                        current.get(CONF_INVENTORY_ACCOUNT, DEFAULT_INVENTORY_ACCOUNT)
                    ),
                ): vol.Coerce(int),
                vol.Required(
                    CONF_INVENTORY_ADJUSTMENT_ACCOUNT,
                    default=int(
                        current.get(
                            CONF_INVENTORY_ADJUSTMENT_ACCOUNT,
                            DEFAULT_INVENTORY_ADJUSTMENT_ACCOUNT,
                        )
                    ),
                ): vol.Coerce(int),
        }
        source_entity = current.get(CONF_INVENTORY_SOURCE_ENTITY)
        source_key = (
            vol.Optional(CONF_INVENTORY_SOURCE_ENTITY, default=source_entity)
            if source_entity
            else vol.Optional(CONF_INVENTORY_SOURCE_ENTITY)
        )
        fields[source_key] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        )
        schema = vol.Schema(fields)
        return self.async_show_form(step_id="init", data_schema=schema)

