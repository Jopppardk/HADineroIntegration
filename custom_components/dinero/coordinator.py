"""Data coordinator for Dinero."""

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DineroApiClient, DineroApiError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class DineroDataUpdateCoordinator(DataUpdateCoordinator[dict]):
    """Fetch shared Dinero data on a fixed interval."""

    def __init__(self, hass: HomeAssistant, client: DineroApiClient) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict:
        try:
            return await self.client.async_year_to_date_revenue()
        except DineroApiError as err:
            raise UpdateFailed(f"Error communicating with Dinero: {err}") from err

