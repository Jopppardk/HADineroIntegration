"""Dinero integration for Home Assistant."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .api import DineroApiClient
from .const import (
    CONF_API_KEY,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_INVENTORY_ACCOUNT,
    CONF_ORGANIZATION_ID,
    DEFAULT_INVENTORY_ACCOUNT,
)
from .coordinator import DineroDataUpdateCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dinero from a config entry."""
    settings = {**entry.data, **entry.options}
    client = DineroApiClient(
        hass,
        client_id=settings[CONF_CLIENT_ID],
        client_secret=settings[CONF_CLIENT_SECRET],
        api_key=settings[CONF_API_KEY],
        organization_id=settings[CONF_ORGANIZATION_ID],
        inventory_account=int(
            settings.get(CONF_INVENTORY_ACCOUNT, DEFAULT_INVENTORY_ACCOUNT)
        ),
    )
    coordinator = DineroDataUpdateCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload Dinero when inventory options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

