"""Remonte dans l'app l'état des entités choisies dans les Options de l'intégration.

- Chaque changement d'état est envoyé (regroupés toutes les 15 s) dans la table ha_entities.
- Option : un appareil hors ligne plus de 3 minutes (entité indisponible, capteur de
  connectivité « off »…) ouvre un ticket « Hors ligne : … » ; à son retour, un message est ajouté.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_UNIT_OF_MEASUREMENT, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .api import TicketsMaisonAPI, TicketsMaisonError
from .const import ALERT_DELAY, CONF_ALERT, CONF_ENTITIES, FLUSH_INTERVAL, RESYNC_INTERVAL

_LOGGER = logging.getLogger(__name__)
UNAVAILABLE = (STATE_UNAVAILABLE, STATE_UNKNOWN)


def is_offline(state: State | None) -> bool:
    """Appareil hors ligne / en défaut ?
    - entité indisponible (unavailable / unknown)
    - capteur de connectivité (ex. intégration Ping) à « off »
    - suivi d'appareil (device_tracker) « not_home »
    - capteur « problème » à « on »
    """
    if state is None or state.state in UNAVAILABLE:
        return True
    domain = state.entity_id.split(".", 1)[0]
    device_class = state.attributes.get(ATTR_DEVICE_CLASS)
    if domain == "binary_sensor" and device_class == "connectivity":
        return state.state == "off"
    if domain == "binary_sensor" and device_class == "problem":
        return state.state == "on"
    if domain == "device_tracker":
        return state.state == "not_home"
    return False


class EntitySync:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: TicketsMaisonAPI) -> None:
        self.hass = hass
        self.api = api
        self.entity_ids: list[str] = list(entry.options.get(CONF_ENTITIES, []))
        self.alert: bool = bool(entry.options.get(CONF_ALERT, False))
        self._dirty: set[str] = set()
        self._unsubs: list = []
        self._pending_alerts: dict[str, Any] = {}
        self._open_tickets: dict[str, str] = {}   # entity_id → ticket id

    async def async_start(self) -> None:
        try:
            await self.api.remove_entities_except(self.entity_ids)
        except TicketsMaisonError as err:
            _LOGGER.warning("Tickets Maison : table ha_entities absente ? (supabase_v6.sql) — %s", err)
            return
        if not self.entity_ids:
            return
        await self._send(self.entity_ids)
        for entity_id in self.entity_ids:
            state = self.hass.states.get(entity_id)
            if self.alert and state is not None and is_offline(state):
                self._schedule_alert(entity_id)
        self._unsubs.append(async_track_state_change_event(self.hass, self.entity_ids, self._on_change))
        self._unsubs.append(async_track_time_interval(self.hass, self._flush, FLUSH_INTERVAL))
        self._unsubs.append(async_track_time_interval(self.hass, self._resync, RESYNC_INTERVAL))

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        for cancel in self._pending_alerts.values():
            cancel()
        self._unsubs.clear()
        self._pending_alerts.clear()

    # ── Changements d'état ───────────────────────────────────────────────

    @callback
    def _on_change(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        new: State | None = event.data["new_state"]
        old: State | None = event.data["old_state"]
        self._dirty.add(entity_id)
        if not self.alert or new is None:
            return
        was_down = old is not None and is_offline(old)
        is_down = is_offline(new)
        if is_down and not was_down:
            self._schedule_alert(entity_id)
        elif was_down and not is_down:
            cancel = self._pending_alerts.pop(entity_id, None)
            if cancel:
                cancel()
            self.hass.async_create_task(self._recovered(entity_id, new))

    def _schedule_alert(self, entity_id: str) -> None:
        if entity_id in self._pending_alerts:
            return

        async def _fire(_now: datetime) -> None:
            self._pending_alerts.pop(entity_id, None)
            state = self.hass.states.get(entity_id)
            if state is None or not is_offline(state) or entity_id in self._open_tickets:
                return
            since = dt_util.as_local(state.last_changed).strftime("%d/%m à %H:%M")
            try:
                ticket_id = await self.api.open_entity_ticket(state.name, entity_id, since)
                if ticket_id:
                    self._open_tickets[entity_id] = ticket_id
                    await self.api.set_entity_ticket(entity_id, ticket_id)
            except TicketsMaisonError as err:
                _LOGGER.warning("Tickets Maison : ticket non créé pour %s — %s", entity_id, err)

        self._pending_alerts[entity_id] = async_call_later(self.hass, ALERT_DELAY, _fire)

    async def _recovered(self, entity_id: str, state: State) -> None:
        ticket_id = self._open_tickets.pop(entity_id, None)
        if not ticket_id:
            return
        when = dt_util.as_local(state.last_changed).strftime("%d/%m à %H:%M")
        try:
            await self.api.add_message(ticket_id, f"✅ {state.name} est de nouveau en ligne ({when}).")
            await self.api.set_entity_ticket(entity_id, None)
        except TicketsMaisonError as err:
            _LOGGER.warning("Tickets Maison : message non envoyé — %s", err)

    # ── Envoi vers Supabase ──────────────────────────────────────────────

    async def _flush(self, _now: datetime | None = None) -> None:
        if not self._dirty:
            return
        ids, self._dirty = list(self._dirty), set()
        await self._send(ids)

    async def _resync(self, _now: datetime | None = None) -> None:
        await self._send(self.entity_ids)

    async def _send(self, entity_ids: list[str]) -> None:
        rows = [self._row(e) for e in entity_ids]
        try:
            await self.api.upsert_entities([r for r in rows if r])
        except TicketsMaisonError as err:
            _LOGGER.warning("Tickets Maison : envoi des entités impossible — %s", err)
            self._dirty.update(entity_ids)

    def _row(self, entity_id: str) -> dict[str, Any] | None:
        state = self.hass.states.get(entity_id)
        if state is None:
            return {"entity_id": entity_id, "name": entity_id, "state": STATE_UNAVAILABLE,
                    "unit": None, "device_class": None, "available": False,
                    "last_changed": None, "updated_at": dt_util.utcnow().isoformat()}
        return {
            "entity_id": entity_id,
            "name": state.name[:80],
            "state": str(state.state)[:100],
            "unit": state.attributes.get(ATTR_UNIT_OF_MEASUREMENT),
            "device_class": state.attributes.get(ATTR_DEVICE_CLASS),
            "available": not is_offline(state),
            "last_changed": state.last_changed.isoformat(),
            "updated_at": dt_util.utcnow().isoformat(),
        }
