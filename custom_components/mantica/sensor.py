"""Sensors for the Mantica school diary."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import ManticaConfigEntry, extras
from .const import DOMAIN
from .coordinator import ManticaCoordinator

# The recorder drops attributes above 16 KB, so lists are capped and long
# texts shortened. Full texts stay in the diary itself.
MAX_TEXT = 200


def _short(value: Any, n: int = MAX_TEXT) -> Any:
    if isinstance(value, str) and len(value) > n:
        return value[: n - 1] + "…"
    return value


def _pick(item: dict[str, Any], keys: tuple[str, ...], n: int = MAX_TEXT) -> dict[str, Any]:
    return {k: _short(item.get(k), n) for k in keys}


EVENT_KEYS = ("name", "date", "days_left", "teacher", "description", "is_test")
GRADE_KEYS = ("subject", "value", "date", "description", "weight", "teacher")
MESSAGE_KEYS = ("id", "subject", "sender", "received", "has_attachment", "new")
# Whole inbox page fits: 10 bodies x 1500 chars stays well under 16 KB.
MAX_BODY = 1500


def _message(m: dict[str, Any], n: int = MAX_TEXT) -> dict[str, Any]:
    return {**_pick(m, MESSAGE_KEYS, n), "body": _short(m.get("body"), MAX_BODY)}


def _event_attrs(e: dict[str, Any] | None) -> dict[str, Any]:
    if not e:
        return {}
    attrs = _pick(e, EVENT_KEYS, 500)
    attrs.pop("name")
    return attrs


@dataclass(frozen=True, kw_only=True)
class ManticaDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] = lambda d: {}
    # Data key of an extra page; the sensor is unavailable when it failed.
    section: str | None = None


def _today() -> date:
    return dt_util.now().date()


def _plan(d: dict[str, Any], offset: int) -> dict[str, Any]:
    return extras.day_plan(
        d["timetable"], d["school_calendar"] or [], d["substitutions"] or [], _today() + timedelta(days=offset)
    )


def _plan_attrs(plan: dict[str, Any]) -> dict[str, Any]:
    lessons = plan["lessons"]
    return {
        "date": plan["date"],
        "weekday": plan["weekday"],
        "day_off": plan["day_off"],
        "start": lessons[0]["start"] if lessons else None,
        "end": lessons[-1]["end"] if lessons else None,
        "substitutions": sum(1 for lesson in lessons if "substitute" in lesson),
        "lessons": lessons,
    }


def _upcoming_subs(d: dict[str, Any]) -> list[dict[str, Any]]:
    today = _today().isoformat()
    return sorted((s for s in d["substitutions"] if s["date"] >= today), key=lambda s: (s["date"], s["lesson"]))


def _open_homework(d: dict[str, Any]) -> list[dict[str, Any]]:
    today = _today().isoformat()
    return [h for h in d["homework"] if h["due"] >= today]


SUB_KEYS = ("date", "lesson", "subject", "absent_teacher", "substitute", "added")
REMARK_KEYS = ("kind", "text", "date", "teacher")
HOMEWORK_KEYS = ("subject", "topic", "assigned", "due", "content", "teacher")


SENSORS: tuple[ManticaDescription, ...] = (
    ManticaDescription(
        key="unread_messages",
        translation_key="unread_messages",
        icon="mdi:email-alert",
        # "New" as tracked in HA: fetching a body marks it read on the portal.
        value_fn=lambda d: len(d["new_messages"]),
        attrs_fn=lambda d: {
            "messages": [_message(m, 120) for m in d["new_messages"][:10]],
            "unread_on_portal": len(d["unread"]),
            "unrecognised_icons": len(d["unknown_read_state"]),
        },
    ),
    ManticaDescription(
        key="last_message",
        translation_key="last_message",
        icon="mdi:email",
        value_fn=lambda d: _short(d["messages"][0]["subject"], 250) if d["messages"] else None,
        attrs_fn=lambda d: _message(d["messages"][0]) if d["messages"] else {},
    ),
    ManticaDescription(
        key="last_grade",
        translation_key="last_grade",
        icon="mdi:school",
        value_fn=lambda d: d["latest_grade"]["value"] if d["latest_grade"] else None,
        attrs_fn=lambda d: _pick(d["latest_grade"], GRADE_KEYS) if d["latest_grade"] else {},
    ),
    ManticaDescription(
        key="recent_grades",
        translation_key="recent_grades",
        icon="mdi:format-list-numbered",
        value_fn=lambda d: len(d["recent_grades"]),
        attrs_fn=lambda d: {
            "days": 14,
            "grades": [_pick(g, GRADE_KEYS[:5], 100) for g in d["recent_grades"][:20]],
        },
    ),
    ManticaDescription(
        key="next_event",
        translation_key="next_event",
        icon="mdi:calendar-star",
        value_fn=lambda d: _short(d["upcoming"][0]["name"], 250) if d["upcoming"] else None,
        attrs_fn=lambda d: _event_attrs(d["upcoming"][0] if d["upcoming"] else None),
    ),
    ManticaDescription(
        key="next_test",
        translation_key="next_test",
        icon="mdi:pencil-box-outline",
        value_fn=lambda d: _short(d["next_test"]["name"], 250) if d["next_test"] else None,
        attrs_fn=lambda d: _event_attrs(d["next_test"]),
    ),
    ManticaDescription(
        key="lessons_today",
        translation_key="lessons_today",
        icon="mdi:timetable",
        section="timetable",
        value_fn=lambda d: len(_plan(d, 0)["lessons"]),
        attrs_fn=lambda d: _plan_attrs(_plan(d, 0)),
    ),
    ManticaDescription(
        key="lessons_tomorrow",
        translation_key="lessons_tomorrow",
        icon="mdi:calendar-arrow-right",
        section="timetable",
        value_fn=lambda d: len(_plan(d, 1)["lessons"]),
        attrs_fn=lambda d: _plan_attrs(_plan(d, 1)),
    ),
    ManticaDescription(
        key="week_plan",
        translation_key="week_plan",
        icon="mdi:calendar-week",
        section="timetable",
        value_fn=lambda d: extras.week_plans(
            d["timetable"], d["school_calendar"] or [], d["substitutions"] or [], _today()
        )[0]["date"],
        attrs_fn=lambda d: {
            "valid_from": d["timetable"]["valid_from"],
            "valid_to": d["timetable"]["valid_to"],
            "slots": d["timetable"]["slots"],
            "days": extras.week_plans(
                d["timetable"], d["school_calendar"] or [], d["substitutions"] or [], _today()
            ),
        },
    ),
    ManticaDescription(
        key="next_day_off",
        translation_key="next_day_off",
        icon="mdi:beach",
        device_class=SensorDeviceClass.DATE,
        section="school_calendar",
        value_fn=lambda d: (
            date.fromisoformat(n["start"]) if (n := extras.next_day_off(d["school_calendar"], _today())) else None
        ),
        attrs_fn=lambda d: {
            k: v
            for k, v in (extras.next_day_off(d["school_calendar"], _today()) or {}).items()
            if k in ("name", "end", "days_left")
        },
    ),
    ManticaDescription(
        key="substitutions",
        translation_key="substitutions",
        icon="mdi:account-switch",
        section="substitutions",
        value_fn=lambda d: len(_upcoming_subs(d)),
        attrs_fn=lambda d: {
            "upcoming": [_pick(s, SUB_KEYS, 100) for s in _upcoming_subs(d)[:20]],
            "latest": [_pick(s, SUB_KEYS, 100) for s in d["substitutions"][:5]],
        },
    ),
    ManticaDescription(
        key="remarks",
        translation_key="remarks",
        icon="mdi:comment-alert",
        section="remarks",
        value_fn=lambda d: len(d["remarks"]),
        attrs_fn=lambda d: {
            "positive": sum(1 for r in d["remarks"] if r["kind"] == "positive"),
            "negative": sum(1 for r in d["remarks"] if r["kind"] == "negative"),
            "remarks": [_pick(r, REMARK_KEYS, 300) for r in d["remarks"][:20]],
        },
    ),
    ManticaDescription(
        key="homework",
        translation_key="homework",
        icon="mdi:notebook-edit",
        section="homework",
        value_fn=lambda d: len(_open_homework(d)),
        attrs_fn=lambda d: {"homework": [_pick(h, HOMEWORK_KEYS, 500) for h in _open_homework(d)[:15]]},
    ),
    ManticaDescription(
        key="upcoming_events",
        translation_key="upcoming_events",
        icon="mdi:calendar-month",
        value_fn=lambda d: len(d["upcoming"]),
        attrs_fn=lambda d: {"events": [_pick(e, EVENT_KEYS, 150) for e in d["upcoming"][:15]]},
    ),
)


def _device(entry: ManticaConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Dziennik Mantica",
        manufacturer="mantica.net",
        entry_type=DeviceEntryType.SERVICE,
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ManticaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [ManticaSensor(coordinator, entry, d) for d in SENSORS]
    # One average sensor per subject present at setup time (reload to add new ones).
    entities += [
        ManticaAverageSensor(coordinator, entry, s["subject"])
        for s in coordinator.data["subjects"]
    ]
    async_add_entities(entities)


class ManticaSensor(CoordinatorEntity[ManticaCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: ManticaDescription

    def __init__(self, coordinator, entry, description: ManticaDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device(entry)

    @property
    def available(self) -> bool:
        section = self.entity_description.section
        return super().available and (section is None or self.coordinator.data.get(section) is not None)

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.entity_description.attrs_fn(self.coordinator.data)


class ManticaAverageSensor(CoordinatorEntity[ManticaCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:chart-line"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, subject: str) -> None:
        super().__init__(coordinator)
        self._subject = subject
        self._attr_name = f"Średnia - {subject}"
        self._attr_unique_id = f"{entry.entry_id}_avg_{subject.lower()}"
        self._attr_device_info = _device(entry)

    def _row(self) -> dict[str, Any] | None:
        return next(
            (s for s in self.coordinator.data["subjects"] if s["subject"] == self._subject),
            None,
        )

    @property
    def native_value(self) -> float | None:
        row = self._row()
        return row["average"] if row else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        row = self._row()
        if not row:
            return {}
        return {
            "final_grade": row["final_grade"],
            "predicted_grade": row["predicted_grade"],
            "grades": [_pick(g, ("value", "date", "description", "weight"), 100) for g in row["grades"]],
        }
