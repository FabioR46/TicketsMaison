"""Base commune : un « appareil » Tickets Maison par maison."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TicketsMaisonCoordinator


class TicketsMaisonEntity(CoordinatorEntity[TicketsMaisonCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: TicketsMaisonCoordinator, key: str, name: str, platform: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.house_id}_{key}"
        # Identifiant prévisible (utilisé par la carte du tableau de bord)
        self.entity_id = f"{platform}.tickets_maison_{key}"
        house = (coordinator.data or {}).get("house") or "Maison"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.house_id)},
            name=f"Tickets Maison – {house}",
            manufacturer="Tickets Maison",
            model="Maison",
            entry_type=DeviceEntryType.SERVICE,
        )
