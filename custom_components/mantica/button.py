"""Button: mark the messages that are new in HA as read."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ManticaConfigEntry
from .coordinator import ManticaCoordinator
from .sensor import _device


async def async_setup_entry(
    hass: HomeAssistant, entry: ManticaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ManticaMarkReadButton(entry.runtime_data, entry)])


class ManticaMarkReadButton(CoordinatorEntity[ManticaCoordinator], ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "mark_messages_read"
    _attr_icon = "mdi:email-check"

    def __init__(self, coordinator: ManticaCoordinator, entry: ManticaConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_mark_messages_read"
        self._attr_device_info = _device(entry)

    async def async_press(self) -> None:
        await self.coordinator.async_mark_messages_read()
