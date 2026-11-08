"""Config flow: host + parent login/password, entered in the HA UI."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

from .api import (
    ManticaAuthError,
    ManticaClient,
    ManticaConnectionError,
    new_session,
    normalize_host,
)
from .const import (
    CONF_ACTIVE_FROM,
    CONF_ACTIVE_TO,
    CONF_SCAN_MINUTES,
    DEFAULT_ACTIVE_FROM,
    DEFAULT_ACTIVE_TO,
    DEFAULT_SCAN_MINUTES,
    DOMAIN,
    MIN_SCAN_MINUTES,
)


class ManticaConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ManticaOptionsFlow()

    async def _try_login(self, host: str, user: str, pw: str) -> str | None:
        client = ManticaClient(new_session(), host, user, pw)
        try:
            await client.login()
        except ManticaAuthError:
            return "invalid_auth"
        except ManticaConnectionError:
            return "cannot_connect"
        finally:
            await client.async_close()
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = normalize_host(user_input[CONF_HOST])
            user = user_input[CONF_USERNAME].strip()
            await self.async_set_unique_id(f"{host}|{user.lower()}")
            self._abort_if_unique_id_configured()
            err = await self._try_login(host, user, user_input[CONF_PASSWORD])
            if err:
                errors["base"] = err
            else:
                return self.async_create_entry(
                    title=f"{host.split('://')[-1]} ({user})",
                    data={
                        CONF_HOST: host,
                        CONF_USERNAME: user,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=(user_input or {}).get(CONF_HOST, "https://"),
                    ): str,
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            err = await self._try_login(
                entry.data[CONF_HOST], entry.data[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if err:
                errors["base"] = err
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )


class ManticaOptionsFlow(OptionsFlow):
    """How often and in which hours the portal is read."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        opts = self.config_entry.options
        if user_input is not None:
            if user_input[CONF_ACTIVE_FROM] >= user_input[CONF_ACTIVE_TO]:
                errors["base"] = "bad_hours"
            else:
                return self.async_create_entry(data=user_input)
        current = user_input or opts
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_MINUTES,
                        default=current.get(CONF_SCAN_MINUTES, DEFAULT_SCAN_MINUTES),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_MINUTES, max=24 * 60)),
                    vol.Required(
                        CONF_ACTIVE_FROM,
                        default=current.get(CONF_ACTIVE_FROM, DEFAULT_ACTIVE_FROM),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
                    vol.Required(
                        CONF_ACTIVE_TO,
                        default=current.get(CONF_ACTIVE_TO, DEFAULT_ACTIVE_TO),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
                }
            ),
            errors=errors,
        )
