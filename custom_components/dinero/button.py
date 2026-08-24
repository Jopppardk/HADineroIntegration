"""Buttons for writing controlled changes to Dinero."""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal, InvalidOperation

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DineroApiError
from .const import (
    CONF_INVENTORY_ACCOUNT,
    CONF_INVENTORY_ADJUSTMENT_ACCOUNT,
    CONF_INVENTORY_SOURCE_ENTITY,
    DEFAULT_INVENTORY_ACCOUNT,
    DEFAULT_INVENTORY_ADJUSTMENT_ACCOUNT,
    DOMAIN,
)
from .coordinator import DineroDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the inventory adjustment button when a source is configured."""
    settings = {**entry.data, **entry.options}
    if settings.get(CONF_INVENTORY_SOURCE_ENTITY):
        async_add_entities([DineroInventoryAdjustmentButton(hass, entry)])


class DineroInventoryAdjustmentButton(
    CoordinatorEntity[DineroDataUpdateCoordinator], ButtonEntity
):
    """Book the difference between a HA sensor and Dinero inventory."""

    _attr_has_entity_name = True
    _attr_translation_key = "book_inventory_adjustment"
    _attr_icon = "mdi:warehouse-plus"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        coordinator: DineroDataUpdateCoordinator = entry.runtime_data
        super().__init__(coordinator)
        self.hass = hass
        self._entry = entry
        self._settings = {**entry.data, **entry.options}
        self._lock = asyncio.Lock()
        self._last_booked_signature: tuple[str, Decimal] | None = None
        self._attr_unique_id = f"{entry.unique_id}_book_inventory_adjustment"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.title,
            manufacturer="Dinero",
            configuration_url="https://dinero.dk/",
        )

    async def async_press(self) -> None:
        """Calculate, create and book one inventory adjustment."""
        if self._lock.locked():
            raise HomeAssistantError("En lagerregulering er allerede i gang")

        async with self._lock:
            source_entity = self._settings[CONF_INVENTORY_SOURCE_ENTITY]
            source_state = self.hass.states.get(source_entity)
            if source_state is None or source_state.state in {"unknown", "unavailable"}:
                raise HomeAssistantError(f"Lagerkilden {source_entity} er ikke tilgængelig")

            try:
                target = Decimal(source_state.state).quantize(Decimal("0.01"))
                current = Decimal(str(self.coordinator.data["inventory_value"])).quantize(
                    Decimal("0.01")
                )
            except (InvalidOperation, TypeError, ValueError) as err:
                raise HomeAssistantError("Lagerkilden indeholder ikke et gyldigt beløb") from err

            amount = target - current
            if amount == 0:
                raise HomeAssistantError("Lagerværdien i Dinero er allerede korrekt")

            signature = (source_state.last_updated.isoformat(), target)
            if signature == self._last_booked_signature:
                raise HomeAssistantError("Denne lagerværdi er allerede blevet bogført")

            reference = (
                f"HA inventory {datetime.now().date().isoformat()} target {target:.2f}"
            )
            try:
                await self.coordinator.client.async_book_inventory_adjustment(
                    amount=amount,
                    inventory_account=int(
                        self._settings.get(
                            CONF_INVENTORY_ACCOUNT, DEFAULT_INVENTORY_ACCOUNT
                        )
                    ),
                    adjustment_account=int(
                        self._settings.get(
                            CONF_INVENTORY_ADJUSTMENT_ACCOUNT,
                            DEFAULT_INVENTORY_ADJUSTMENT_ACCOUNT,
                        )
                    ),
                    external_reference=reference,
                )
            except DineroApiError as err:
                raise HomeAssistantError(f"Dinero afviste lagerreguleringen: {err}") from err

            self._last_booked_signature = signature
            await self.coordinator.async_request_refresh()

