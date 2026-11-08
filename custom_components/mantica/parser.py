"""Pure-Python parsers for the mantica.net parent portal (no Home Assistant imports).

The portal has no API, so everything here is based on the HTML structure
observed on a live parent account (Nov 2026).

Design rule: *fail loud*. When a page is fetched while logged in but does not
look the way we expect, raise LayoutError instead of returning partial or
empty data. The coordinator turns that into "unavailable" entities and a
Repairs issue, instead of silently showing "no grades / nothing planned".
"""
from __future__ import annotations

import html as htmllib
import logging
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from typing import Any


_LOGGER = logging.getLogger(__name__)


class LayoutError(Exception):
    """Logged-in page whose structure the parser does not recognise."""


_SCRIPT_RE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.S | re.I)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_WS_RE = re.compile(r"\s+")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_IMG_RE = re.compile(r"<img[^>]*>", re.I)


def _clean(html: str) -> str:
    """Drop scripts/styles and HTML comments (the grades page keeps
    commented-out duplicates of every grade)."""
    return _COMMENT_RE.sub("", _SCRIPT_RE.sub("", html))


def _text(fragment: str) -> str:
    fragment = _BR_RE.sub(" ", fragment)
    fragment = _TAG_RE.sub("", fragment)
    return _WS_RE.sub(" ", htmllib.unescape(fragment)).strip()


def _num(value: str) -> float | None:
    value = value.strip().replace(",", ".")
    return float(value) if re.fullmatch(r"\d+(\.\d+)?", value) else None


# --------------------------------------------------------------------------
# Session detection
# --------------------------------------------------------------------------
_LOGGED_IN_MARKERS = ("logout=1", "Zalogowany jako")
_PASSWORD_INPUT_RE = re.compile(r"<input[^>]*type=[\"']?password", re.I)


def is_logged_in(html: str) -> bool:
    """Two independent markers, so one renamed link does not break it."""
    return any(m in html for m in _LOGGED_IN_MARKERS)


def is_login_page(html: str) -> bool:
    """A page with a password field and no logged-in markers."""
    return not is_logged_in(html) and bool(_PASSWORD_INPUT_RE.search(html))


# --------------------------------------------------------------------------
# Generic nesting-aware table reader
# --------------------------------------------------------------------------
# Attribute values may contain raw "<b>...</b>" (the live grade tooltips do),
# so a tag ends at the first ">" outside quotes, not at the first ">".
_ATTRS = r"""(?:[^>"']|"[^"]*"|'[^']*')*"""
_TABLE_TOKEN_RE = re.compile(r"<(/?)(table|tr|td|th)\b" + _ATTRS + ">", re.I)


def _tables(html: str) -> list[list[list[tuple[str, str]]]]:
    """Every <table> as rows of (tag, inner_html) cells.

    Only a table's own rows/cells are listed; nested tables stay inside the
    cell's HTML. Unclosed <td>/<tr> are closed implicitly, like browsers do.
    """
    out: list[list[list[tuple[str, str]]]] = []
    stack: list[dict[str, Any]] = []

    def close_cell(t: dict[str, Any], end: int) -> None:
        if t["cell"] is not None:
            tag, start = t["cell"]
            if t["row"] is None:
                t["row"] = []
            t["row"].append((tag, html[start:end]))
            t["cell"] = None

    def close_row(t: dict[str, Any]) -> None:
        if t["row"]:
            t["rows"].append(t["row"])
        t["row"] = None

    for m in _TABLE_TOKEN_RE.finditer(html):
        closing, tag = m.group(1) == "/", m.group(2).lower()
        if tag == "table":
            if not closing:
                stack.append({"rows": [], "row": None, "cell": None})
            elif stack:
                t = stack.pop()
                close_cell(t, m.start())
                close_row(t)
                out.append(t["rows"])
            continue
        if not stack:
            continue
        t = stack[-1]
        if tag == "tr":
            close_cell(t, m.start())
            close_row(t)
            if not closing:
                t["row"] = []
        else:  # td / th
            close_cell(t, m.start())
            if not closing:
                t["cell"] = (tag, m.end())
    return out


