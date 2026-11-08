"""Timetable, substitutions, school calendar, remarks, homework, day plans."""
from datetime import date

from fixtures import HOMEWORK, HOMEWORK_EMPTY, REMARKS, SCHOOL_CAL, SUBSTITUTIONS, TIMETABLE, extras as x


def _raises(fn, *args):
    try:
        fn(*args)
    except x.LayoutError:
        return
    raise AssertionError("expected LayoutError")


def test_timetable():
    t = x.parse_timetable(TIMETABLE)
    assert (t["valid_from"], t["valid_to"]) == ("2026-09-01", "2027-06-25")
    assert [s["number"] for s in t["slots"]] == [1, 2, 8]
    mon = [l for l in t["lessons"] if l["weekday"] == 0]
    assert [(l["number"], l["start"], l["subject"]) for l in mon] == [
        (1, "08:00", "Edukacja wczesnoszkolna"), (2, "08:55", "Wychowanie fizyczne")
    ]
    assert not [l for l in t["lessons"] if l["weekday"] == 2 and l["number"] == 2]


def test_timetable_layout_error():
    _raises(x.parse_timetable, "<table><tr><th>Godzina</th><th>Pon</th></tr></table>")


def test_substitutions_keep_newest_correction():
    subs = x.parse_substitutions(SUBSTITUTIONS)
    assert [(s["date"], s["lesson"], s["substitute"]) for s in subs] == [
        ("2026-11-09", 2, "Wiśniewska Ola"), ("2026-10-09", 3, "Kowal Jan")
    ]
    assert subs[0]["absent_teacher"] == "Nowak Anna"


def test_school_calendar():
    cal = x.parse_school_calendar(SCHOOL_CAL)
    assert [(e["name"], e["start"], e["end"], e["day_off"]) for e in cal][1:3] == [
        ("Dzień Niepodległości", "2026-11-11", "2026-11-11", True),
        ("Dzień wolny od zajęć edukacyjnych", "2026-11-12", "2026-11-13", True),
    ]
    assert cal[0]["day_off"] is False and cal[3]["day_off"] is False
    nxt = x.next_day_off(cal, date(2026, 11, 8))
    assert (nxt["start"], nxt["days_left"]) == ("2026-11-11", 3)


def test_remarks():
    r = x.parse_remarks(REMARKS)
    assert [(i["kind"], i["date"], i["teacher"], i["text"]) for i in r] == [
        ("positive", "2026-10-30", "Anna Nowak", "Pochwała za przebranie."),
        ("negative", "2026-10-05", "Jan Kowal", "Rozmowy na lekcji."),
    ]
    assert x.parse_remarks(REMARKS.split("<font")[0]) == []
    _raises(x.parse_remarks, "<p>inna strona</p>")


def test_homework():
    assert x.parse_homework(HOMEWORK_EMPTY) == []
    (h,) = x.parse_homework(HOMEWORK)
    assert (h["subject"], h["topic"], h["assigned"], h["due"], h["content"]) == (
        "Język angielski", "Unit 2", "2026-11-06", "2026-11-10", "Ćw. 3 i 4, str. 21"
    )


def test_day_plans():
    t = x.parse_timetable(TIMETABLE)
    cal = x.parse_school_calendar(SCHOOL_CAL)
    subs = x.parse_substitutions(SUBSTITUTIONS)
    mon = x.day_plan(t, cal, subs, date(2026, 11, 9))
    assert mon["day_off"] is None and [l["number"] for l in mon["lessons"]] == [1, 2]
    assert mon["lessons"][1]["substitute"] == "Wiśniewska Ola"
    assert "substitute" not in mon["lessons"][0]
    assert x.day_plan(t, cal, subs, date(2026, 11, 11))["day_off"] == "Dzień Niepodległości"
    assert x.day_plan(t, cal, subs, date(2026, 11, 8))["day_off"] == "weekend"
    assert x.day_plan(t, cal, subs, date(2027, 7, 5))["lessons"] == []  # after the plan ends
    week = x.week_plans(t, cal, subs, date(2026, 11, 8))  # Sunday -> next week
    assert [d["date"] for d in week] == ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"]
    assert [bool(d["day_off"]) for d in week] == [False, False, True, True, True]
