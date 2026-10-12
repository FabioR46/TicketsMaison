"""
Tickets Maison — Watchdog réseau
================================
Surveille les appareils déclarés dans l'app (Réglages › Paramètres de la maison
› Surveillance réseau) et crée automatiquement un ticket quand l'un d'eux ne
répond plus.

Configuration (variables d'environnement, voir .env.example) :
  TM_CODE        code de connexion copié depuis l'app (remplace les 3 suivantes)
  SUPABASE_URL   https://xxxx.supabase.co
  SUPABASE_KEY   clé anon / publishable de l'app
  HOUSE_ID       ID de la maison (copié depuis l'app)
  INTERVAL       secondes entre deux tours (défaut 60)
  FAILS          échecs consécutifs avant alerte (défaut 3)
  TIMEOUT        délai d'attente d'un test, en secondes (défaut 3)
  TZ             fuseau horaire pour les messages (ex. Europe/Paris)
"""

import json
import os
import platform
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# ── Configuration ────────────────────────────────────────────────────────

def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if value is not None:
        # Tolère les espaces et guillemets collés par erreur dans le .env
        value = value.strip().strip('"').strip("'").strip()
    if required and (not value or "TON-PROJET" in value or "COLLE-TA-CLE" in value
                     or value.startswith("00000000")):
        sys.exit(f"[watchdog] Variable manquante : {name} (voir .env.example)")
    return value

def decode_code(code):
    """Code de connexion « TM1:… » affiché par l'app → (url, clé, id maison)."""
    import base64
    raw = code.strip().replace(" ", "").replace("\n", "")
    if raw.upper().startswith("TM1:"):
        raw = raw[4:]
    try:
        raw += "=" * (-len(raw) % 4)
        data = json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
        return str(data["u"]), str(data["k"]), str(data["h"])
    except Exception:
        sys.exit("[watchdog] Code de connexion illisible : recopie-le en entier depuis l'app "
                 "(Paramètres de la maison › Appareils › Copier le code).")


# Le plus simple : un seul code de connexion (TM_CODE), sinon les 3 variables séparées
_CODE = env("TM_CODE")
if _CODE and not _CODE.startswith("COLLE"):
    _url, _key, _house = decode_code(_CODE)
    os.environ.setdefault("SUPABASE_URL", _url)
    os.environ.setdefault("SUPABASE_KEY", _key)
    os.environ.setdefault("HOUSE_ID", _house)

BASE = env("SUPABASE_URL", required=True).rstrip("/")
if BASE.endswith("/rest/v1"):
    BASE = BASE[: -len("/rest/v1")]
KEY = env("SUPABASE_KEY", required=True)
HOUSE_ID = env("HOUSE_ID", required=True).strip().lower()
INTERVAL = int(env("INTERVAL", "60"))
FAILS = max(1, int(env("FAILS", "3")))
TIMEOUT = float(env("TIMEOUT", "3"))

AUTHOR = "Watchdog"
ZONE_NAME = "Surveillance réseau"
ZONE_ICON = "antenna.radiowaves.left.and.right"
PROBLEM_ICON = "wifi.exclamationmark"


def log(message):
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)


# ── Mini client Supabase (PostgREST) ─────────────────────────────────────

