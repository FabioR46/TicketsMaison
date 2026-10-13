"""Piles et batteries faibles : un ticket quand une batterie suivie par Home Assistant
passe sous le seuil (20 % par défaut), un message quand la pile a été changée.

Aucune entité à choisir : toutes les batteries de Home Assistant sont surveillées
(capteurs « Batterie » en %, et capteurs binaires « Batterie faible »).
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_CLASS, ATTR_UNIT_OF_MEASUREMENT, EVENT_STATE_CHANGED, PERCENTAGE,
    STATE_UNAVAILABLE, STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .api import TicketsMaisonAPI, TicketsMaisonError
from .const import BATTERY_HYSTERESIS, CONF_BATTERY, CONF_BATTERY_THRESHOLD, DEFAULT_BATTERY_THRESHOLD

_LOGGER = logging.getLogger(__name__)


class BatteryWatch:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: TicketsMaisonAPI) -> None:
        self.hass = hass
        self.api = api
        self.enabled = bool(entry.options.get(CONF_BATTERY, False))
        self.threshold = int(entry.options.get(CONF_BATTERY_THRESHOLD, DEFAULT_BATTERY_THRESHOLD))
        self.low: set[str] = set()      # entités déjà signalées (pile faible)
        self._unsub = None

    # ── Démarrage / arrêt ────────────────────────────────────────────────

    async def async_start(self) -> None:
        if not self.enabled:
            return
        # État actuel de toutes les batteries
        for state in self.hass.states.async_all(["sensor", "binary_sensor"]):
            if self._is_battery(state):
                await self._evaluate(state, startup=True)
        self._unsub = self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._on_event)
        _LOGGER.info("Tickets Maison : surveillance des piles (seuil %s %%)", self.threshold)

    @callback
    def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    # ── Détection ────────────────────────────────────────────────────────

    @staticmethod
    def _is_battery(state: State | None) -> bool:
        if state is None or state.attributes.get(ATTR_DEVICE_CLASS) != "battery":
            return False
        domain = state.entity_id.split(".", 1)[0]
        if domain == "binary_sensor":
            return True
        return domain == "sensor" and state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == PERCENTAGE

    @callback
    def _on_event(self, event: Event) -> None:
        new: State | None = event.data.get("new_state")
        if self._is_battery(new):
            self.hass.async_create_task(self._evaluate(new))

    def _level(self, state: State) -> float | None:
        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        if state.entity_id.startswith("binary_sensor."):
            return 0.0 if state.state == "on" else 100.0     # « batterie faible » on/off
        try:
            return float(state.state)
        except ValueError:
            return None

    def _device_name(self, state: State) -> str:
        """Nom de l'appareil (« Détecteur cuisine ») plutôt que de l'entité (« … Batterie »)."""
        entry = er.async_get(self.hass).async_get(state.entity_id)
        if entry and entry.device_id:
            device = dr.async_get(self.hass).async_get(entry.device_id)
            if device and (device.name_by_user or device.name):
                return device.name_by_user or device.name
        name = state.name
        for suffix in (" Batterie", " batterie", " Battery", " battery", " Battery level"):
            if name.endswith(suffix):
                return name[: -len(suffix)]
        return name

    async def _evaluate(self, state: State, startup: bool = False) -> None:
        level = self._level(state)
        if level is None:
            return
        entity_id = state.entity_id
        name = self._device_name(state)
        problem = f"Pile faible : {name}"
        binary = entity_id.startswith("binary_sensor.")
        try:
            if level < self.threshold and entity_id not in self.low:
                self.low.add(entity_id)
                existing = await self.api.find_open_ticket(problem)
                if existing:
                    if not startup:
                        await self.api.add_message(existing, f"🔋 Toujours faible : {self._text(level, binary)}.")
                    return
                details = (f"La batterie de « {name} » est à {self._text(level, binary)} "
                           f"(seuil {self.threshold} %). Pense à changer la pile. ({entity_id})")
                await self.api.create_auto_ticket(problem, details, "battery.25percent")
                _LOGGER.info("Tickets Maison : pile faible pour %s (%s)", name, level)
            elif level >= self.threshold + BATTERY_HYSTERESIS and entity_id in self.low:
                self.low.discard(entity_id)
                existing = await self.api.find_open_ticket(problem)
                if existing:
                    await self.api.add_message(existing, f"✅ Pile changée : {self._text(level, binary)}.")
        except TicketsMaisonError as err:
            _LOGGER.warning("Tickets Maison : alerte pile impossible pour %s — %s", entity_id, err)

    @staticmethod
    def _text(level: float, binary: bool) -> str:
        if binary:
            return "niveau faible" if level < 50 else "niveau normal"
        return f"{level:.0f} %"
