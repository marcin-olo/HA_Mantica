"""Every site-change scenario from the review: the integration must either
keep working correctly or fail loudly (LayoutError) - never return wrong data."""
from fixtures import CAL, GRADES, INBOX, MAINTENANCE, LOGIN_PAGE, parser as p


def raises_layout(fn, *args):
    try:
        fn(*args)
    except p.LayoutError as err:
        return str(err)
    raise AssertionError(f"{fn.__name__} should have raised LayoutError")


def ids(subjects):
    return {g["id"] for s in subjects for g in s["grades"]}


BASE_IDS = ids(p.parse_grades(GRADES))


# Live portal (Nov 2026): tooltip HTML is NOT escaped inside title="..."
def test_raw_html_in_tooltip():
    raw = GRADES.replace("&lt;", "<").replace("&gt;", ">")
    assert raw != GRADES
    subj = p.parse_grades(raw)
    assert ids(subj) == BASE_IDS
    g = subj[0]["grades"][0]
    assert g["value"] == "4" and g["weight"] == "1"
    assert g["description"] == "Praca na lekcji - ulubiony sport"
    assert g["teacher"] == "Ewa Zielińska"


# Live portal: edited grade + "Oceny bez opisu" grade wrapped in a <label>
LIVE_CELL = (
    '<span style="background-color:#FFFFFF;" class="vtip" title="<b>Opis działu:</b> '
    'Wiersz na pamięć<br><b>Waga oceny: </b>1<br><b>Wystawił/a: </b>Anna Nowak, '
    '2026-10-23 <br><b>Zmieniał/a: </b>Anna Nowak, 2026-10-24 ">5+</span> <br><br>'
    '<label class="vtip" title="Oceny bez opisu <br>Wystawił/a: <b>Anna Nowak, '
    '2026-10-13 </b> "><span style="background-color:#ffffff; height: 20px;">-</span>'
    '<span style="background-color:#ffffff;">+</span></label>'
)


def test_label_grades_and_edited_grade():
    html = (
        "<table><tr><th>Przedmiot</th><th>Oceny bieżące</th></tr>"
        f"<tr><td>Edukacja polonistyczna</td><td>{LIVE_CELL}</td></tr></table>"
    )
    grades = p.parse_grades(html)[0]["grades"]
    assert [(g["value"], g["date"], g["teacher"]) for g in grades] == [
        ("-", "2026-10-13", "Anna Nowak"),
        ("+", "2026-10-13", "Anna Nowak"),
        ("5+", "2026-10-23", "Anna Nowak"),  # issue date, not the edit date
    ]
    assert grades[0]["weight"] == "" and grades[2]["weight"] == "1"
    assert grades[2]["description"] == "Wiersz na pamięć"


# A. row class changed -> still parsed (rows found by table structure, not class)
def test_row_class_changed():
    subj = p.parse_grades(GRADES.replace('class="row1"', 'class="row1 highlight"').replace('class="row2"', ""))
    assert ids(subj) == BASE_IDS


# B. new "predicted grade" column -> columns mapped by header names
def test_predicted_column_added():
    html = GRADES.replace("<th> Semestralna </th>", "<th>Przewidywana</th><th> Semestralna </th>")
    html = html.replace('<td style="text-align: justify; width: 40%;">', "<td>5</td><td>")
    html = html.replace("<td>Bardzo dobry</td>", "<td>5</td><td>Bardzo dobry</td>")
    html = html.replace('<td style="x"> &nbsp; ---------------', '<td>-</td><td style="x"> ---------------')
    subj = p.parse_grades(html)
    en, pe = subj[0], subj[2]
    assert en["predicted_grade"] == "5" and en["final_grade"] is None
    assert pe["final_grade"] == "Bardzo dobry" and pe["predicted_grade"] == "5"


# B2. column added to rows but header unchanged -> rows ignored -> loud failure
def test_column_added_without_header():
    html = GRADES.replace("<td><b>5,00</b></td>", "<td>x</td><td><b>5,00</b></td>")
    html = html.replace('<td style="text-align: center; width: 10%; font-size: 18px">', "<td>x</td><td>")
    html = html.replace('<td style="x"> </td>\n<td style="x"> </td>', '<td></td><td></td><td></td>')
    raises_layout(p.parse_grades, html)


# C. tooltip label renamed -> same ids (no flood), description still found
def test_tooltip_labels_renamed():
    subj = p.parse_grades(GRADES.replace("Opis działu:", "Opis:").replace("Wystawił/a:", "Wystawił:"))
    assert ids(subj) == BASE_IDS
    assert subj[0]["grades"][0]["description"] == "Praca na lekcji - ulubiony sport"
    assert subj[0]["grades"][0]["teacher"] == "Ewa Zielińska"


# C2. tooltip without date -> loud failure
def test_tooltip_without_date():
    assert "without date" in raises_layout(p.parse_grades, GRADES.replace("2026-09-25", "25.09"))


# I. grades rendered as <font> instead of <span> -> loud failure
def test_grade_tag_changed():
    html = GRADES.replace("<span", "<font").replace("</span>", "</font>")
    assert "unparsed grade text" in raises_layout(p.parse_grades, html)


# J. grades header renamed -> loud failure
def test_grades_header_missing():
    raises_layout(p.parse_grades, GRADES.replace("Oceny bieżące", "Wyniki"))


# D. unknown read icon -> state "unknown" (not counted as unread)
def test_unknown_message_icon():
    msgs = p.parse_messages(INBOX.replace("mail_open.gif", "read.gif").replace("Przeczytana wiadomość", "x"))
    assert [m["unread"] for m in msgs] == [None, True]


def test_inbox_header_missing():
    raises_layout(p.parse_messages, INBOX.replace("Nadawca", "Od kogo"))


def test_empty_inbox_is_fine():
    head = INBOX.split('<tr onmouseover="x"')[0] + "</tbody></table>"
    assert p.parse_messages(head) == []


# E. server ignores ?month= -> header mismatch -> loud failure
def test_month_parameter_ignored():
    assert "page shows listopad 2026" in raises_layout(p.parse_calendar, CAL, 2026, 12)


# F. calendar table class renamed -> loud failure
def test_calendar_table_renamed():
    raises_layout(p.parse_calendar, CAL.replace('class="terminarz"', 'class="kalendarz"'), 2026, 11)


# G. no <br> after day number -> dates still correct
def test_day_without_br():
    ev = p.parse_calendar(CAL.replace("17<br>", "17 "), 2026, 11)
    assert [e["date"] for e in ev] == ["2026-11-10", "2026-11-17", "2026-11-17"]


# G2. day number missing entirely -> loud failure, no stale date from the previous cell
def test_day_number_missing():
    assert "no day number" in raises_layout(p.parse_calendar, CAL.replace("17<br>", "<br>"), 2026, 11)


def test_invalid_day():
    raises_layout(p.parse_calendar, CAL.replace("17<br>", "31<br>"), 2026, 11)


# H. logout link renamed -> second marker still detects the session
def test_logout_link_renamed():
    assert p.is_logged_in('<a href="logout.php">Wyloguj</a> Zalogowany jako: X')


# I. maintenance page is neither logged in nor a login form
def test_maintenance_page():
    assert not p.is_logged_in(MAINTENANCE) and not p.is_login_page(MAINTENANCE)
    assert p.is_login_page(LOGIN_PAGE)