class Supabase:
    def __init__(self, base, key):
        self.base = base
        self.headers = {
            "apikey": key,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        if key.startswith("eyJ"):  # ancienne clé anon (JWT)
            self.headers["Authorization"] = f"Bearer {key}"

    def request(self, method, table, query=None, body=None):
        url = f"{self.base}/rest/v1/{table}"
        if query:
            url += "?" + urllib.parse.urlencode(query, safe="=.,()*:")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=self.headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            raise RuntimeError(f"{method} {table} → HTTP {e.code} : {detail}") from None

    def select(self, table, **filters):
        return self.request("GET", table, query=filters)

    def insert(self, table, row):
        result = self.request("POST", table, body=row)
        return result[0] if result else None

    def update(self, table, row_id, changes):
        return self.request("PATCH", table, query={"id": f"eq.{row_id}"}, body=changes)

    def update_where(self, table, filters, changes):
        return self.request("PATCH", table, query=filters, body=changes)


# Historique des coupures (table device_events, créée par supabase_v3.sql).
# Facultatif : si la table n'existe pas encore, la surveillance continue sans historique.
HISTORY = {"ok": True}


def record_outage_start(db, device, started):
    if not HISTORY["ok"]:
        return
    try:
        db.insert("device_events", {"device_id": device["id"], "house_id": HOUSE_ID,
                                    "started_at": iso(started)})
    except RuntimeError as e:
        HISTORY["ok"] = False
        log(f"ℹ️ Historique des coupures indisponible (exécute supabase_v3.sql) : {e}")


def record_outage_end(db, device, ended):
    if not HISTORY["ok"]:
        return
    try:
        db.update_where("device_events", {"device_id": f"eq.{device['id']}", "ended_at": "is.null"},
                        {"ended_at": iso(ended)})
    except RuntimeError as e:
        HISTORY["ok"] = False
        log(f"ℹ️ Historique des coupures indisponible (exécute supabase_v3.sql) : {e}")


# ── Tests de connectivité ────────────────────────────────────────────────

IS_WINDOWS = platform.system() == "Windows"


def ping(host):
    """Un ping ICMP. Renvoie True si l'appareil répond."""
    if IS_WINDOWS:
        cmd = ["ping", "-n", "1", "-w", str(int(TIMEOUT * 1000)), host]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, int(TIMEOUT))), host]
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=TIMEOUT + 2)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def tcp(host, port):
    """Ouvre une connexion TCP. Renvoie True si le port répond."""
    try:
        with socket.create_connection((host, int(port)), timeout=TIMEOUT):
            return True
    except OSError:
        return False


def is_up(device):
    # Deux essais rapprochés pour éviter les faux positifs (paquet perdu)
    for attempt in range(2):
        ok = tcp(device["host"], device["port"]) if device.get("port") else ping(device["host"])
        if ok:
            return True
        if attempt == 0:
            time.sleep(1)
    return False


# ── Logique de surveillance ──────────────────────────────────────────────

def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat()


def parse(ts):
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def local(dt):
    return dt.astimezone().strftime("%d/%m/%Y à %H:%M:%S")


def duration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} s"
    minutes, _ = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts = []
    if days:
        parts.append(f"{days} j")
    if hours:
        parts.append(f"{hours} h")
    if minutes:
        parts.append(f"{minutes} min")
    return " ".join(parts)


def address(device):
    return f"{device['host']}:{device['port']}" if device.get("port") else f"{device['host']} (ping)"


