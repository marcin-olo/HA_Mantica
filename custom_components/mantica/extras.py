"""Parsers for the timetable, substitutions, school-year calendar, remarks
and homework pages, plus the day plans built from them (no HA imports).

Structures observed on a live parent account (Nov 2026):
- plan_lekcji_uczen.php: one table, header Lekcja / Poniedziałek..Piątek,
  first cell "<b>(1)</b>08:00-08:45", other cells the subject name.
- p_zastepstwa_new_u.php: Lp / Data zastępstwa / Przedmiot / Lekcja /
  Zastępstwo za / Zastępujący / Data dodania / Klasa/grupa (rows without
  </tr>; a corrected substitution is listed again with a newer Data dodania).
- kalendarz_info.php: Lp / Wydarzenie / Data ("YYYY-MM-DD - YYYY-MM-DD") /
  Wolne (TAK/NIE).
- uwagi_uczen.php?semestr=N: <font class="vtip" title="Uwaga pozytywna.<br>
  Wystawiona: <b>date time</b> przez <b>teacher</b>"><b>text</b></font>.
- zadania_domowe_info.php: Lp / Przedmiot / Nauczyciel / Temat /
  Data zadania / Termin wykonania / Treść (no rows seen yet).
"""
from __future__ import annotations

import html as htmllib
import re
from datetime import date, timedelta
from typing import Any

from .parser import _ATTRS, LayoutError, _clean, _find_table, _tables, _text, _title_of

WEEKDAYS = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")
_DATE = r"(\d{4}-\d{2}-\d{2})"


def _has_header(html: str, title: str) -> bool:
    return bool(re.search(r'class="table_header"[^>]*>\s*<td[^>]*>\s*' + title, html, re.I))


# --------------------------------------------------------------------------
# Timetable
# --------------------------------------------------------------------------
_SLOT_RE = re.compile(r"\((\d+)\)\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})")


def parse_timetable(html: str) -> dict[str, Any]:
    """{valid_from, valid_to, slots: [{number, start, end}], lessons: [{weekday, number, start, end, subject}]}"""
    html = _clean(html)
    for rows in _tables(html):
        if not rows:
            continue
        header = [_text(c).lower() for _, c in rows[0]]
        if not header or "lekcja" not in header[0]:
            continue
        days = [WEEKDAYS.index(h) if h in WEEKDAYS else None for h in header[1:]]
        if None in days or not days:
            raise LayoutError(f"timetable day columns not recognised: {header[1:]}")
        slots, lessons = [], []
        for row in rows[1:]:
            if len(row) != len(header):
                continue
            m = _SLOT_RE.search(_text(row[0][1]))
            if not m:
                continue  # e.g. "(0) ?-?" - lesson 0 without hours
            number, start, end = int(m.group(1)), m.group(2).zfill(5), m.group(3).zfill(5)
            slots.append({"number": number, "start": start, "end": end})
            for wd, (_, cell) in zip(days, row[1:]):
                subject = _text(cell)
                if subject:
                    lessons.append(
                        {"weekday": wd, "number": number, "start": start, "end": end, "subject": subject}
                    )
        if not slots:
            raise LayoutError("timetable has no lesson rows with hours")
        valid = re.search(r"obowiązuje od:\s*(?:<[^>]+>\s*)*" + _DATE + r".*?do:\s*(?:<[^>]+>\s*)*" + _DATE, html, re.S | re.I)
        return {
            "valid_from": valid.group(1) if valid else None,
            "valid_to": valid.group(2) if valid else None,
            "slots": slots,
            "lessons": lessons,
        }
    raise LayoutError("timetable table (Lekcja / Poniedziałek...) not found")


# --------------------------------------------------------------------------
# Substitutions
# --------------------------------------------------------------------------
SUBSTITUTION_COLUMNS: dict[str, tuple[str, ...]] = {
    "date": ("data zastępstwa", "data zastepstwa"),
    "added": ("data dodania",),
    "subject": ("przedmiot",),
    "lesson": ("lekcja",),
    "absent": ("zastępstwo za", "zastepstwo za"),
    "substitute": ("zastępujący", "zastepujacy"),
    "group": ("klasa",),
}


