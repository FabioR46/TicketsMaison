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

    async def _write(self, method: str, path: str, body: dict[str, Any]) -> None:
        headers = {**self._headers, "Prefer": "return=minimal"}
        try:
            async with self._session.request(
                method, f"{self._rest}/{path}", headers=headers, json=body,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (401, 403):
                    raise InvalidAuth
                if resp.status >= 400:
                    raise TicketsMaisonError(f"Erreur Supabase {resp.status}: {await resp.text()}")
        except aiohttp.ClientError as err:
            raise TicketsMaisonError(f"Connexion impossible : {err}") from err

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
