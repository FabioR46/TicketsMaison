"""Tickets Maison : statuts des tickets et de la surveillance dans Home Assistant."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import TicketsMaisonCoordinator
from .entities import EntitySync

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.TODO]

type TicketsMaisonConfigEntry = ConfigEntry[TicketsMaisonCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: TicketsMaisonConfigEntry) -> bool:
    coordinator = TicketsMaisonCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Entités Home Assistant à remonter dans l'app (Options de l'intégration)
    sync = EntitySync(hass, entry, coordinator.api)
    coordinator.entity_sync = sync
    entry.async_on_unload(sync.async_stop)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    hass.async_create_task(sync.async_start())
    return True


async def _options_updated(hass: HomeAssistant, entry: TicketsMaisonConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TicketsMaisonConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
