"""Capteurs : compteurs de tickets, appareils hors ligne, dernier ticket."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TicketsMaisonConfigEntry
from .entity import TicketsMaisonEntity


@dataclass(frozen=True)
class Spec:
    key: str
    name: str
    icon: str
    value: Callable[[dict[str, Any]], Any]
    unit: str | None = "tickets"
    attrs: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _open_attrs(d: dict[str, Any]) -> dict[str, Any]:
    return {"maison": d.get("house"), "tickets": d.get("tickets") or [], "mis_a_jour": d.get("updated_at")}


def _last_value(d: dict[str, Any]) -> str:
    t = d.get("last_ticket") or {}
    return f"{t.get('number', '')} {t.get('title', '')}".strip()[:250] if t else "Aucun"


SPECS: tuple[Spec, ...] = (
    Spec("ouverts", "Ouverts", "mdi:ticket-confirmation", lambda d: d.get("open"), attrs=_open_attrs),
    Spec("envoyes", "Envoyés", "mdi:email-arrow-right", lambda d: d.get("sent")),
    Spec("en_cours", "En cours", "mdi:progress-wrench", lambda d: d.get("in_progress")),
    Spec("en_attente", "En attente de réponse", "mdi:message-reply-text", lambda d: d.get("waiting_user")),
    Spec("urgents", "Urgents", "mdi:alert", lambda d: d.get("urgent")),
    Spec("a_valider", "Urgence à valider", "mdi:gavel", lambda d: d.get("to_validate")),
    Spec("resolus_jour", "Résolus aujourd'hui", "mdi:check-decagram", lambda d: d.get("resolved_today"),
         attrs=lambda d: {"resolus_7_jours": d.get("resolved_7d")}),
    Spec("hors_ligne", "Appareils hors ligne", "mdi:lan-disconnect", lambda d: d.get("devices_down"),
         unit="appareils",
         attrs=lambda d: {"surveilles": d.get("devices"), "noms": d.get("devices_down_names") or ""}),
    Spec("dernier", "Dernier ticket", "mdi:ticket-outline", _last_value, unit=None,
         attrs=lambda d: dict(d.get("last_ticket") or {})),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: TicketsMaisonConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(TicketsMaisonSensor(coordinator, spec) for spec in SPECS)


class TicketsMaisonSensor(TicketsMaisonEntity, SensorEntity):
    def __init__(self, coordinator, spec: Spec) -> None:
        super().__init__(coordinator, spec.key, spec.name, "sensor")
        self._spec = spec
        self._attr_icon = spec.icon
        self._attr_native_unit_of_measurement = spec.unit
        if spec.unit:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Any:
        return self._spec.value(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self._spec.attrs(self.coordinator.data or {}) if self._spec.attrs else None
