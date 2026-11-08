"""HTTP client for the mantica.net parent portal."""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any
from urllib.parse import urlparse

import aiohttp

from . import extras, parser

_LOGGER = logging.getLogger(__name__)
TIMEOUT = aiohttp.ClientTimeout(total=30)
CALENDAR_MONTHS = 3  # current + next two
# Identify honestly, so the portal admins can tell what this traffic is.
USER_AGENT = (
    "HomeAssistant-Mantica/0.5 "
    "(unofficial Home Assistant integration; parent account, read-only; "
    "+https://github.com/marcin-olo/HA_Mantica)"
)


def new_session() -> aiohttp.ClientSession:
    """Own cookie jar (PHP session) and an honest User-Agent."""
    return aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(), headers={"User-Agent": USER_AGENT}
    )


class ManticaError(Exception):
    """Base error."""


class ManticaAuthError(ManticaError):
    """The server showed the login form again after we sent credentials."""


class ManticaConnectionError(ManticaError):
    """Network/HTTP problem, maintenance page or any other unexpected page."""


class ManticaLayoutError(ManticaError):
    """Logged in fine, but a page's structure is not recognised."""


def normalize_host(value: str) -> str:
    """'https://x.mantica.net/index.php' -> 'https://x.mantica.net'."""
    value = value.strip()
    if "://" not in value:
        value = "https://" + value
    p = urlparse(value)
    return f"{p.scheme}://{p.netloc}".rstrip("/")


def semester_for(today: date) -> int:
    """Polish school year: 1st semester Sep-Jan, 2nd Feb-Aug."""
    return 1 if today.month in (9, 10, 11, 12, 1) else 2


class ManticaClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._base = normalize_host(host)
        self._username = username
        self._password = password
        self._lock_obj: asyncio.Lock | None = None
        # Timetable and school-year calendar change rarely: read once a day.
        self._static_day: date | None = None
        self._static: dict[str, Any] = {}

    @property
    def _lock(self) -> asyncio.Lock:
        # Created lazily inside the running loop (Python < 3.10 binds a Lock
        # to the loop current at construction time).
        if self._lock_obj is None:
            self._lock_obj = asyncio.Lock()
        return self._lock_obj

    async def async_close(self) -> None:
        await self._session.close()

    async def _request(self, method: str, path: str, **kwargs: Any) -> str:
        call = self._session.post if method == "POST" else self._session.get
        try:
            async with call(f"{self._base}/{path}", timeout=TIMEOUT, **kwargs) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise ManticaConnectionError(f"{path}: HTTP {resp.status}")
                return text
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise ManticaConnectionError(f"{path}: {err!r}") from err

    async def login(self) -> None:
        text = await self._request(
            "POST",
            "index.php",
            data={
                "Logowanie": "1",
                "username": self._username,
                "password": self._password,
                "zaloguj": "Zaloguj",
            },
        )
        if parser.is_logged_in(text):
            return
        if parser.is_login_page(text):
            raise ManticaAuthError(
                "Server returned the login form again (wrong password, "
                "or the login form changed)"
            )
        raise ManticaConnectionError(
            "Unexpected page after login (maintenance or site change)"
        )

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> str:
        text = await self._request("GET", path, params=params)
        if parser.is_logged_in(text):
            return text
        if not parser.is_login_page(text):
            # Neither logged-in nor login form: maintenance or a changed site.
            # Do NOT treat this as a password problem.
            raise ManticaConnectionError(
                f"{path}: unexpected page (maintenance or site change)"
            )
        await self.login()  # session missing/expired
        text = await self._request("GET", path, params=params)
        if parser.is_logged_in(text):
            return text
        raise ManticaConnectionError(f"{path}: still not logged in after login")

    async def fetch_message_html(self, url: str) -> str:
        """Raw HTML of one message (poczta_czytaj.php?id=...).

        The portal loads it into a box via AJAX, so the fragment may lack the
        logged-in markers; only an actual login form means "log in again".
        NOTE: opening a message most likely marks it as read on the portal.
        """
        path = url.lstrip("/")
        if not path.startswith("poczta_czytaj.php?"):
            raise ManticaLayoutError(f"unexpected message link: {url[:60]}")
        async with self._lock:
            text = await self._request("GET", path)
            if parser.is_login_page(text):
                await self.login()
                text = await self._request("GET", path)
                if parser.is_login_page(text):
                    raise ManticaConnectionError(f"{path}: still not logged in after login")
        return text

    async def fetch_all(self, today: date) -> dict[str, Any]:
        sem = semester_for(today)
        async with self._lock:
            pages: list[tuple[str, str, int, int]] = []
            grades_html = await self._get("oceny_uczen.php", {"semestr": sem})
            inbox_html = await self._get("poczta_new.php", {"message": "inbox"})
            year, month = today.year, today.month
            for _ in range(CALENDAR_MONTHS):
                html = await self._get(
                    "terminarz_uczen.php", {"month": month, "year": year, "klasa": ""}
                )
                pages.append(("terminarz_uczen.php", html, year, month))
                month += 1
                if month > 12:
                    month, year = 1, year + 1
            # Extra pages: a layout problem there must not hide grades and
            # messages, so they are parsed separately below.
            extra_html: dict[str, str] = {}
            if self._static_day != today:
                extra_html["timetable"] = await self._get("plan_lekcji_uczen.php")
                extra_html["school_calendar"] = await self._get("kalendarz_info.php")
            extra_html["substitutions"] = await self._get("p_zastepstwa_new_u.php")
            extra_html["remarks"] = await self._get("uwagi_uczen.php", {"semestr": sem})
            extra_html["homework"] = await self._get("zadania_domowe_info.php")
        try:
            subjects = parser.parse_grades(grades_html)
        except parser.LayoutError as err:
            raise ManticaLayoutError(f"Oceny: {err}") from err
        try:
            messages = parser.parse_messages(inbox_html)
        except parser.LayoutError as err:
            raise ManticaLayoutError(f"Wiadomości: {err}") from err
        events: list[dict[str, Any]] = []
        for _, html, y, m in pages:
            try:
                events += parser.parse_calendar(html, y, m)
            except parser.LayoutError as err:
                raise ManticaLayoutError(f"Terminarz {m:02d}/{y}: {err}") from err
        data = parser.build_summary(subjects, messages, events, today)
        data.update(self._parse_extras(extra_html, today))
        return data

    def _parse_extras(self, pages: dict[str, str], today: date) -> dict[str, Any]:
        """Parsed extra sections; a section that failed is None and its
        error is listed in "extra_errors"."""
        out: dict[str, Any] = {}
        errors: list[str] = []
        for key, label, fn in (
            ("timetable", "Plan lekcji", extras.parse_timetable),
            ("school_calendar", "Kalendarz roku", extras.parse_school_calendar),
            ("substitutions", "Zastępstwa", extras.parse_substitutions),
            ("remarks", "Uwagi", extras.parse_remarks),
            ("homework", "Zadania domowe", extras.parse_homework),
        ):
            if key not in pages:
                out[key] = self._static.get(key)  # read earlier today
                continue
            try:
                out[key] = fn(pages[key])
            except parser.LayoutError as err:
                out[key] = None
                errors.append(f"{label}: {err}")
        if "timetable" in pages and out["timetable"] is not None and out["school_calendar"] is not None:
            self._static = {"timetable": out["timetable"], "school_calendar": out["school_calendar"]}
            self._static_day = today
        out["extra_errors"] = errors
        return out
