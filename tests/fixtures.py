"""Loads the integration's HA-free modules and provides HTML fixtures
that mirror the structure seen on the live portal (Nov 2026)."""
import importlib
import pathlib
import sys
import types

COMPONENT = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "mantica"

# Minimal aiohttp stand-in so api.py can be imported without Home Assistant.
try:
    import aiohttp  # noqa: F401
except ImportError:
    stub = types.ModuleType("aiohttp")

    class ClientError(Exception):
        pass

    stub.ClientError = ClientError
    stub.ClientTimeout = lambda **kw: None
    stub.ClientSession = object
    sys.modules["aiohttp"] = stub

# Register the package without running __init__.py (which needs HA).
pkg = types.ModuleType("mantica")
pkg.__path__ = [str(COMPONENT)]
sys.modules.setdefault("mantica", pkg)
parser = importlib.import_module("mantica.parser")
policy = importlib.import_module("mantica.policy")
api = importlib.import_module("mantica.api")

LOGGED = '<td id="logo_on">Zalogowany jako: <b>RODZIC/OPIEKUN</b></td><a href="index.php?logout=1">Wyloguj</a>'

LOGIN_PAGE = """<html><body><form action="index.php" method="post">
<input type="hidden" name="Logowanie" value="1"><input type="text" name="username" id="pole_logowania">
<input type="password" name="password" id="password"><input type="submit" name="zaloguj" value="Zaloguj">
</form></body></html>"""

MAINTENANCE = "<html><body><h1>Przerwa techniczna</h1><p>Zapraszamy później.</p></body></html>"

GRADES = """
<script>var menu1=new Array(); menu1[0]='<table><tr><td>menu</td></tr></table>';</script>
<table class="new_border"><tr><td>
<table><tr><th> Przedmiot </th><th> Oceny bieżące </th><th> Średnia </th><th> Semestralna </th></tr>
<tr onmouseover="javascript:highlightTableRowVersionA(this, '#dbdbdb');" class="row1">
<td style="text-align: right; width: 20%"><b>Język angielski: &nbsp; &nbsp; </b></td>
<td style="text-align: left; width: 290px; padding: 9px;">
<!-- <font size="4" color="#5330FF" class="vtip" title="<b>Opis działu:</b> Praca na lekcji - ulubiony sport<br><b>Waga oceny: </b>1<br><b>Wystawił/a: </b>Ewa Zielińska, 2026-09-25 ">4</font>, -->
<span style="background-color:#5330FF; line-height: 28px;" class="vtip" title="&lt;b&gt;Opis działu:&lt;/b&gt; Praca na lekcji - ulubiony sport&lt;br&gt;&lt;b&gt;Waga oceny: &lt;/b&gt;1&lt;br&gt;&lt;b&gt;Wystawił/a: &lt;/b&gt;Ewa Zielińska, 2026-09-25 ">4</span>
<!-- <font>commented dup</font> -->
<span style="background-color:#FFFFFF;" class="vtip" title="&lt;b&gt;Opis działu:&lt;/b&gt; piosenka z rozdziału 1: We like sport!&lt;br&gt;&lt;b&gt;Waga oceny: &lt;/b&gt;2&lt;br&gt;&lt;b&gt;Wystawił/a: &lt;/b&gt;Ewa Zielińska, 2026-09-29 ">6</span>
</td>
<td style="text-align: center; width: 10%; font-size: 18px"> <b>5.00</b> </td>
<td style="text-align: justify; width: 40%;"> &nbsp; &nbsp; --------------- </td></tr>
<tr class="row2"><td style="text-align: right"><b>Edukacja społeczna: &nbsp;</b></td><td style="x"> </td>
<td style="x"> </td><td style="x"> &nbsp; --------------- </td></tr>
<tr class="row1"><td><b>Wychowanie fizyczne: &nbsp;</b></td><td>
<span class="vtip" title="&lt;b&gt;Opis działu:&lt;/b&gt; AKTYWNOŚĆ NA LEKCJI&lt;br&gt;&lt;b&gt;Waga oceny: &lt;/b&gt;1&lt;br&gt;&lt;b&gt;Wystawił/a: &lt;/b&gt;Katarzyna Wójcik, 2026-10-22 ">5</span>
<span class="vtip" title="&lt;b&gt;Opis działu:&lt;/b&gt; basen&lt;br&gt;&lt;b&gt;Waga oceny: &lt;/b&gt;1&lt;br&gt;&lt;b&gt;Wystawił/a: &lt;/b&gt;Katarzyna Wójcik, 2026-10-22 ">5</span> -
</td><td><b>5,00</b></td><td>Bardzo dobry</td></tr>
<tr class="row2"><td colspan="4"><b>Zachowanie:</b> ---------------</td></tr>
</table>
</td></tr></table>"""

