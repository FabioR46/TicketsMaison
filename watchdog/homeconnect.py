"""
Tickets Maison — module Home Connect (Bosch, Siemens, Neff, Gaggenau…)
=======================================================================
Tourne dans le watchdog, à côté de la surveillance réseau. Tout se règle depuis l'app :

1. L'app enregistre le Client ID / Client Secret (table homeconnect, statut « login_requested »).
2. Le watchdog demande un code d'autorisation à Home Connect et l'écrit dans la table :
   l'app l'affiche avec un bouton « Autoriser chez Home Connect ».
3. Une fois autorisé, le watchdog écoute en continu les événements des appareils :
   - alerte (sel presque vide, porte du congélateur ouverte…) → ticket, message quand elle disparaît
   - appareil déconnecté plus de 3 minutes → ticket « Hors ligne », message à son retour
   La liste des appareils (et leurs alertes en cours) est écrite dans la table appliances.
"""

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = os.environ.get("HC_API", "https://api.home-connect.com").rstrip("/")
SCOPE = "IdentifyAppliance Monitor"
DISCONNECT_DELAY = int(os.environ.get("HC_DISCONNECT_DELAY", "180"))   # secondes avant un ticket « Hors ligne »
AUTHOR = "Home Connect"
ZONE = "Électroménager"
ZONE_ICON = "washer.fill"

# Alertes connues (clé Home Connect → libellé)
ALERT_LABELS = {
    "Dishcare.Dishwasher.Event.SaltNearlyEmpty": "Sel presque vide",
    "Dishcare.Dishwasher.Event.RinseAidNearlyEmpty": "Liquide de rinçage presque vide",
    "Dishcare.Dishwasher.Event.MachineCareReminder": "Entretien de la machine conseillé",
    "Dishcare.Dishwasher.Event.SaltLack": "Plus de sel",
    "Dishcare.Dishwasher.Event.RinseAidLack": "Plus de liquide de rinçage",
    "Dishcare.Dishwasher.Event.LowWaterPressure": "Pression d'eau trop faible",
    "Dishcare.Dishwasher.Event.CheckFilterSystem": "Vérifier le filtre",
    "Dishcare.Dishwasher.Event.DrainingNotPossible": "Vidange impossible",
    "Dishcare.Dishwasher.Event.DrainPumpBlocked": "Pompe de vidange bloquée",
    "Dishcare.Dishwasher.Event.WaterheaterCalcified": "Résistance entartrée",
    "Refrigeration.FridgeFreezer.Event.DoorAlarmFreezer": "Porte du congélateur ouverte",
    "Refrigeration.FridgeFreezer.Event.DoorAlarmRefrigerator": "Porte du réfrigérateur ouverte",
    "Refrigeration.FridgeFreezer.Event.TemperatureAlarmFreezer": "Température du congélateur trop haute",
    "Refrigeration.Common.Event.Dispenser.WaterFilterNearlyExhausted": "Filtre à eau bientôt usé",
    "LaundryCare.Washer.Event.IDos1FillLevelPoor": "Réservoir i-Dos 1 presque vide",
    "LaundryCare.Washer.Event.IDos2FillLevelPoor": "Réservoir i-Dos 2 presque vide",
    "LaundryCare.Common.Event.DrumCleanReminder": "Nettoyage du tambour conseillé",
    "LaundryCare.Dryer.Event.DryerCondensateContainerFull": "Bac à eau du sèche-linge plein",
    "ConsumerProducts.CoffeeMaker.Event.WaterTankEmpty": "Réservoir d'eau vide",
    "ConsumerProducts.CoffeeMaker.Event.BeanContainerEmpty": "Plus de café en grains",
    "ConsumerProducts.CoffeeMaker.Event.DripTrayFull": "Bac d'égouttage plein",
    "ConsumerProducts.CoffeeMaker.Event.DescalingIn5Cups": "Détartrage dans 5 tasses",
    "ConsumerProducts.CoffeeMaker.Event.DescalingIn0Cups": "Détartrage nécessaire",
    "ConsumerProducts.CoffeeMaker.Event.CalcNCleanIn5Cups": "Entretien dans 5 tasses",
    "ConsumerProducts.CoffeeMaker.Event.CalcNCleanIn0Cups": "Entretien nécessaire",
    "Cooking.Common.Event.Hood.GreaseFilterMaxSaturationNearlyReached": "Filtre à graisse bientôt saturé",
    "Cooking.Common.Event.Hood.GreaseFilterMaxSaturationReached": "Filtre à graisse saturé",
    "ConsumerProducts.CleaningRobot.Event.EmptyDustBoxAndCleanFilter": "Vider le bac à poussière",
    "ConsumerProducts.CleaningRobot.Event.RobotIsStuck": "Robot bloqué",
    "ConsumerProducts.CleaningRobot.Event.DockingStationNotFound": "Base introuvable",
}
# Événements simplement informatifs : jamais de ticket
IGNORED = re.compile(r"(ProgramFinished|ProgramAborted|AlarmClockElapsed|PreheatFinished|"
                     r"RemainingProgramTime|FinishInRelative|StartInRelative)$")
