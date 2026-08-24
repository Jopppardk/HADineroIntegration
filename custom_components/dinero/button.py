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
    """Set up Dinero write-action buttons."""
    settings = {**entry.data, **entry.options}
    entities = [DineroCardAccountSettlementButton(entry)]
    if settings.get(CONF_INVENTORY_SOURCE_ENTITY):
        entities.append(DineroInventoryAdjustmentButton(hass, entry))
    async_add_entities(entities)


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


class DineroCardAccountSettlementButton(
    CoordinatorEntity[DineroDataUpdateCoordinator], ButtonEntity
):
    """Settle Shopify Payments and Flatpay against the distribution account."""

    _attr_has_entity_name = True
    _attr_translation_key = "settle_card_accounts"
    _attr_icon = "mdi:credit-card-sync-outline"

    def __init__(self, entry: ConfigEntry) -> None:
        coordinator: DineroDataUpdateCoordinator = entry.runtime_data
        super().__init__(coordinator)
        self._lock = asyncio.Lock()
        self._last_booked_signature: tuple[Decimal, Decimal] | None = None
        self._attr_unique_id = f"{entry.unique_id}_settle_card_accounts"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.title,
            manufacturer="Dinero",
            configuration_url="https://dinero.dk/",
        )

    async def async_press(self) -> None:
        """Book positive counter-postings for negative card-account balances."""
        if self._lock.locked():
            raise HomeAssistantError("En udligning er allerede i gang")

        async with self._lock:
            await self.coordinator.async_request_refresh()
            shopify_balance = Decimal(
                str(self.coordinator.data["shopify_payments_balance"])
            ).quantize(Decimal("0.01"))
            flatpay_balance = Decimal(
                str(self.coordinator.data["flatpay_balance"])
            ).quantize(Decimal("0.01"))
            distribution_balance = Decimal(
                str(self.coordinator.data["distribution_account_balance"])
            ).quantize(Decimal("0.01"))
            shopify_amount = max(-shopify_balance, Decimal("0"))
            flatpay_amount = max(-flatpay_balance, Decimal("0"))

            if shopify_amount == 0 and flatpay_amount == 0:
                raise HomeAssistantError(
                    "Shopify Payments og Flatpay har ingen negative saldi"
                )
            settlement_total = shopify_amount + flatpay_amount
            if distribution_balance < settlement_total:
                raise HomeAssistantError(
                    "Fordelingskontoen har ikke saldo nok til udligningen: "
                    f"{distribution_balance} DKK tilgængelig, "
                    f"{settlement_total} DKK nødvendig"
                )

            signature = (shopify_balance, flatpay_balance)
            if signature == self._last_booked_signature:
                raise HomeAssistantError("Disse saldi er allerede blevet udlignet")

            reference = f"HA card settlement {datetime.now().date().isoformat()}"
            try:
                await self.coordinator.client.async_book_card_account_settlement(
                    shopify_payments_amount=shopify_amount,
                    flatpay_amount=flatpay_amount,
                    external_reference=reference,
                )
            except DineroApiError as err:
                raise HomeAssistantError(
                    f"Dinero afviste udligningen: {err}"
                ) from err

            self._last_booked_signature = signature
            await self.coordinator.async_request_refresh()