def _map_columns(
    header: list[str], spec: dict[str, tuple[str, ...]]
) -> dict[str, int]:
    """Header texts -> {key: column index}. Spec order matters: the first
    key whose pattern appears in a header cell wins that cell."""
    cols: dict[str, int] = {}
    for idx, h in enumerate(header):
        for key, patterns in spec.items():
            if key not in cols and any(p in h for p in patterns):
                cols[key] = idx
                break
    return cols


def _find_table(
    html: str, spec: dict[str, tuple[str, ...]], required: tuple[str, ...]
) -> tuple[list[list[tuple[str, str]]], dict[str, int]] | None:
    for rows in _tables(html):
        if not rows:
            continue
        header = [_text(c).lower() for _, c in rows[0]]
        cols = _map_columns(header, spec)
        if all(k in cols for k in required):
            return rows, cols
    return None


# --------------------------------------------------------------------------
# Grades: oceny_uczen.php?semestr=N
# --------------------------------------------------------------------------
GRADE_COLUMNS: dict[str, tuple[str, ...]] = {
    "subject": ("przedmiot",),
    "grades": ("oceny bieżące", "oceny biezace", "bieżące"),
    "predicted": ("przewidywan", "proponowan"),
    "average": ("średnia", "srednia"),
    "final": ("semestraln", "roczn", "końcow", "koncow"),
}
_SPAN_RE = re.compile(r"<span\b(" + _ATTRS + r")>(.*?)</span>", re.S | re.I)
# "Oceny bez opisu": the tooltip sits on a wrapping <label>, the grade
# spans inside it have no title of their own.
_LABEL_RE = re.compile(r"<label\b(" + _ATTRS + r")>(.*?)</label>", re.S | re.I)
_TITLE_RE = re.compile(r"""\btitle\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
_B = r"\s*(?:</?b>\s*)*"  # optional <b>/</b> around tooltip values


def _title_of(attrs: str) -> str | None:
    m = _TITLE_RE.search(attrs)
    return (m.group(1) if m.group(1) is not None else m.group(2)) if m else None


def _grade_items(gcell: str) -> tuple[list[tuple[str | None, str]], str]:
    """[(tooltip, value_html), ...] for every grade in the cell, plus the
    cell HTML with all recognised grades removed (to spot leftovers)."""
    items: list[tuple[str | None, str]] = []

    def label(m: re.Match[str]) -> str:
        own = _title_of(m.group(1))
        inner = m.group(2)
        spans = _SPAN_RE.findall(inner)
        for attrs, value in spans:
            items.append((_title_of(attrs) or own, value))
        return " " + _SPAN_RE.sub(" ", inner) + " "

    rest = _LABEL_RE.sub(label, gcell)
    for attrs, value in _SPAN_RE.findall(rest):
        items.append((_title_of(attrs), value))
    return items, _SPAN_RE.sub(" ", rest)


def _grade_from_title(subject: str, value: str, title: str) -> dict[str, Any] | None:
    t = htmllib.unescape(title)
    dates = _DATE_RE.findall(t)
    if not dates:
        return None
    desc = re.search(r"Opis[^:<]*:" + _B + r"(.*?)(?:<br\s*/?>|$)", t, re.S | re.I)
    weight = re.search(r"Wag[^:<]*:" + _B + r"([^<]*)", t, re.I)
    issued = re.search(
        r"Wystawi[^:<]*:" + _B + r"([^<]*?),\s*(\d{4}-\d{2}-\d{2})", t, re.I
    )
    return {
        "subject": subject,
        "value": value,
        # Issue date, not a later "Zmieniał/a" date, so editing a grade
        # does not change its id.
        "date": issued.group(2) if issued else dates[0],
        "description": _text(desc.group(1)) if desc else "",
        "weight": weight.group(1).strip() if weight else "",
        "teacher": issued.group(1).strip() if issued else "",
    }


def _final_text(cell: str) -> str | None:
    return _text(cell).strip("-  ") or None


def parse_grades(html: str) -> list[dict[str, Any]]:
    """[{subject, average, final_grade, predicted_grade, grades:[...]}, ...]"""
    found = _find_table(_clean(html), GRADE_COLUMNS, ("subject", "grades"))
    if not found:
        raise LayoutError("grades table (Przedmiot / Oceny bieżące) not found")
    rows, cols = found
    width = len(rows[0])
    subjects: list[dict[str, Any]] = []
    problems: list[str] = []
    logged_raw = False

    for row in rows[1:]:
        if len(row) != width:  # e.g. colspan rows like "Zachowanie"
            continue

        def cell(key: str) -> str:
            return row[cols[key]][1] if key in cols else ""

        name = _text(cell("subject")).rstrip(": ").strip()
        if not name:
            continue
        gcell = cell("grades")
        problems_before = len(problems)
        grades: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        items, rest = _grade_items(gcell)
        for title, inner in items:
            value = _text(inner)
            g = _grade_from_title(name, value, title) if title else None
            if g is None:
                problems.append(f"{name}: grade '{value}' without date/details")
                continue
            # ID deliberately ignores description/teacher wording, so a
            # relabelled tooltip does not make every grade look "new".
            base = f"{name}|{g['date']}|{value}"
            counts[base] = counts.get(base, 0) + 1
            g["id"] = f"{base}|{counts[base]}"
            grades.append(g)
        leftover = _text(rest)
        if re.search(r"[0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]", leftover):
            problems.append(f"{name}: unparsed grade text '{leftover[:40]}'")
        if len(problems) > problems_before and not logged_raw:
            # Raw HTML of the first cell that failed, so the layout can be
            # fixed from the HA log without access to the portal.
            logged_raw = True
            _LOGGER.warning(
                "Unrecognised grades cell for %s: %r",
                name,
                _WS_RE.sub(" ", gcell).strip()[:10000],
            )
        subjects.append(
            {
                "subject": name,
                "average": _num(_text(cell("average"))) if "average" in cols else None,
                "final_grade": _final_text(cell("final")) if "final" in cols else None,
                "predicted_grade": (
                    _final_text(cell("predicted")) if "predicted" in cols else None
                ),
                "grades": grades,
            }
        )
    if problems:
        raise LayoutError("; ".join(problems[:3]))
    if not subjects:
        raise LayoutError("grades table has no subject rows")
    return subjects


# --------------------------------------------------------------------------
# Inbox: poczta_new.php?message=inbox  (first page = 10 newest)
# --------------------------------------------------------------------------
MESSAGE_COLUMNS: dict[str, tuple[str, ...]] = {
    "subject": ("temat",),
    "sender": ("nadawca",),
    "received": ("data",),
}
_READ_MARKERS = ("mail_open", "przeczytana")
_UNREAD_MARKERS = ("nieprzeczytan", "nowa wiadomo", "unread", "mail_new", "mail_close", "images/mail.gif")


def _read_state(cell_html: str) -> bool | None:
    """True = unread, False = read, None = icon not recognised."""
    img = _IMG_RE.search(cell_html)
    if not img:
        return None
    tag = img.group(0).lower()
    if any(m in tag for m in _UNREAD_MARKERS):  # checked first: contains "przeczytana"
        return True
    if any(m in tag for m in _READ_MARKERS):
        return False
    return None


_MSG_LINK_RE = re.compile(r"poczta_czytaj\.php\?id=\d+[^'\"\s<>]*")
_BLOCK_END_RE = re.compile(r"</(p|div|tr|li|h\d|table)\s*>|<br\s*/?>", re.I)
_MSG_HEADER_RE = re.compile(
    r"^(temat|od|nadawca|do|odbiorca|odbiorcy|data|data wysłania|wysłano)\s*:",
    re.I,
)


_MSG_BODY_OPEN_RE = re.compile(r"<div\b[^>]*\bclass=[\"']?[^\"'>]*\btresc_listy\b[^>]*>", re.I)
_DIV_TAG_RE = re.compile(r"<(/?)div\b[^>]*>", re.I)


def _message_div(html: str) -> str | None:
    """Inner HTML of <div class="tresc_listy"> (the message text), or None."""
    start = _MSG_BODY_OPEN_RE.search(html)
    if not start:
        return None
    depth = 1
    for tag in _DIV_TAG_RE.finditer(html, start.end()):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return html[start.end():tag.start()]
    return html[start.end():]


def _html_to_text(html: str) -> str:
    """Readable text: line breaks kept, header lines (Temat:, Od:, ...) dropped."""
    html = re.sub(r"<(form|select|button|input|textarea)\b.*?(?:</\1\s*>|>)", " ", html, flags=re.S | re.I)
    html = _BLOCK_END_RE.sub("\n", html)
    text = htmllib.unescape(_TAG_RE.sub(" ", html))
    lines: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"[ \t\u00a0\ufeff]+", " ", line).strip()
        if not line or _MSG_HEADER_RE.match(line):
            if lines and lines[-1]:
                lines.append("")
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def parse_message_body(html: str) -> str:
    """Readable text of a poczta_czytaj.php page/fragment.

    The portal returns a fragment with the subject in tr.table_header, a
    "Odpowiedź" link and the text in <div class="tresc_listy"> (empty when
    the message has no text, which is valid). Without that div, fall back
    to generic text extraction of the whole page.
    """
    html = _clean(html)
    inner = _message_div(html)
    if inner is not None:
        return _html_to_text(inner)
    body = re.search(r"<body\b[^>]*>(.*)</body>", html, re.S | re.I)
    out = _html_to_text(body.group(1) if body else html)
    if not out:
        raise LayoutError("message page has no text")
    return out


def parse_messages(html: str) -> list[dict[str, Any]]:
    found = _find_table(_clean(html), MESSAGE_COLUMNS, ("subject", "sender", "received"))
    if not found:
        raise LayoutError("inbox table (Temat / Nadawca / Data) not found")
    rows, cols = found
    width = len(rows[0])
    attach_col = next(
        (i for i, (_, c) in enumerate(rows[0]) if "spinacz" in c.lower() or "zał" in c.lower()),
        None,
    )
    out, problems = [], []
    for row in rows[1:]:
        if len(row) != width:
            continue
        raw = "".join(c for _, c in row)
        mid = re.search(r"poczta_czytaj\.php\?id=(\d+)", raw) or re.search(
            r"value=\"(\d+)\"", raw
        )
        subject_html = row[cols["subject"]][1]
        if not mid:
            if _text(raw):
                problems.append(f"message row without id: '{_text(raw)[:40]}'")
            continue
        # Full link as the portal opens it (typ=n, imie=..., ...).
        link = _MSG_LINK_RE.search(raw)
        out.append(
            {
                "id": mid.group(1),
                "url": htmllib.unescape(link.group(0))
                if link
                else f"poczta_czytaj.php?id={mid.group(1)}",
                "subject": _text(subject_html) or "(bez tematu)",
                "sender": _text(row[cols["sender"]][1]),
                "received": _text(row[cols["received"]][1]),
                "has_attachment": attach_col is not None
                and "<img" in row[attach_col][1].lower(),
                "unread": _read_state(subject_html),
            }
        )
    if problems:
        raise LayoutError("; ".join(problems[:3]))
    return out


# --------------------------------------------------------------------------
# Calendar: terminarz_uczen.php?month=M&year=Y&klasa=
# --------------------------------------------------------------------------
PL_MONTHS = (
    "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
    "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
)
TEST_KEYWORDS = (
    "sprawdzian", "kartkówk", "klasówk", "praca klasowa", "egzamin", "dyktando", "quiz",
)
_TEST_WORD_RE = re.compile(r"\btest\b", re.I)


def classify_test(name: str, description: str = "") -> bool:
    blob = f"{name} {description}".lower()
    return any(k in blob for k in TEST_KEYWORDS) or bool(_TEST_WORD_RE.search(blob))


class _CalParser(HTMLParser):
    def __init__(self, year: int, month: int) -> None:
        super().__init__(convert_charrefs=True)
        self.year, self.month = year, month
        self.found = False
        self.header: list[str] = []
        self.events: list[dict[str, Any]] = []
        self.problems: list[str] = []
        self._in_cal = False
        self._depth = 0
        self._in_th = False
        self._day: int | None = None
        self._color = ""
        self._ev_title: str | None = None
        self._ev_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag == "table":
            if self._in_cal:
                self._depth += 1
                if a.get("bgcolor"):
                    self._color = a["bgcolor"]
            elif "terminarz" in cls:
                self._in_cal, self._depth, self.found = True, 1, True
            return
        if not self._in_cal:
            return
        if tag == "th":
            self._in_th = True
        elif tag == "td":
            if self._depth == 1:  # a new day cell of the month grid
                self._day, self._color = None, ""
            if "vtip" in cls:
                self._ev_title, self._ev_text = a.get("title") or "", []

    def handle_endtag(self, tag):
        if not self._in_cal:
            return
        if tag == "table":
            self._depth -= 1
            if self._depth == 0:
                self._in_cal = False
        elif tag == "th":
            self._in_th = False
        elif tag == "td" and self._ev_title is not None:
            name = _WS_RE.sub(" ", "".join(self._ev_text)).strip()
            if name:
                if self._day is None:
                    self.problems.append(f"event '{name}' has no day number")
                else:
                    ev = self._build(name, self._ev_title)
                    if ev:
                        self.events.append(ev)
            self._ev_title = None

    def handle_data(self, data):
        if not self._in_cal:
            return
        if self._in_th:
            self.header.append(data)
        elif self._ev_title is not None:
            self._ev_text.append(data)
        else:
            s = data.strip()
            if s.isdigit() and 1 <= int(s) <= 31:
                self._day = int(s)  # no reliance on the <br> after it

    def _build(self, name: str, title: str) -> dict[str, Any] | None:
        try:
            d = date(self.year, self.month, self._day or 0)
        except ValueError:
            self.problems.append(f"event '{name}': invalid day {self._day}")
            return None
        teacher = re.search(r"Nauczyciel[^:<]*:\s*(?:</b>)?\s*([^<]*)", title, re.I)
        desc = re.search(r"Opis[^:<]*:\s*(?:</b>)?\s*(.*?)(?:<br\s*/?>|$)", title, re.S | re.I)
        added = re.search(r"Data dodania[^:<]*:\s*(?:</b>)?\s*([\d-]+)", title, re.I)
        visible = re.search(r"Widoczne[^:<]*:\s*(?:</b>)?\s*([^<]*)", title, re.I)
        description = _text(desc.group(1)) if desc else ""
        return {
            "name": name,
            "date": d.isoformat(),
            "teacher": teacher.group(1).strip() if teacher else "",
            "description": description,
            "added": added.group(1) if added else "",
            "visible_for": visible.group(1).strip() if visible else "",
            "color": self._color,
            "is_test": classify_test(name, description),
        }


def parse_calendar(html: str, year: int, month: int) -> list[dict[str, Any]]:
    p = _CalParser(year, month)
    p.feed(_clean(html))
    p.close()
    if not p.found:
        raise LayoutError("calendar table (class 'terminarz') not found")
    header = _WS_RE.sub(" ", " ".join(p.header)).lower()
    m = re.search(r"([a-ząćęłńóśźż]+)\s+(\d{4})", header)
    if not m or m.group(1) not in PL_MONTHS:
        raise LayoutError(f"calendar month header not recognised: '{header[:60]}'")
    shown = (PL_MONTHS.index(m.group(1)) + 1, int(m.group(2)))
    if shown != (month, year):
        raise LayoutError(
            f"asked for {month:02d}/{year}, page shows {m.group(1)} {m.group(2)}"
        )
    days = [e["date"] for e in p.events]
    if days != sorted(days):
        p.problems.append("event days are out of order")
    if p.problems:
        raise LayoutError("; ".join(p.problems[:3]))
    return p.events


# --------------------------------------------------------------------------
# Summary used by the coordinator / sensors
# --------------------------------------------------------------------------
def build_summary(
    subjects: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    events: list[dict[str, Any]],
    today: date,
    recent_days: int = 14,
) -> dict[str, Any]:
    grades = [g for s in subjects for g in s["grades"]]
    indexed = [(g["date"], i, g) for i, g in enumerate(grades)]
    latest = max(indexed)[2] if indexed else None
    cutoff = (today - timedelta(days=recent_days)).isoformat()
    recent = sorted((g for g in grades if g["date"] >= cutoff), key=lambda g: g["date"], reverse=True)
    seen: set[tuple[str, str]] = set()
    upcoming = []
    for e in sorted(events, key=lambda e: (e["date"], e["name"])):
        key = (e["date"], e["name"])
        if key in seen or e["date"] < today.isoformat():
            continue
        seen.add(key)
        days_left = (datetime.fromisoformat(e["date"]).date() - today).days
        upcoming.append({**e, "id": f"{e['date']}|{e['name']}", "days_left": days_left})
    return {
        "subjects": subjects,
        "grades": grades,
        "latest_grade": latest,
        "recent_grades": recent,
        "messages": messages,
        "unread": [m for m in messages if m["unread"] is True],
        "unknown_read_state": [m for m in messages if m["unread"] is None],
        "upcoming": upcoming,
        "next_test": next((e for e in upcoming if e["is_test"]), None),
    }
