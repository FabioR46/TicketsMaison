"""Constantes de l'intégration Tickets Maison."""
from datetime import timedelta

DOMAIN = "tickets_maison"
CONF_URL = "url"
CONF_KEY = "key"
CONF_HOUSE = "house_id"
CONF_CODE = "code"

SCAN_INTERVAL = timedelta(seconds=60)
EVENT_NEW_TICKET = "tickets_maison_nouveau_ticket"

# Entités Home Assistant remontées dans l'app (Options de l'intégration)
CONF_ENTITIES = "entities"
CONF_ALERT = "alert_unavailable"
ALERT_DELAY = 180          # secondes d'indisponibilité avant de créer un ticket
FLUSH_INTERVAL = timedelta(seconds=15)
RESYNC_INTERVAL = timedelta(minutes=10)

# Piles et batteries faibles
CONF_BATTERY = "battery_alert"
CONF_BATTERY_THRESHOLD = "battery_threshold"
DEFAULT_BATTERY_THRESHOLD = 20
BATTERY_HYSTERESIS = 10    # « pile changée » quand on repasse au-dessus du seuil + 10 %