# Autres événements considérés comme une alerte
ALERT_PATTERN = re.compile(r"(Alarm|NearlyEmpty|Empty|Full|Poor|Lack|Saturation|Exhausted|"
                           r"Descaling|Blocked|Stuck|NotPossible|Error|Fault|Calcified|Check)")

TYPE_NAMES = {
    "Dishwasher": "Lave-vaisselle", "Washer": "Lave-linge", "Dryer": "Sèche-linge",
    "WasherDryer": "Lavante-séchante", "Oven": "Four", "CoffeeMaker": "Machine à café",
    "FridgeFreezer": "Réfrigérateur-congélateur", "Refrigerator": "Réfrigérateur",
    "Freezer": "Congélateur", "Hood": "Hotte", "Hob": "Plaque de cuisson",
    "CookProcessor": "Robot cuiseur", "WineCooler": "Cave à vin", "CleaningRobot": "Robot aspirateur",
    "WarmingDrawer": "Tiroir chauffant", "Microwave": "Micro-ondes",
}
TYPE_ICONS = {
    "Dishwasher": "dishwasher.fill", "Washer": "washer.fill", "Dryer": "dryer.fill",
    "WasherDryer": "washer.fill", "Oven": "oven.fill", "CoffeeMaker": "cup.and.saucer.fill",
    "FridgeFreezer": "refrigerator.fill", "Refrigerator": "refrigerator.fill",
    "Freezer": "refrigerator.fill", "Hood": "fan.fill", "Hob": "cooktop.fill",
    "Microwave": "microwave.fill", "CleaningRobot": "fan.fill",
}


def label_for(key):
    if key in ALERT_LABELS:
        return ALERT_LABELS[key]
    last = key.split(".")[-1]
    return re.sub(r"(?<!^)(?=[A-Z])", " ", last).capitalize()


def is_alert(key):
    if key in ALERT_LABELS:
        return True
    if ".Event." not in key:
        return False
    last = key.split(".")[-1]
    return not IGNORED.search(last) and bool(ALERT_PATTERN.search(last))


def is_present(value):
    """Valeur d'un événement : Present = actif ; Off / Confirmed = terminé."""
    return isinstance(value, str) and value.endswith(".Present")


def now_utc():
    return datetime.now(timezone.utc)


class HCError(Exception):
    pass


