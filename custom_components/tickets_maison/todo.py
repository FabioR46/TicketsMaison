"""Liste « À faire » : les tickets ouverts dans les Listes de tâches de Home Assistant.

- Cocher une tâche  → le ticket passe en « Résolu »
- Ajouter une tâche → crée un ticket dans la zone Maintenance
"""
from __future__ import annotations

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TicketsMaisonConfigEntry
from .api import TicketsMaisonError
from .entity import TicketsMaisonEntity

DOTS = {"sent": "🟣", "inProgress": "🟠", "waitingUser": "🟡"}
LABELS = {"sent": "Envoyé", "inProgress": "En cours", "waitingUser": "En attente de réponse"}


async def async_setup_entry(
    hass: HomeAssistant, entry: TicketsMaisonConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([TicketsMaisonTodo(entry.runtime_data)])


class TicketsMaisonTodo(TicketsMaisonEntity, TodoListEntity):
    _attr_icon = "mdi:clipboard-check-outline"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "a_faire", "À faire", "todo")

    @property
    def todo_items(self) -> list[TodoItem]:
        items: list[TodoItem] = []
        for t in (self.coordinator.data or {}).get("tickets") or []:
            status = t.get("status")
            urgent = " ⚠️" if t.get("priority") == "urgent" else ""
            items.append(TodoItem(
                uid=str(t.get("id")),
                # « 🟣 Fuite sous l'évier — Envoyé »
                summary=f"{DOTS.get(status, '⚪')} {t.get('title', '')}{urgent} — {LABELS.get(status, status or '')}",
                status=TodoItemStatus.NEEDS_ACTION,
                description=t.get("zone") or None,
            ))
        return items

    async def async_create_todo_item(self, item: TodoItem) -> None:
        title = (item.summary or "").strip()
        if not title:
            raise HomeAssistantError("Titre vide")
        try:
            await self.coordinator.api.create_ticket(title, item.description or "")
        except TicketsMaisonError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        if item.status != TodoItemStatus.COMPLETED:
            return  # seul le passage à « fait » a un effet (ticket résolu)
        try:
            await self.coordinator.api.set_status(item.uid, "resolved")
        except TicketsMaisonError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_refresh()
