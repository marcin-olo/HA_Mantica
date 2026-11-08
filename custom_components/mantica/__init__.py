"""Mantica school diary (dziennik elektroniczny) integration."""
from __future__ import annotations

from pathlib import Path

import voluptuous as vol
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType

from .api import ManticaClient, new_session
from .const import DOMAIN, VERSION, ISSUE_EXTRA, ISSUE_ICON, ISSUE_LAYOUT, ISSUE_UNREACHABLE
from .coordinator import ManticaCoordinator
from .policy import FailurePolicy

PLATFORMS = [Platform.BUTTON, Platform.CALENDAR, Platform.SENSOR]

type ManticaConfigEntry = ConfigEntry[ManticaCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
SERVICE_MARK_READ = "mark_message_read"
CARD_URL = "/mantica_static/mantica-messages-card.js"
CARD_FILE = Path(__file__).parent / "frontend" / "mantica-messages-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    # Messages card: served by the integration, no separate frontend install.
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)]
    )
    add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")

    async def mark_read(call: ServiceCall) -> None:
        """Clear the "new" flag of one message (message_id) or of all of them."""
        message_id = call.data.get("message_id")
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.state is ConfigEntryState.LOADED:
                await entry.runtime_data.async_mark_messages_read(
                    {str(message_id)} if message_id else None
                )

    hass.services.async_register(
        DOMAIN,
        SERVICE_MARK_READ,
        mark_read,
        schema=vol.Schema({vol.Optional("message_id"): cv.string}),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ManticaConfigEntry) -> bool:
    # Own session = own cookie jar (the portal uses a PHP session cookie).
    # A plain aiohttp session (not HA's helper) because we close it ourselves
    # on unload / failed setup; HA warns when its helper sessions get closed.
    client = ManticaClient(
        new_session(),
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    # Failure counters live outside the entry so they survive setup retries.
    policy = hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, FailurePolicy())
    coordinator = ManticaCoordinator(hass, entry, client, policy)
    await coordinator.async_load()
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.async_close()
        raise
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    @callback
    def _new_day(_now) -> None:
        # "Today"/"tomorrow" sensors move on at midnight, without a portal read.
        if coordinator.data:
            coordinator.async_update_listeners()

    entry.async_on_unload(async_track_time_change(hass, _new_day, hour=0, minute=0, second=5))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ManticaConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ManticaConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.async_close()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ManticaConfigEntry) -> None:
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    for issue in (ISSUE_LAYOUT, ISSUE_UNREACHABLE, ISSUE_ICON, ISSUE_EXTRA):
        ir.async_delete_issue(hass, DOMAIN, f"{issue}_{entry.entry_id}")
