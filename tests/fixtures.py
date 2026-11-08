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


extras = importlib.import_module("mantica.extras")

_HEAD = '<table class="new_border"><tr class="table_header"> <td >{} </td> </tr><tr class="panel_tresc"><td>'

TIMETABLE = _HEAD.format("Plan lekcji") + """
<center>Plan obowiązuje od: <b>2026-09-01</b> do: <b>2027-06-25</b></center> <br>
<table style="width:100%; " class="TableFrekwencja" cellspacing="0" onMouseOut="javascript:highlightTableRowVersionA(0);" >
<th style="width: 115px">Lekcja</th> <th >Poniedziałek<br></th> <th >Wtorek<br></th> <th >Środa<br></th> <th >Czwartek<br></th> <th >Piątek<br></th>
<tr onMouseOver="javascript:highlightTableRowVersionA(this, '#dbdbdb');" class="row1"> <td><b>(0)</b> ?-? </td> <td> </td> <td> </td> <td> </td> <td> </td> <td> </td> </tr>
<tr class="row2"> <td><b>(1)</b>08:00-08:45</td> <td> Edukacja wczesnoszkolna </td> <td> Edukacja wczesnoszkolna </td> <td> Język angielski </td> <td> Edukacja wczesnoszkolna </td> <td> Religia </td> </tr>
<tr class="row1"> <td><b>(2)</b>08:55-09:40</td> <td> Wychowanie fizyczne </td> <td> Język niemiecki </td> <td> </td> <td> Edukacja wczesnoszkolna </td> <td> Informatyka </td> </tr>
<tr class="row2"> <td><b>(8)</b>14:30-15:15</td> <td> </td> <td> </td> <td> </td> <td> </td> <td> </td> </tr>
</table></td></tr></table>"""

SUBSTITUTIONS = _HEAD.format("Lista zastępstw") + """<center>
<table style="width:100%"; border="0" onMouseOut="javascript:highlightTableRowVersionA(0);"> <tr> <th>Lp</th> <th>Data zastępstwa</th> <th>Przedmiot</th> <th>Lekcja</th> <th>Zastępstwo za</th> <th>Zastępujący</th> <th>Data dodania</th> <th>Klasa/grupa</th> </tr>
<tr class="row1"> <td><center>1</center></td> <td>2026-11-09</td> <td >Wychowanie fizyczne</td> <td >2</td> <td>Nowak Anna</td> <td>Wiśniewska Ola</td> <td>2026-11-08 11:13:28</td> <td>SP 3A </td>
<tr class="row2"> <td><center>2</center></td> <td>2026-10-09</td> <td >Język angielski</td> <td >3</td> <td>Zielińska Ewa</td> <td>Kowal Jan</td> <td>2026-10-29 10:13:52</td> <td>SP 3A </td>
<tr class="row1"> <td><center>3</center></td> <td>2026-10-09</td> <td >Język angielski</td> <td >3</td> <td>Zielińska Ewa</td> <td>Mazur Piotr</td> <td>2026-10-08 07:17:52</td> <td>SP 3A </td>
</table><br></center></td></tr></table>"""

SCHOOL_CAL = _HEAD.format("Kalendarz roku szkolnego") + """<br>
<table style="width:95%"; border="0"> <th>Lp</th> <th>Wydarzenie</th> <th>Data</th> <th>Wolne</th>
<tr class="row1"> <td><center>1</center></td> <td><b><font style="font-size: 14px;">Rok szkolny</font></b></td> <td>2026-09-01 - 2027-06-26</td> <td><center></td> </tr>
<tr class="row2"> <td><center>2</center></td> <td>Dzień Niepodległości</td> <td>2026-11-11 - 2026-11-11</td> <td><center><b><font color="green">TAK</font></b></td> </tr>
<tr class="row1"> <td><center>3</center></td> <td>Dzień wolny od zajęć edukacyjnych</td> <td>2026-11-12 - 2026-11-13</td> <td><center><b><font color="green">TAK</font></b></td> </tr>
<tr class="row2"> <td><center>4</center></td> <td>Egzamin ósmoklasisty</td> <td>2027-05-11 - 2027-05-13</td> <td><center><b><font color="red">NIE</font></b></td> </tr>
</table></td></tr></table>"""

REMARKS = _HEAD.format("Uwagi półrocze 1") + """<br><center><br><table style='width: 100%;' border="1"> <tr> <td valign="top" style="text-align: justify;">
<font style="font-size: 14px;" color="green" title="Uwaga pozytywna.<br>Wystawiona: <b>2026-10-30 13:18:08</b> przez <b>Anna Nowak</b>" style="text-align: justify;" class="vtip" > <b>Pochwała za przebranie. </b> </font> <hr>
<font style="font-size: 14px;" color="red" title="Uwaga negatywna.<br>Wystawiona: <b>2026-10-05 11:08:33</b> przez <b>Jan Kowal</b>" class="vtip" > <b>Rozmowy na lekcji. </b> </font>
</td> </table></center></td></tr></table>"""

HOMEWORK_EMPTY = _HEAD.format("Lista zadań domowych") + """<center>
<table style="width:100%"; border="0"> <th>Lp</th> <th>Przedmiot</th> <th>Nauczyciel</th> <th>Temat</th> <th>Data zadania</th> <th>Termin wykonania</th> <th>Treść</th>
<tr> <td colspan="7"><center><b>Legenda:</b>&nbsp;<span style="background-color: #ff7f00;">&nbsp;&nbsp;</span> - zadanie do wykonania na jutro</td> </tr>
</table><br></center></td></tr></table>"""

HOMEWORK = HOMEWORK_EMPTY.replace(
    "</table><br></center>",
    """<tr class="row1"><td>1</td><td>Język angielski</td><td>Ewa Zielińska</td><td>Unit 2</td><td>2026-11-06</td><td>2026-11-10</td><td>Ćw. 3 i 4, str. 21</td></tr>
</table><br></center>""",
)