def parse_substitutions(html: str) -> list[dict[str, Any]]:
    """Newest entry per (date, lesson), newest dates first."""
    html = _clean(html)
    found = _find_table(html, SUBSTITUTION_COLUMNS, ("date", "subject", "lesson", "substitute"))
    if not found:
        if _has_header(html, "Lista zastępstw"):
            return []  # page without any substitutions (table not seen yet)
        raise LayoutError("substitutions table (Data zastępstwa / Lekcja) not found")
    rows, cols = found
    width = len(rows[0])
    best: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows[1:]:
        if len(row) != width:
            continue
        get = lambda k: _text(row[cols[k]][1]) if k in cols else ""  # noqa: E731
        day, lesson = get("date"), get("lesson")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or not lesson.isdigit():
            raise LayoutError(f"substitution row not recognised: '{day}' / '{lesson}'")
        item = {
            "date": day,
            "lesson": int(lesson),
            "subject": get("subject"),
            "absent_teacher": get("absent"),
            "substitute": get("substitute"),
            "added": get("added"),
            "group": get("group"),
        }
        item["id"] = f"{day}|{lesson}|{item['added']}"
        key = (day, int(lesson))
        if key not in best or item["added"] > best[key]["added"]:
            best[key] = item
    return sorted(best.values(), key=lambda s: (s["date"], s["lesson"]), reverse=True)


# --------------------------------------------------------------------------
# School-year calendar (days off)
# --------------------------------------------------------------------------
SCHOOL_CAL_COLUMNS: dict[str, tuple[str, ...]] = {
    "name": ("wydarzenie",),
    "dates": ("data",),
    "off": ("wolne",),
}


def parse_school_calendar(html: str) -> list[dict[str, Any]]:
    found = _find_table(_clean(html), SCHOOL_CAL_COLUMNS, ("name", "dates", "off"))
    if not found:
        raise LayoutError("school calendar table (Wydarzenie / Data / Wolne) not found")
    rows, cols = found
    width = len(rows[0])
    out = []
    for row in rows[1:]:
        if len(row) != width:
            continue
        name = _text(row[cols["name"]][1])
        dates = re.findall(_DATE, _text(row[cols["dates"]][1]))
        if not name:
            continue
        if not dates:
            raise LayoutError(f"school calendar entry '{name[:30]}' has no dates")
        off = _text(row[cols["off"]][1]).upper()
        out.append(
            {"name": name, "start": dates[0], "end": dates[-1], "day_off": off.startswith("TAK")}
        )
    return out


# --------------------------------------------------------------------------
# Remarks (uwagi)
# --------------------------------------------------------------------------
_FONT_RE = re.compile(r"<font\b(" + _ATTRS + r")>(.*?)</font>", re.S | re.I)


def parse_remarks(html: str) -> list[dict[str, Any]]:
    html = _clean(html)
    if not _has_header(html, "Uwagi"):
        raise LayoutError("remarks page header (Uwagi) not found")
    out = []
    for attrs, inner in _FONT_RE.findall(html):
        title = _title_of(attrs)
        if not title or "uwaga" not in title.lower():
            continue
        t = htmllib.unescape(title)
        kind = re.match(r"\s*Uwaga\s+([a-ząćęłńóśźż]+)", t, re.I)
        kind_word = kind.group(1).lower() if kind else ""
        when = re.search(r"(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}(?::\d{2})?))?", t)
        who = re.search(r"przez\s*(?:<[^>]+>\s*)*([^<]+)", t, re.I)
        text = _text(inner)
        if not when or not text:
            raise LayoutError(f"remark not recognised: '{_text(t)[:50]}'")
        out.append(
            {
                "text": text,
                "kind": "positive" if kind_word.startswith("pozytywn")
                else "negative" if kind_word.startswith("negatywn")
                else kind_word or "neutral",
                "date": when.group(1),
                "time": when.group(2) or "",
                "teacher": who.group(1).strip() if who else "",
            }
        )
        out[-1]["id"] = f"{when.group(1)} {when.group(2) or ''}|{out[-1]['teacher']}|{text[:30]}"
    out.sort(key=lambda r: (r["date"], r["time"]), reverse=True)
    return out


