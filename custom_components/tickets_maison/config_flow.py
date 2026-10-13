"""Ajout de l'intégration : on colle simplement le code de connexion affiché par l'app."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HouseNotFound, InvalidAuth, InvalidCode, TicketsMaisonAPI, TicketsMaisonError, decode_code
from .const import (
    CONF_ALERT, CONF_BATTERY, CONF_BATTERY_THRESHOLD, CONF_CODE, CONF_ENTITIES, CONF_HOUSE, CONF_KEY,
    CONF_URL, DEFAULT_BATTERY_THRESHOLD, DOMAIN,
)

SCHEMA = vol.Schema({vol.Required(CONF_CODE): str})


class TicketsMaisonConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TicketsMaisonOptionsFlow()

    async def _check(self, code: str) -> tuple[dict[str, str] | None, str | None, str | None]:
        """Renvoie (données, nom de la maison, erreur)."""
        try:
            data = decode_code(code)
            summary = await TicketsMaisonAPI(
                async_get_clientsession(self.hass), data["url"], data["key"], data["house_id"]
            ).summary()
        except InvalidCode:
            return None, None, "invalid_code"
        except InvalidAuth:
            return None, None, "invalid_auth"
        except HouseNotFound:
            return None, None, "house_not_found"
        except TicketsMaisonError:
            return None, None, "cannot_connect"
        return {CONF_URL: data["url"], CONF_KEY: data["key"], CONF_HOUSE: data["house_id"]}, summary["house"], None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data, house, error = await self._check(user_input[CONF_CODE])
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(data[CONF_HOUSE])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=house, data=data)
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data, _house, error = await self._check(user_input[CONF_CODE])
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(self._get_reauth_entry(), data=data)
        return self.async_show_form(step_id="reauth_confirm", data_schema=SCHEMA, errors=errors)


class TicketsMaisonOptionsFlow(OptionsFlow):
    """« Configurer » : choisir les entités Home Assistant à afficher dans l'app."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        schema = vol.Schema({
            vol.Optional(CONF_ENTITIES, default=options.get(CONF_ENTITIES, [])):
                selector.EntitySelector(selector.EntitySelectorConfig(multiple=True)),
            vol.Optional(CONF_ALERT, default=options.get(CONF_ALERT, False)):
                selector.BooleanSelector(),
            vol.Optional(CONF_BATTERY, default=options.get(CONF_BATTERY, False)):
                selector.BooleanSelector(),
            vol.Optional(CONF_BATTERY_THRESHOLD,
                         default=options.get(CONF_BATTERY_THRESHOLD, DEFAULT_BATTERY_THRESHOLD)):
                selector.NumberSelector(selector.NumberSelectorConfig(
                    min=5, max=50, step=5, unit_of_measurement="%", mode=selector.NumberSelectorMode.SLIDER)),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