INBOX = """
<table border="0" width="100%"><tbody><tr>
<th style="width: 5%;"><input type="checkbox" onclick="Zaznacz(this);"></th>
<th style="width: 45%;">Temat</th><th style="width: 3%;"><img src="images//ikony/spinacz.png" border="0"></th>
<th style="width: 35%;">Nadawca</th><th style="width: 15%;">Data</th></tr>
<tr onmouseover="x" class="row1" id="tr_message_view">
<td style="text-align: center;"><input class="zaznacz" type="checkbox" name="usun_o[]" value="30257"></td>
<td style="border-left: 1px solid #aaa;"> <a href="#" onclick="loadContentBox('poczta_czytaj.php?id=30257&amp;typ=n&amp;imie=Sekretariat&amp;nazwisko=Testowa', 'czytaj_wiadomosc'); return false;">
&nbsp;<img src="images/mail_open.gif" alt="Przeczytana wiadomość" title="Przeczytana wiadomość" style="border: 0;"> informacja </a> </td>
<td style="text-align: center;"><img src="images//ikony/spinacz.png" width="70%" border="0"></td>
<td style="border-left: 1px solid #aaa;"> Sekretariat Testowa </td>
<td style="border-left: 1px solid #aaa;"> 2026-10-29 11:58:41</td></tr>
<tr class="row2" id="tr_message_view">
<td><input class="zaznacz" type="checkbox" name="usun_o[]" value="30200"></td>
<td><a href="#" onclick="loadContentBox('poczta_czytaj.php?id=30200&amp;typ=n', 'x');"><img src="images/mail.gif" alt="Nieprzeczytana wiadomość"> Zebranie z rodzicami. </a></td>
<td></td><td> Anna Nowak </td><td> 2026-10-22 10:10:24</td></tr>
</tbody></table>
<a href="#">[1-10]</a> <a href="#">[11-20]</a>"""

CAL = """
<table class="terminarz"><tr><th><a href="terminarz_uczen.php?month=10&amp;year=2026&amp;klasa=">&lt;&lt;</a></th>
<th colspan="5"><b>Listopad 2026</b></th><th><a href="#">&gt;&gt;</a></th></tr>
<tr><th><div><font color="red">Nie</font></div></th><th><div>Pon</div></th><th><div>Wto</div></th></tr>
<tr><td style="background-color: #ffffff;">8</td><td>9</td>
<td style="background-color: #ffffff;" align="center"><table border="0" width="100%"><tbody><tr>
<td style="border:0px; vertical-align: top; text-align: center;">10<br>
<table bgcolor="FFF719" width="100%"><tbody><tr>
<td style="text-align: left;" class="vtip" title="&lt;b&gt;Nauczyciel:&lt;/b&gt; Ewa Zielińska&lt;br&gt;&lt;b&gt;Opis:&lt;/b&gt; Piosenka z rozdziału 2 na ocenę.&lt;br&gt;&lt;b&gt;Data dodania:&lt;/b&gt; 2026-11-03 &lt;br&gt;&lt;b&gt;Widoczne:&lt;/b&gt; 3A">piosenka j. angielski</td>
</tr></tbody></table></td></tr></tbody></table></td>
<td>11</td>
<td style="background-color: #ffffff;"><table><tbody><tr>
<td style="border:0px;">17<br>
<table bgcolor="0FFF57"><tbody><tr>
<td class="vtip" title="&lt;b&gt;Nauczyciel:&lt;/b&gt; Piotr Lewandowski&lt;br&gt;&lt;b&gt;Opis:&lt;/b&gt; &lt;br&gt;&lt;b&gt;Data dodania:&lt;/b&gt; 2026-11-06 &lt;br&gt;&lt;b&gt;Widoczne:&lt;/b&gt; 3A">Backzeit- piosenka dla chętnych.</td></tr></tbody></table>
<table bgcolor="FF0000"><tbody><tr>
<td class="vtip" title="&lt;b&gt;Nauczyciel:&lt;/b&gt; Piotr Lewandowski&lt;br&gt;&lt;b&gt;Opis:&lt;/b&gt; Rozdział 2&lt;br&gt;&lt;b&gt;Data dodania:&lt;/b&gt; 2026-11-06 &lt;br&gt;&lt;b&gt;Widoczne:&lt;/b&gt; 3A">Sprawdzian z angielskiego</td></tr></tbody></table>
</td></tr></tbody></table></td><td>18</td></tr></table>
<table class="other"><tr><td class="vtip" title="x">must be ignored</td></tr></table>"""


def cal_for(month_name: str) -> str:
    """Calendar page for another month (no events)."""
    return (
        '<table class="terminarz"><tr><th><b>' + month_name + "</b></th></tr>"
        "<tr><td>1</td><td>2</td></tr></table>"
    )