# --------------------------------------------------------------------------
# Homework
# --------------------------------------------------------------------------
HOMEWORK_COLUMNS: dict[str, tuple[str, ...]] = {
    "subject": ("przedmiot",),
    "teacher": ("nauczyciel",),
    "topic": ("temat",),
    "assigned": ("data zadania",),
    "due": ("termin",),
    "content": ("treść", "tresc"),
}


def parse_homework(html: str) -> list[dict[str, Any]]:
    found = _find_table(_clean(html), HOMEWORK_COLUMNS, ("subject", "due"))
    if not found:
        raise LayoutError("homework table (Przedmiot / Termin wykonania) not found")
    rows, cols = found
    width = len(rows[0])
    out = []
    for row in rows[1:]:
        if len(row) != width:
            continue  # legend row (colspan)
        get = lambda k: _text(row[cols[k]][1]) if k in cols else ""  # noqa: E731
        subject = get("subject")
        due = re.search(_DATE, get("due"))
        if not subject:
            continue
        if not due:
            raise LayoutError(f"homework for '{subject[:30]}' has no due date")
        assigned = re.search(_DATE, get("assigned"))
        item = {
            "subject": subject,
            "teacher": get("teacher"),
            "topic": get("topic"),
            "assigned": assigned.group(1) if assigned else "",
            "due": due.group(1),
            "content": get("content"),
        }
        item["id"] = f"{subject}|{item['assigned']}|{item['due']}|{item['topic'][:30]}"
        out.append(item)
    out.sort(key=lambda h: h["due"])
    return out


# --------------------------------------------------------------------------
# Day plans
# --------------------------------------------------------------------------
def day_off_on(school_calendar: list[dict[str, Any]], day: str) -> str | None:
    for e in school_calendar:
        if e["day_off"] and e["start"] <= day <= e["end"]:
            return e["name"]
    return None


def day_plan(
    timetable: dict[str, Any] | None,
    school_calendar: list[dict[str, Any]],
    substitutions: list[dict[str, Any]],
    day: date,
) -> dict[str, Any]:
    """Lessons of one day, with days off and substitutions applied."""
    iso = day.isoformat()
    plan: dict[str, Any] = {"date": iso, "weekday": WEEKDAYS[day.weekday()], "day_off": None, "lessons": []}
    if day.weekday() >= 5:
        plan["day_off"] = "weekend"
        return plan
    off = day_off_on(school_calendar, iso)
    if off:
        plan["day_off"] = off
        return plan
    if not timetable:
        return plan
    if (timetable.get("valid_from") and iso < timetable["valid_from"]) or (
        timetable.get("valid_to") and iso > timetable["valid_to"]
    ):
        return plan
    subs = {s["lesson"]: s for s in substitutions if s["date"] == iso}
    for lesson in timetable["lessons"]:
        if lesson["weekday"] != day.weekday():
            continue
        item = {k: lesson[k] for k in ("number", "start", "end", "subject")}
        sub = subs.get(lesson["number"])
        if sub:
            item["substitute"] = sub["substitute"]
            item["absent_teacher"] = sub["absent_teacher"]
        plan["lessons"].append(item)
    plan["lessons"].sort(key=lambda lesson: lesson["number"])
    return plan


def week_plans(
    timetable: dict[str, Any] | None,
    school_calendar: list[dict[str, Any]],
    substitutions: list[dict[str, Any]],
    today: date,
) -> list[dict[str, Any]]:
    """Mon-Fri of this week, or of next week from Saturday on."""
    monday = today - timedelta(days=today.weekday())
    if today.weekday() >= 5:
        monday += timedelta(days=7)
    return [day_plan(timetable, school_calendar, substitutions, monday + timedelta(days=i)) for i in range(5)]


def next_day_off(school_calendar: list[dict[str, Any]], today: date) -> dict[str, Any] | None:
    iso = today.isoformat()
    future = sorted(
        (e for e in school_calendar if e["day_off"] and e["end"] >= iso), key=lambda e: e["start"]
    )
    if not future:
        return None
    e = future[0]
    days_left = max(0, (date.fromisoformat(e["start"]) - today).days)
    return {**e, "days_left": days_left}
