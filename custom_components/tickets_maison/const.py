"""Constantes de l'intégration Tickets Maison."""
from datetime import timedelta

DOMAIN = "tickets_maison"
CONF_URL = "url"
CONF_KEY = "key"
CONF_HOUSE = "house_id"
CONF_CODE = "code"

SCAN_INTERVAL = timedelta(seconds=60)
EVENT_NEW_TICKET = "tickets_maison_nouveau_ticket"