class HomeConnectWorker(threading.Thread):
    def __init__(self, db, house_id, log, stop, local_time):
        super().__init__(daemon=True, name="homeconnect")
        self.db, self.house, self.log, self.stop, self.local = db, house_id, log, stop, local_time
        self.cfg = None
        self.access_token = None
        self.access_expires = now_utc()
        self.appliances = {}          # haId → ligne de la table appliances
        self.disconnected_at = {}     # haId → date de déconnexion
        self.offline_alerted = set()  # haId déjà signalés hors ligne
        self.table_ok = True

    # ── Supabase ──────────────────────────────────────────────────────────

    def _db(self, method, path, body=None, prefer="return=representation"):
        headers = dict(self.db.headers)
        headers["Prefer"] = prefer
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.db.base}/rest/v1/{path}", data=data,
                                     method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method} {path} → HTTP {e.code} : {e.read().decode(errors='replace')}")

    def load_cfg(self):
        rows = self._db("GET", f"homeconnect?house_id=eq.{self.house}&select=*")
        return rows[0] if rows else None

    def save_cfg(self, **changes):
        changes["updated_at"] = now_utc().isoformat()
        self._db("PATCH", f"homeconnect?house_id=eq.{self.house}", changes, prefer="return=minimal")
        if self.cfg is not None:
            self.cfg.update(changes)

    def save_appliance(self, ha_id):
        row = dict(self.appliances[ha_id])
        row["house_id"] = self.house
        row["updated_at"] = now_utc().isoformat()
        self._db("POST", "appliances?on_conflict=house_id,ha_id", [row],
                 prefer="resolution=merge-duplicates,return=minimal")

    def create_ticket(self, appliance, problem, details, icon):
        rows = self._db("POST", "tickets", {
            "house_id": self.house, "theme": ZONE, "theme_icon": ZONE_ICON,
            "problem": problem[:80], "problem_icon": icon,
            "details": details[:500], "status": "sent", "author": AUTHOR,
            "requested_priority": "normal",
        })
        return rows[0]["id"] if rows else None

    def add_message(self, ticket_id, text):
        try:
            self._db("POST", "messages", {"ticket_id": ticket_id, "text": text[:500],
                                          "author": AUTHOR, "from_admin": False},
                     prefer="return=minimal")
        except RuntimeError as e:
            self.log(f"⚠️ Home Connect : message non envoyé ({e})")

    # ── OAuth (device flow) ───────────────────────────────────────────────

    def _form(self, path, fields):
        data = urllib.parse.urlencode(fields).encode()
        req = urllib.request.Request(f"{API}{path}", data=data, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read() or b"{}")
            except ValueError:
                body = {}
            body.setdefault("error", f"http_{e.code}")
            return body

    def token_request(self, fields):
        """Demande de jeton. Si Home Connect refuse le Client Secret (application « publique »
        ou secret mal copié), on réessaie sans : le Device Flow n'en a pas toujours besoin."""
        secret = (self.cfg.get("client_secret") or "").strip()
        if secret and not self.cfg.get("_skip_secret"):
            answer = self._form("/security/oauth/token", dict(fields, client_secret=secret))
            text = f"{answer.get('error', '')} {answer.get('error_description', '')}".lower()
            if "access_token" in answer or not ("secret" in text or "invalid_client" in text):
                return answer
            self.log("ℹ️ Home Connect refuse le Client Secret : nouvel essai sans")
            self.cfg["_skip_secret"] = True
        return self._form("/security/oauth/token", fields)

    def login(self):
        """Demande un code, l'affiche dans l'app, attend la validation."""
        cfg = self.cfg
        answer = self._form("/security/oauth/device_authorization",
                            {"client_id": cfg["client_id"], "scope": SCOPE})
        if "device_code" not in answer:
            desc = answer.get("error_description") or answer.get("error")
            self.save_cfg(status="error", error=f"Home Connect refuse le Client ID ({desc}). "
                                                "Vérifie-le, ou attends quelques minutes après "
                                                "la création de l'application.")
            return
        expires = now_utc() + timedelta(seconds=int(answer.get("expires_in", 300)))
        self.save_cfg(status="awaiting_user", user_code=answer.get("user_code"),
                      verification_uri=answer.get("verification_uri_complete") or answer.get("verification_uri"),
                      code_expires_at=expires.isoformat(), error=None)
        self.log(f"🔑 Home Connect : code {answer.get('user_code')} affiché dans l'app")
        interval = int(answer.get("interval", 5))
        while not self.stop["now"] and now_utc() < expires:
            time.sleep(interval)
            token = self.token_request({"grant_type": "device_code", "device_code": answer["device_code"],
                                        "client_id": cfg["client_id"]})
            if "access_token" in token:
                self._store_token(token)
                self.save_cfg(status="connected", user_code=None, verification_uri=None,
                              code_expires_at=None, error=None)
                self.log("✅ Home Connect connecté")
                return
            err = token.get("error")
            if err == "slow_down":
                interval += 5
            elif err != "authorization_pending":
                # Annulation, ou l'utilisateur a relancé la connexion depuis l'app
                latest = self.load_cfg()
                if latest is None or latest.get("status") == "login_requested":
                    return
                desc = token.get('error_description') or err
                hint = (" Vérifie le Client Secret : recopie-le en entier depuis le portail Home Connect "
                        "(Modifier les identifiants)." if "secret" in str(desc).lower() else "")
                self.save_cfg(status="error", user_code=None, verification_uri=None,
                              error=f"Autorisation refusée ou impossible ({desc}).{hint}")
                return
        if not self.stop["now"]:
            self.save_cfg(status="error", user_code=None, verification_uri=None,
                          error="Le code a expiré : touche « Recommencer » dans l'app.")

    def _store_token(self, token):
        self.access_token = token["access_token"]
        self.access_expires = now_utc() + timedelta(seconds=int(token.get("expires_in", 86400)) - 600)
        if token.get("refresh_token"):
            self.save_cfg(refresh_token=token["refresh_token"])

    def ensure_token(self, force=False):
        if self.access_token and not force and now_utc() < self.access_expires:
            return
        cfg = self.cfg
        token = self.token_request({"grant_type": "refresh_token", "refresh_token": cfg.get("refresh_token") or "",
                                    "client_id": cfg["client_id"]})
        if "access_token" not in token:
            self.access_token = None
            self.save_cfg(status="error", error="Connexion Home Connect expirée : touche « Recommencer » "
                                                "dans l'app pour autoriser à nouveau.")
            raise HCError("refresh impossible")
        self._store_token(token)

    # ── API Home Connect ──────────────────────────────────────────────────

    def api_get(self, path):
        self.ensure_token()
        req = urllib.request.Request(f"{API}{path}", headers={
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/vnd.bsh.sdk.v1+json", "Accept-Language": "fr-FR"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self.ensure_token(force=True)
            raise HCError(f"GET {path} → HTTP {e.code}")

    def sync_appliances(self):
        data = self.api_get("/api/homeappliances").get("data", {}).get("homeappliances", [])
        known = {r["ha_id"]: r for r in self._db("GET", f"appliances?house_id=eq.{self.house}&select=*") or []}
        seen = set()
        for a in data:
            ha_id = a["haId"]
            seen.add(ha_id)
            row = known.get(ha_id, {"ha_id": ha_id, "alerts": [], "open_ticket_id": None})
            row.update({"name": a.get("name") or TYPE_NAMES.get(a.get("type"), a.get("type", "Appareil")),
                        "brand": a.get("brand"), "type": a.get("type"),
                        "connected": bool(a.get("connected", True))})
            self.appliances[ha_id] = row
            self.save_appliance(ha_id)
            if not row["connected"]:
                self.disconnected_at.setdefault(ha_id, now_utc())
        for ha_id in set(known) - seen:   # appareil retiré du compte Home Connect
            self._db("DELETE", f"appliances?house_id=eq.{self.house}&ha_id=eq.{urllib.parse.quote(ha_id)}",
                     prefer="return=minimal")
            self.appliances.pop(ha_id, None)
        self.log(f"🏠 Home Connect : {len(data)} appareil(s)")

    def display_name(self, row):
        kind = TYPE_NAMES.get(row.get("type"), "")
        name = row.get("name") or kind or "Appareil"
        return name if (not kind or kind.lower() in name.lower()) else f"{kind} {name}"

    # ── Événements ────────────────────────────────────────────────────────

    def on_alert(self, ha_id, key, value):
        row = self.appliances.get(ha_id)
        if row is None:
            return
        alerts = [a for a in row.get("alerts") or [] if a.get("key") != key]
        label = label_for(key)
        name = self.display_name(row)
        icon = TYPE_ICONS.get(row.get("type"), "exclamationmark.triangle.fill")
        if is_present(value):
            alerts.append({"key": key, "label": label, "since": now_utc().isoformat()})
            row["alerts"] = alerts
            if row.get("open_ticket_id"):
                self.add_message(row["open_ticket_id"], f"⚠️ Nouvelle alerte : {label}.")
            else:
                row["open_ticket_id"] = self.create_ticket(
                    row, f"{name} : {label}",
                    f"Home Connect signale « {label} » sur {name} ({row.get('brand') or ''}) "
                    f"le {self.local(now_utc()).strftime('%d/%m à %H:%M')}.", icon)
            self.log(f"⚠️ {name} : {label}")
        else:
            had = len(alerts) != len(row.get("alerts") or [])
            row["alerts"] = alerts
            if had and row.get("open_ticket_id"):
                self.add_message(row["open_ticket_id"], f"✅ {label} : c'est réglé.")
                if not alerts and row.get("connected", True):
                    row["open_ticket_id"] = None
            self.log(f"✅ {name} : fin de « {label} »")
        self.save_appliance(ha_id)

    def on_connection(self, ha_id, connected):
        row = self.appliances.get(ha_id)
        if row is None:
            return
        row["connected"] = connected
        name = self.display_name(row)
        if connected:
            self.disconnected_at.pop(ha_id, None)
            if row.get("open_ticket_id") and ha_id in self.offline_alerted:
                self.add_message(row["open_ticket_id"],
                                 f"✅ {name} est de nouveau connecté "
                                 f"({self.local(now_utc()).strftime('%d/%m à %H:%M')}).")
                if not row.get("alerts"):
                    row["open_ticket_id"] = None
            self.offline_alerted.discard(ha_id)
            self.log(f"✅ {name} reconnecté")
        else:
            self.disconnected_at.setdefault(ha_id, now_utc())
            self.log(f"… {name} déconnecté")
        self.save_appliance(ha_id)

    def check_disconnections(self):
        for ha_id, since in list(self.disconnected_at.items()):
            row = self.appliances.get(ha_id)
            if row is None or row.get("connected", True) or ha_id in self.offline_alerted:
                continue
            if now_utc() - since < timedelta(seconds=DISCONNECT_DELAY):
                continue
            name = self.display_name(row)
            text = (f"{name} ne répond plus à Home Connect depuis le "
                    f"{self.local(since).strftime('%d/%m à %H:%M')} (Wi-Fi coupé, appareil débranché ?).")
            if row.get("open_ticket_id"):
                self.add_message(row["open_ticket_id"], "📡 " + text)
            else:
                row["open_ticket_id"] = self.create_ticket(row, f"Hors ligne : {name}", text,
                                                           "wifi.exclamationmark")
            self.offline_alerted.add(ha_id)
            self.save_appliance(ha_id)
            self.log(f"📡 {name} hors ligne : ticket créé")

    def handle_event(self, kind, ha_id, data):
        if kind in ("CONNECTED", "DISCONNECTED"):
            self.on_connection(ha_id, kind == "CONNECTED")
        elif kind in ("PAIRED", "DEPAIRED"):
            self.sync_appliances()
        elif kind in ("EVENT", "NOTIFY", "STATUS") and data:
            try:
                items = json.loads(data).get("items", [])
            except ValueError:
                return
            for item in items:
                key = item.get("key", "")
                target = item.get("haId") or ha_id
                if is_alert(key):
                    self.on_alert(target, key, item.get("value"))

    def stream(self):
        """Écoute les événements de tous les appareils (connexion longue, reconnexion auto)."""
        self.ensure_token()
        req = urllib.request.Request(f"{API}/api/homeappliances/events", headers={
            "Authorization": f"Bearer {self.access_token}", "Accept": "text/event-stream",
            "Accept-Language": "fr-FR"})
        last_cfg_check = time.monotonic()
        with urllib.request.urlopen(req, timeout=90) as resp:
            kind, ha_id, data = None, None, []
            for raw in resp:
                if self.stop["now"]:
                    return
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if line == "":
                    if kind:
                        self.handle_event(kind, ha_id, "\n".join(data))
                    kind, ha_id, data = None, None, []
                    self.check_disconnections()
                    if time.monotonic() - last_cfg_check > 60:
                        last_cfg_check = time.monotonic()
                        latest = self.load_cfg()
                        if latest is None or latest.get("status") != "connected" \
                                or latest.get("client_id") != self.cfg.get("client_id"):
                            return   # déconnecté ou relancé depuis l'app
                        if now_utc() >= self.access_expires:
                            return   # nouveau jeton puis reconnexion
                elif line.startswith("event:"):
                    kind = line[6:].strip()
                elif line.startswith("id:"):
                    ha_id = line[3:].strip()
                elif line.startswith("data:"):
                    data.append(line[5:].strip())

    # ── Boucle principale ─────────────────────────────────────────────────

    def run(self):
        backoff = 10
        while not self.stop["now"]:
            try:
                self.cfg = self.load_cfg()
                self.table_ok = True
            except RuntimeError as e:
                if self.table_ok and ("PGRST205" in str(e) or "404" in str(e)):
                    self.log("ℹ️ Home Connect inactif (exécute supabase_v7.sql pour l'activer)")
                self.table_ok = False
                self._sleep(300)
                continue
            cfg = self.cfg
            try:
                if not cfg:
                    self.access_token = None
                    self._sleep(30)
                elif cfg["status"] == "login_requested":
                    self.access_token = None
                    self.login()
                elif cfg["status"] == "connected" and cfg.get("refresh_token"):
                    self.sync_appliances()
                    self.stream()
                    backoff = 10
                else:
                    self._sleep(15)   # en attente d'une action dans l'app
            except HCError as e:
                self.log(f"⚠️ Home Connect : {e}")
                self._sleep(backoff)
                backoff = min(backoff * 2, 600)
            except Exception as e:  # réseau coupé, flux interrompu…
                self.log(f"⚠️ Home Connect : {e} — nouvelle tentative dans {backoff} s")
                self._sleep(backoff)
                backoff = min(backoff * 2, 600)

    def _sleep(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end and not self.stop["now"]:
            time.sleep(1)
