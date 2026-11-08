"""HTTP client against a fake server: password errors vs maintenance vs layout."""
import asyncio
from datetime import date

from fixtures import (
    CAL, GRADES, HOMEWORK, INBOX, LOGGED, LOGIN_PAGE, MAINTENANCE, REMARKS, SCHOOL_CAL,
    SUBSTITUTIONS, TIMETABLE, api, cal_for,
)

EXTRA_PAGES = {
    "plan_lekcji_uczen.php": TIMETABLE,
    "kalendarz_info.php": SCHOOL_CAL,
    "p_zastepstwa_new_u.php": SUBSTITUTIONS,
    "uwagi_uczen.php": REMARKS,
    "zadania_domowe_info.php": HOMEWORK,
}

PASSWORD = "secret"


class Resp:
    def __init__(self, status, text):
        self.status, self._text = status, text

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSite:
    """mode: ok | maintenance | maintenance_after_login | http503 | layout | login_form_changed"""

    def __init__(self, mode="ok"):
        self.mode, self.logged, self.requests = mode, False, []

    def post(self, url, data=None, timeout=None):
        self.requests.append(("POST", url))
        if self.mode in ("maintenance", "maintenance_after_login"):
            return Resp(200, MAINTENANCE)
        if self.mode == "login_form_changed" or data.get("password") != PASSWORD:
            return Resp(200, LOGIN_PAGE)
        self.logged = True
        return Resp(200, LOGGED + "<p>pulpit</p>")

    def get(self, url, params=None, timeout=None):
        self.requests.append(("GET", url, dict(params or {})))
        if self.mode == "http503":
            return Resp(503, "Service Unavailable")
        if self.mode == "maintenance":
            return Resp(200, MAINTENANCE)
        if not self.logged:
            return Resp(200, LOGIN_PAGE)
        if url.endswith("oceny_uczen.php"):
            body = GRADES if self.mode != "layout" else GRADES.replace("Oceny bieżące", "Wyniki")
        elif url.endswith("poczta_new.php"):
            body = INBOX
        elif url.rsplit("/", 1)[-1] in EXTRA_PAGES:
            body = EXTRA_PAGES[url.rsplit("/", 1)[-1]]
            if self.mode == "extra_layout" and "zastepstwa" in url:
                body = "<p>inna strona</p>"
        elif "poczta_czytaj.php" in url:
            return Resp(200, "<div>Treść wiadomości</div>")  # AJAX fragment, no markers
        else:
            body = {11: CAL, 12: cal_for("Grudzień 2026"), 1: cal_for("Styczeń 2027")}[params["month"]]
        return Resp(200, LOGGED + body)

    async def close(self):
        pass


def run(mode, password=PASSWORD):
    site = FakeSite(mode)
    client = api.ManticaClient(site, "https://szkola.mantica.net/index.php", "rodzic", password)
    try:
        return asyncio.run(client.fetch_all(date(2026, 11, 8))), site
    except api.ManticaError as err:
        return err, site


def test_happy_path_logs_in_lazily():
    data, site = run("ok")
    assert isinstance(data, dict), data
    assert data["next_test"]["name"] == "Sprawdzian z angielskiego"
    assert sum(1 for r in site.requests if r[0] == "POST") == 1
    months = [r[2]["month"] for r in site.requests if r[0] == "GET" and "terminarz" in r[1]]
    assert months == [11, 12, 1]


def test_wrong_password_is_auth_error():
    err, _ = run("ok", password="bad")
    assert type(err) is api.ManticaAuthError


def test_maintenance_is_not_auth_error():
    err, site = run("maintenance")
    assert type(err) is api.ManticaConnectionError, err
    assert not any(r[0] == "POST" for r in site.requests)  # no login attempt on maintenance page


def test_maintenance_after_login_is_not_auth_error():
    err, _ = run("maintenance_after_login")
    assert type(err) is api.ManticaConnectionError, err


def test_http_error_is_connection_error():
    err, _ = run("http503")
    assert type(err) is api.ManticaConnectionError and "503" in str(err)


def test_layout_change_is_layout_error():
    err, _ = run("layout")
    assert type(err) is api.ManticaLayoutError and str(err).startswith("Oceny:")


def test_normalize_host():
    assert api.normalize_host("przykladowaszkola.mantica.net/index.php") == "https://przykladowaszkola.mantica.net"


def test_message_fragment_without_markers_is_fine():
    site = FakeSite("ok")
    client = api.ManticaClient(site, "https://szkola.mantica.net", "rodzic", PASSWORD)
    html = asyncio.run(client.fetch_message_html("poczta_czytaj.php?id=1&typ=n"))
    assert "Treść" in html
    assert [r[0] for r in site.requests] == ["GET", "POST", "GET"]  # logged in lazily


def test_message_link_must_be_a_message():
    client = api.ManticaClient(FakeSite("ok"), "https://szkola.mantica.net", "rodzic", PASSWORD)
    try:
        asyncio.run(client.fetch_message_html("https://evil.example/x"))
    except api.ManticaLayoutError:
        return
    raise AssertionError("expected ManticaLayoutError")


def test_extra_pages_are_read():
    data, site = run("ok")
    assert data["extra_errors"] == []
    assert data["timetable"]["valid_to"] == "2027-06-25"
    assert len(data["substitutions"]) == 2 and len(data["remarks"]) == 2 and len(data["homework"]) == 1
    assert any(r[1].endswith("uwagi_uczen.php") and r[2] == {"semestr": 1} for r in site.requests if r[0] == "GET")


def test_extra_layout_change_keeps_the_rest():
    data, _ = run("extra_layout")
    assert isinstance(data, dict), data
    assert data["substitutions"] is None and data["timetable"] is not None
    assert data["extra_errors"] and data["extra_errors"][0].startswith("Zastępstwa:")
    assert data["next_test"]["name"] == "Sprawdzian z angielskiego"


def test_timetable_read_once_a_day():
    site = FakeSite("ok")
    client = api.ManticaClient(site, "https://szkola.mantica.net", "rodzic", PASSWORD)

    async def twice():
        await client.fetch_all(date(2026, 11, 8))
        return await client.fetch_all(date(2026, 11, 8))

    data = asyncio.run(twice())
    assert sum(1 for r in site.requests if r[0] == "GET" and r[1].endswith("plan_lekcji_uczen.php")) == 1
    assert data["timetable"]["slots"] and data["school_calendar"]
