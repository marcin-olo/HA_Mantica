"""Calendar of lessons (timetable + substitutions), days off and homework."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import ManticaConfigEntry, extras
from .coordinator import ManticaCoordinator
from .sensor import _device

MAX_DAYS = 120  # longest range listed at once (school-year views stay cheap)


async def async_setup_entry(
    hass: HomeAssistant, entry: ManticaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ManticaLessonsCalendar(entry.runtime_data, entry)])


class ManticaLessonsCalendar(CoordinatorEntity[ManticaCoordinator], CalendarEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "lessons"
    _attr_icon = "mdi:school-outline"

    def __init__(self, coordinator: ManticaCoordinator, entry: ManticaConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_lessons"
        self._attr_device_info = _device(entry)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.get("timetable") is not None

    def _day_events(self, day: date) -> list[CalendarEvent]:
        d = self.coordinator.data
        tz = dt_util.get_default_time_zone()
        plan = extras.day_plan(d["timetable"], d["school_calendar"] or [], d["substitutions"] or [], day)
        out: list[CalendarEvent] = []
        if plan["day_off"] and plan["day_off"] != "weekend":
            out.append(CalendarEvent(start=day, end=day + timedelta(days=1), summary=plan["day_off"]))
        for lesson in plan["lessons"]:
            summary = f"{lesson['number']}. {lesson['subject']}"
            description = None
            if "substitute" in lesson:
                summary += " (zastępstwo)"
                description = f"Zastępstwo: {lesson['substitute']} za {lesson['absent_teacher']}"
            out.append(
                CalendarEvent(
                    start=datetime.combine(day, time.fromisoformat(lesson["start"]), tz),
                    end=datetime.combine(day, time.fromisoformat(lesson["end"]), tz),
                    summary=summary,
                    description=description,
                )
            )
        for hw in d["homework"] or []:
            if hw["due"] == day.isoformat():
                out.append(
                    CalendarEvent(
                        start=day,
                        end=day + timedelta(days=1),
                        summary=f"Zadanie: {hw['subject']}" + (f" - {hw['topic']}" if hw["topic"] else ""),
                        description=hw["content"] or None,
                    )
                )
        return out

    @property
    def event(self) -> CalendarEvent | None:
        """Current or next lesson (looks two weeks ahead)."""
        now = dt_util.now()
        today = now.date()
        for i in range(15):
            for ev in self._day_events(today + timedelta(days=i)):
                if isinstance(ev.start, datetime) and ev.end > now:
                    return ev
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        first = dt_util.as_local(start_date).date()
        # end_date is exclusive (a view ending at midnight does not include that day).
        last = min((dt_util.as_local(end_date) - timedelta(microseconds=1)).date(), first + timedelta(days=MAX_DAYS))
        out: list[CalendarEvent] = []
        day = first
        while day <= last:
            for ev in self._day_events(day):
                ev_start: Any = ev.start
                ev_end: Any = ev.end
                if isinstance(ev_start, datetime):
                    if ev_end > start_date and ev_start < end_date:
                        out.append(ev)
                else:
                    out.append(ev)
            day += timedelta(days=1)
        return out
