"""Accès à Supabase (fonction ha_summary) et décodage du code de connexion."""
from __future__ import annotations

import base64
import json
from typing import Any

import aiohttp


class TicketsMaisonError(Exception):
    """Erreur générique."""


class InvalidCode(TicketsMaisonError):
    """Code de connexion illisible."""


class InvalidAuth(TicketsMaisonError):
    """Clé refusée par Supabase."""


class HouseNotFound(TicketsMaisonError):
    """La maison n'existe pas."""


def decode_code(code: str) -> dict[str, str]:
    """Code « TM1:… » généré par l'app → {url, key, house_id}."""
    raw = (code or "").strip().replace("\n", "").replace(" ", "")
    if raw.upper().startswith("TM1:"):
        raw = raw[4:]
    try:
        raw += "=" * (-len(raw) % 4)
        data = json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
        url = str(data["u"]).strip().rstrip("/")
        key = str(data["k"]).strip()
        house = str(data["h"]).strip().lower()
    except Exception as err:  # noqa: BLE001
        raise InvalidCode from err
    for suffix in ("/rest/v1", "/rest"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    if not url.startswith("http") or not key or len(house) != 36:
        raise InvalidCode
    return {"url": url, "key": key, "house_id": house}


class TicketsMaisonAPI:
    """Client minimal."""

    def __init__(self, session: aiohttp.ClientSession, url: str, key: str, house_id: str) -> None:
        self._session = session
        self._rest = f"{url.rstrip('/')}/rest/v1"
        self._url = f"{self._rest}/rpc/ha_summary"
        self._house = house_id
        self._headers = {"apikey": key, "Content-Type": "application/json"}
        if key.startswith("eyJ"):
            self._headers["Authorization"] = f"Bearer {key}"

    async def summary(self) -> dict[str, Any]:
        try:
            async with self._session.post(
                self._url,
                headers=self._headers,
                json={"p_house": self._house},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (401, 403):
                    raise InvalidAuth
                if resp.status == 404:
                    raise TicketsMaisonError(
                        "Fonction ha_summary introuvable : exécute supabase_v5.sql dans Supabase"
                    )
                if resp.status >= 400:
                    raise TicketsMaisonError(f"Erreur Supabase {resp.status}: {await resp.text()}")
                data = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise TicketsMaisonError(f"Connexion impossible : {err}") from err
        if not isinstance(data, dict) or not data.get("house"):
            raise HouseNotFound
        return data

    async def _write(self, method: str, path: str, body: Any, prefer: str = "return=minimal") -> Any:
        headers = {**self._headers, "Prefer": prefer}
        try:
            async with self._session.request(
                method, f"{self._rest}/{path}", headers=headers, json=body,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (401, 403):
                    raise InvalidAuth
                if resp.status >= 400:
                    raise TicketsMaisonError(f"Erreur Supabase {resp.status}: {await resp.text()}")
                if "return=representation" in prefer:
                    return await resp.json(content_type=None)
                return None
        except aiohttp.ClientError as err:
            raise TicketsMaisonError(f"Connexion impossible : {err}") from err

    # ── Entités Home Assistant remontées dans l'app ──────────────────────

    async def upsert_entities(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        for row in rows:
            row["house_id"] = self._house
        await self._write("POST", "ha_entities?on_conflict=house_id,entity_id", rows,
                          prefer="resolution=merge-duplicates,return=minimal")

    async def remove_entities_except(self, entity_ids: list[str]) -> None:
        query = f"ha_entities?house_id=eq.{self._house}"
        if entity_ids:
            quoted = ",".join('"' + e.replace('"', "") + '"' for e in entity_ids)
            query += f"&entity_id=not.in.({quoted})"
        await self._write("DELETE", query, None)

    async def set_entity_ticket(self, entity_id: str, ticket_id: str | None) -> None:
        await self._write("PATCH", f"ha_entities?house_id=eq.{self._house}&entity_id=eq.{entity_id}",
                          {"open_ticket_id": ticket_id})

    async def open_entity_ticket(self, name: str, entity_id: str, since: str) -> str | None:
        """Ticket « Hors ligne : … » (zone Home Assistant). Renvoie son id."""
        created = await self._write("POST", "tickets", {
            "house_id": self._house,
            "theme": "Home Assistant",
            "theme_icon": "house.lodge.fill",
            "problem": f"Hors ligne : {name}"[:80],
            "problem_icon": "wifi.exclamationmark",
            "details": f"Home Assistant signale « {name} » ({entity_id}) hors ligne depuis le {since}."[:500],
            "status": "sent",
            "author": "Home Assistant",
            "requested_priority": "normal",
        }, prefer="return=representation")
        return created[0]["id"] if created else None

    async def add_message(self, ticket_id: str, text: str) -> None:
        await self._write("POST", "messages", {
            "ticket_id": ticket_id, "text": text[:500], "author": "Home Assistant", "from_admin": False,
        })

    async def set_status(self, ticket_id: str, status: str) -> None:
        """Change le statut d'un ticket (resolved = résolu)."""
        from datetime import datetime, timezone
        body: dict[str, Any] = {"status": status}
        body["resolved_at"] = datetime.now(timezone.utc).isoformat() if status == "resolved" else None
        await self._write("PATCH", f"tickets?id=eq.{ticket_id}&house_id=eq.{self._house}", body)

    async def create_ticket(self, title: str, details: str = "") -> None:
        """Nouveau ticket « Maintenance » créé depuis Home Assistant."""
        await self._write("POST", "tickets", {
            "house_id": self._house,
            "theme": "Maintenance",
            "theme_icon": "wrench.and.screwdriver.fill",
            "problem": title.strip()[:80],
            "problem_icon": "checklist",
            "details": (details or "Ajouté depuis Home Assistant")[:500],
            "status": "sent",
            "author": "Home Assistant",
            "requested_priority": "normal",
        })