def check(db, device):
    up = is_up(device)
    t = now_utc()
    changes = {"last_check": iso(t)}

    if up:
        changes["last_seen"] = iso(t)
        if device["status"] == "down":
            # Retour en ligne → message sur le ticket ouvert
            down_since = parse(device.get("down_since")) or t
            outage = (t - down_since).total_seconds()
            log(f"✅ {device['name']} de retour ({duration(outage)} de coupure)")
            if device.get("open_ticket_id"):
                text = (f"✅ De retour en ligne le {local(t)} "
                        f"après {duration(outage)} de coupure.")
                db.insert("messages", {"ticket_id": device["open_ticket_id"], "text": text,
                                       "author": AUTHOR, "from_admin": True})
                # Touche le ticket (updated_at) pour qu'il remonte en tête de liste
                db.update("tickets", device["open_ticket_id"], {"theme": ZONE_NAME})
            record_outage_end(db, device, t)
            changes.update(status="up", fail_count=0, first_fail_at=None,
                           down_since=None, open_ticket_id=None)
        elif device["status"] != "up" or device["fail_count"]:
            if device["status"] == "unknown":
                log(f"🟢 {device['name']} en ligne")
            changes.update(status="up", fail_count=0, first_fail_at=None)
    else:
        fails = device["fail_count"] + 1
        first_fail = parse(device.get("first_fail_at")) or t
        changes.update(fail_count=fails, first_fail_at=iso(first_fail))

        if fails >= FAILS and device["status"] != "down":
            log(f"🔴 {device['name']} hors ligne depuis {local(first_fail)}")
            last_seen = parse(device.get("last_seen"))
            details = (f"L'appareil « {device['name']} » ({address(device)}) ne répond plus "
                       f"depuis le {local(first_fail)} ({fails} vérifications échouées).")
            if last_seen:
                details += f" Dernière réponse : {local(last_seen)}."
            ticket = db.insert("tickets", {
                "house_id": HOUSE_ID,
                "theme": ZONE_NAME,
                "theme_icon": ZONE_ICON,
                "problem": f"Hors ligne : {device['name']}",
                "problem_icon": device.get("icon") or PROBLEM_ICON,
                "details": details[:500],
                "status": "sent",
                "author": AUTHOR,
            })
            record_outage_start(db, device, first_fail)
            changes.update(status="down", down_since=iso(first_fail),
                           open_ticket_id=ticket["id"] if ticket else None)
        elif device["status"] != "down":
            log(f"… {device['name']} ne répond pas ({fails}/{FAILS})")

    db.update("monitored_devices", device["id"], changes)


def run_once(db):
    devices = db.select("monitored_devices", house_id=f"eq.{HOUSE_ID}", enabled="eq.true",
                        select="id,name,host,port,icon,status,fail_count,first_fail_at,"
                               "down_since,last_seen,open_ticket_id")
    for device in devices or []:
        try:
            check(db, device)
        except Exception as e:  # un appareil en erreur ne bloque pas les autres
            log(f"⚠️ {device.get('name')} : {e}")
    db.update("houses", HOUSE_ID, {"watchdog_seen_at": iso(now_utc())})
    return len(devices or [])


def main():
    db = Supabase(BASE, KEY)
    log(f"Connexion à {BASE} avec la clé {KEY[:12]}…{KEY[-4:]} ({len(KEY)} caractères)")
    try:
        houses = db.select("houses", id=f"eq.{HOUSE_ID}", select="id,name")
    except RuntimeError as e:
        if "401" in str(e):
            log("❌ Clé refusée par Supabase. Vérifie SUPABASE_KEY et SUPABASE_URL dans .env : "
                "mêmes valeurs que SupabaseConfig.swift, sans guillemets ni espaces. "
                "Puis : docker compose up -d")
            time.sleep(300)   # évite de redémarrer en boucle
            sys.exit(1)
        raise
    if not houses:
        sys.exit(f"[watchdog] Maison introuvable : {HOUSE_ID}. Copie l'ID depuis l'app "
                 "(Paramètres de la maison › Surveillance réseau).")
    log(f"Watchdog démarré pour « {houses[0]['name']} » — un tour toutes les {INTERVAL} s, "
        f"alerte après {FAILS} échecs")

    stop = {"now": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(now=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(now=True))

    # Électroménager Home Connect (activé depuis l'app, voir homeconnect.py)
    try:
        from homeconnect import HomeConnectWorker
        HomeConnectWorker(db, HOUSE_ID, log, stop, lambda dt: dt.astimezone()).start()
    except Exception as e:
        log(f"⚠️ Module Home Connect indisponible : {e}")

    first = True
    while not stop["now"]:
        started = time.monotonic()
        try:
            count = run_once(db)
            if first:
                log(f"{count} appareil(s) surveillé(s)")
                first = False
        except Exception as e:
            log(f"⚠️ Supabase injoignable : {e}")
        # Attente découpée pour s'arrêter vite
        remaining = INTERVAL - (time.monotonic() - started)
        while remaining > 0 and not stop["now"]:
            time.sleep(min(1, remaining))
            remaining -= 1
    log("Watchdog arrêté")


if __name__ == "__main__":
    main()
