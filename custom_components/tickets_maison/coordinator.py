"""Interroge Supabase toutes les minutes."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import InvalidAuth, TicketsMaisonAPI, TicketsMaisonError
from .const import CONF_HOUSE, CONF_KEY, CONF_URL, DOMAIN, EVENT_NEW_TICKET, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class TicketsMaisonCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Données partagées par tous les capteurs."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.house_id: str = entry.data[CONF_HOUSE]
        self.api = TicketsMaisonAPI(
            async_get_clientsession(hass),
            entry.data[CONF_URL],
            entry.data[CONF_KEY],
            self.house_id,
        )
        self._last_number: str | None = None
        self.entity_sync = None   # EntitySync (entités remontées dans l'app)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.api.summary()
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed("Clé Supabase refusée") from err
        except TicketsMaisonError as err:
            raise UpdateFailed(str(err) or "Maison introuvable") from err

        # Événement « nouveau ticket » pour les automatisations
        last = data.get("last_ticket") or {}
        number = last.get("number")
        if number and self._last_number and number != self._last_number:
            self.hass.bus.async_fire(
                EVENT_NEW_TICKET,
                {
                    "house": data.get("house"),
                    "number": number,
                    "title": last.get("title"),
                    "zone": last.get("zone"),
                    "author": last.get("author"),
                    "status": last.get("status"),
                },
            )
        if number:
            self._last_number = number
        return data
