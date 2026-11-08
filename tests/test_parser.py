"""Parser on HTML mirroring the live portal."""
from datetime import date

from fixtures import CAL, GRADES, INBOX, parser as p


def test_grades():
    subj = p.parse_grades(GRADES)
    assert [s["subject"] for s in subj] == ["Język angielski", "Edukacja społeczna", "Wychowanie fizyczne"], subj
    en = subj[0]
    assert [g["value"] for g in en["grades"]] == ["4", "6"]  # commented duplicates ignored
    assert en["average"] == 5.0 and en["final_grade"] is None and en["predicted_grade"] is None
    assert en["grades"][1]["weight"] == "2" and en["grades"][1]["date"] == "2026-09-29"
    assert en["grades"][0]["teacher"] == "Ewa Zielińska"
    assert en["grades"][0]["description"] == "Praca na lekcji - ulubiony sport"
    assert subj[1]["grades"] == [] and subj[1]["average"] is None
    pe = subj[2]
    assert pe["average"] == 5.0 and pe["final_grade"] == "Bardzo dobry"
    assert len({g["id"] for g in pe["grades"]}) == 2  # same subject/date/value -> distinct ids


def test_messages():
    msgs = p.parse_messages(INBOX)
    msgs[0].pop("url")  # checked in test_message_link_kept
    assert msgs[0] == {"id": "30257", "subject": "informacja", "sender": "Sekretariat Testowa",
                       "received": "2026-10-29 11:58:41", "has_attachment": True, "unread": False}, msgs[0]
    assert msgs[1]["unread"] is True and msgs[1]["has_attachment"] is False
    assert msgs[1]["subject"] == "Zebranie z rodzicami."


def test_calendar():
    ev = p.parse_calendar(CAL, 2026, 11)
    assert [(e["date"], e["name"]) for e in ev] == [
        ("2026-11-10", "piosenka j. angielski"),
        ("2026-11-17", "Backzeit- piosenka dla chętnych."),
        ("2026-11-17", "Sprawdzian z angielskiego"),
    ], ev
    assert ev[0]["teacher"] == "Ewa Zielińska"
    assert [e["is_test"] for e in ev] == [False, False, True]
    assert ev[2]["color"] == "FF0000"


def test_summary():
    subj, msgs, ev = p.parse_grades(GRADES), p.parse_messages(INBOX), p.parse_calendar(CAL, 2026, 11)
    s = p.build_summary(subj, msgs, ev + ev[:1], date(2026, 11, 8))
    assert [e["days_left"] for e in s["upcoming"]] == [2, 9, 9]
    assert s["next_test"]["name"] == "Sprawdzian z angielskiego"
    assert s["latest_grade"]["date"] == "2026-10-22"
    assert len(s["unread"]) == 1 and s["unknown_read_state"] == []


def test_markers():
    assert p.classify_test("Test z matematyki") and not p.classify_test("kontekst piosenka")


def test_message_link_kept():
    msgs = {m["id"]: m for m in p.parse_messages(INBOX)}
    assert msgs["30257"]["url"] == (
        "poczta_czytaj.php?id=30257&typ=n&imie=Sekretariat&nazwisko=Testowa"
    )
    assert msgs["30200"]["url"] == "poczta_czytaj.php?id=30200&typ=n"


MESSAGE_PAGE = """<html><body><script>var x = 1;</script>
<table><tr><td><b>Temat:</b> Wyjście do MOK-u</td></tr>
<tr><td><b>Od:</b> Anna Nowak</td></tr>
<tr><td><b>Data:</b> 2026-11-06 12:00</td></tr>
<tr><td><p>Szanowni Państwo,</p><p>w&nbsp;piątek klasa 3A idzie do MOK-u.<br>Zbiórka o 8:00.</p></td></tr>
</table><form><input type="button" value="Odpowiedz"></form></body></html>"""


def test_message_body():
    assert p.parse_message_body(MESSAGE_PAGE) == (
        "Szanowni Państwo,\nw piątek klasa 3A idzie do MOK-u.\nZbiórka o 8:00."
    )


def test_empty_message_page_is_layout_error():
    try:
        p.parse_message_body("<html><body><script>x</script></body></html>")
    except p.LayoutError:
        return
    raise AssertionError("expected LayoutError")
