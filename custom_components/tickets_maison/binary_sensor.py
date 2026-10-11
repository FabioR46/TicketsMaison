"""Capteurs binaires : urgence en cours, appareil hors ligne."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TicketsMaisonConfigEntry
from .entity import TicketsMaisonEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: TicketsMaisonConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([
        TicketsMaisonProblem(coordinator, "urgence", "Urgence en cours", "urgent", "mdi:alert"),
        TicketsMaisonProblem(coordinator, "panne_reseau", "Appareil hors ligne", "devices_down", "mdi:lan-disconnect"),
    ])


class TicketsMaisonProblem(TicketsMaisonEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, key: str, name: str, field: str, icon: str) -> None:
        super().__init__(coordinator, key, name, "binary_sensor")
        self._field = field
        self._attr_icon = icon

    @property
    def is_on(self) -> bool:
        return int((self.coordinator.data or {}).get(self._field) or 0) > 0
