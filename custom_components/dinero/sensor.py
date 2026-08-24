"""Sensors for Dinero."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_INVENTORY_SOURCE_ENTITY, DOMAIN
from .coordinator import DineroDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class DineroSensorDescription(SensorEntityDescription):
    """Description of a Dinero monetary sensor."""

    period: str


SENSORS = (
    DineroSensorDescription(
        key="year_to_date_revenue", translation_key="year_to_date_revenue",
        icon="mdi:calendar-star", period="year_to_date"
    ),
    DineroSensorDescription(
        key="year_to_date_expenses", translation_key="year_to_date_expenses",
        icon="mdi:cash-minus", period="year_to_date"
    ),
    DineroSensorDescription(
        key="year_to_date_result", translation_key="year_to_date_result",
        icon="mdi:chart-line", period="year_to_date"
    ),
    DineroSensorDescription(
        key="current_month_revenue", translation_key="current_month_revenue",
        icon="mdi:cash-plus", period="current_month"
    ),
    DineroSensorDescription(
        key="current_month_expenses", translation_key="current_month_expenses",
        icon="mdi:cash-minus", period="current_month"
    ),
    DineroSensorDescription(
        key="current_month_result", translation_key="current_month_result",
        icon="mdi:chart-areaspline", period="current_month"
    ),
    DineroSensorDescription(
        key="inventory_value", translation_key="inventory_value",
        icon="mdi:warehouse", period="current_balance"
    ),
    DineroSensorDescription(
        key="ltm_revenue", translation_key="ltm_revenue",
        icon="mdi:calendar-range", period="last_twelve_months"
    ),
    DineroSensorDescription(
        key="ltm_expenses", translation_key="ltm_expenses",
        icon="mdi:cash-minus", period="last_twelve_months"
    ),
    DineroSensorDescription(
        key="ltm_result", translation_key="ltm_result",
        icon="mdi:chart-timeline-variant", period="last_twelve_months"
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    """Set up Dinero sensors."""
    coordinator: DineroDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        DineroMonetarySensor(entry, coordinator, description)
        for description in SENSORS
    )
    settings = {**entry.data, **entry.options}
    if source_entity := settings.get(CONF_INVENTORY_SOURCE_ENTITY):
        async_add_entities(
            [DineroInventoryAdjustmentSensor(entry, coordinator, source_entity)]
        )


class DineroMonetarySensor(CoordinatorEntity[DineroDataUpdateCoordinator], SensorEntity):
    """A monetary value calculated from Dinero's general ledger."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "DKK"

    def __init__(self, entry: ConfigEntry, coordinator: DineroDataUpdateCoordinator,
                 description: DineroSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_translation_key = description.translation_key
        self._attr_icon = description.icon
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.title,
            manufacturer="Dinero",
            configuration_url="https://dinero.dk/",
        )

    @property
    def native_value(self) -> float:
        return self.coordinator.data[self.entity_description.key]

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        if self.entity_description.period == "current_month":
            start_date = data["month_start"]
        elif self.entity_description.period == "last_twelve_months":
            start_date = data["ltm_start"]
        else:
            start_date = data["start_date"]
        return {
            "start_date": start_date,
            "end_date": data["end_date"],
            "year": data["year"],
            "period": self.entity_description.period,
            "amount_basis": "excluding_vat",
            "source": (
                f"general_ledger_account_{self.coordinator.client.inventory_account}"
                if self.entity_description.key == "inventory_value"
                else "general_ledger_profit_and_loss"
            ),
        }


class DineroInventoryAdjustmentSensor(
    CoordinatorEntity[DineroDataUpdateCoordinator], SensorEntity
):
    """Show the adjustment needed to match Dinero with the source sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "inventory_adjustment"
    _attr_icon = "mdi:swap-vertical"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "DKK"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DineroDataUpdateCoordinator,
        source_entity: str,
    ) -> None:
        super().__init__(coordinator)
        self._source_entity = source_entity
        self._attr_unique_id = f"{entry.unique_id}_inventory_adjustment"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.title,
            manufacturer="Dinero",
            configuration_url="https://dinero.dk/",
        )

    async def async_added_to_hass(self) -> None:
        """Update immediately whenever the selected source sensor changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._source_entity], self._async_source_changed
            )
        )

    async def _async_source_changed(self, _event) -> None:
        """Write the newly calculated adjustment to Home Assistant."""
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        source_state = self.hass.states.get(self._source_entity)
        return (
            super().available
            and source_state is not None
            and source_state.state not in {"unknown", "unavailable"}
        )

    @property
    def native_value(self) -> float | None:
        source_state = self.hass.states.get(self._source_entity)
        if source_state is None:
            return None
        try:
            source_value = Decimal(source_state.state)
            dinero_value = Decimal(str(self.coordinator.data["inventory_value"]))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return float((source_value - dinero_value).quantize(Decimal("0.01")))

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "source_entity": self._source_entity,
            "dinero_inventory_value": self.coordinator.data["inventory_value"],
            "calculation": "source_inventory_value - dinero_inventory_value",
        }

