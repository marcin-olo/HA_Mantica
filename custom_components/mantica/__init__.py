"""Mantica school diary (dziennik elektroniczny) integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .api import ManticaClient, new_session
from .const import DOMAIN, ISSUE_ICON, ISSUE_LAYOUT, ISSUE_UNREACHABLE
from .coordinator import ManticaCoordinator
from .policy import FailurePolicy

PLATFORMS = [Platform.BUTTON, Platform.SENSOR]

type ManticaConfigEntry = ConfigEntry[ManticaCoordinator]


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
    for issue in (ISSUE_LAYOUT, ISSUE_UNREACHABLE, ISSUE_ICON):
        ir.async_delete_issue(hass, DOMAIN, f"{issue}_{entry.entry_id}")
