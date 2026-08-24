"""Sensors for Dinero."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DineroDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    """Set up Dinero sensors."""
    async_add_entities([DineroYearToDateRevenueSensor(entry, entry.runtime_data)])


class DineroYearToDateRevenueSensor(CoordinatorEntity[DineroDataUpdateCoordinator], SensorEntity):
    """Revenue from booked invoices in the current calendar year."""

    _attr_has_entity_name = True
    _attr_translation_key = "year_to_date_revenue"
    _attr_icon = "mdi:calendar-star"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "DKK"

    def __init__(self, entry: ConfigEntry, coordinator: DineroDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id}_year_to_date_revenue"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.title,
            manufacturer="Dinero",
            configuration_url="https://dinero.dk/",
        )

    @property
    def native_value(self) -> float:
        return self.coordinator.data["year_to_date_revenue"]

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        return {
            "invoice_count": data["invoice_count"],
            "fetched_invoice_count": data["raw_invoice_count"],
            "booked_invoice_count": data["booked_invoice_count"],
            "start_date": data["start_date"],
            "end_date": data["end_date"],
            "year": data["year"],
            "period": "year_to_date",
            "amount_basis": "excluding_vat",
        }

