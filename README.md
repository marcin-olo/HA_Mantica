# Mantica – dziennik szkolny (Home Assistant)

Integracja czyta dziennik mantica.net (konto rodzica): oceny, wiadomości, terminarz.
Domyślnie co 60 minut, tylko w godzinach 6:00–22:00 (do zmiany w opcjach).
Mantica nie ma API, więc to scraping HTML: integracja loguje się jak przeglądarka i odczytuje strony.

> **Zastrzeżenie.** Projekt nieoficjalny, niezwiązany z Michał Owczarek, Marek Kociołek Mantica s.c.
> ani z żadną szkołą. Do prywatnego użytku z własnym kontem rodzica, na własne ryzyko.
> Regulamin Mantica.net nie zakazuje wprost automatycznego dostępu, ale §4 ust. 3 pozwala Spółce
> zablokować konto przy podejrzeniu korzystania niezgodnego z regulaminem lub dobrymi obyczajami.
> Integracja przedstawia się nagłówkiem `User-Agent: HomeAssistant-Mantica/…` i domyślnie
> czyta dziennik raz na godzinę w ciągu dnia. Autor nie odpowiada za blokadę konta ani inne skutki.
> Pobranie treści nowej wiadomości oznacza ją na portalu jako przeczytaną.

## Instalacja
1. HACS → ⋮ → Repozytoria niestandardowe → adres tego repozytorium, typ „Integracja”.
   Potem wyszukaj „Mantica” w HACS i pobierz.
   (Ręcznie: skopiuj folder `custom_components/mantica` do `/config/custom_components/`.)
2. Restart Home Assistanta.
3. Ustawienia → Urządzenia i usługi → Dodaj integrację → „Mantica”.
4. Podaj adres (np. `https://przykladowaszkola.mantica.net`), login i hasło rodzica.
   HA trzyma hasło w `/config/.storage/core.config_entries` (jawnym tekstem, jak większość integracji),
   więc backup HA też je zawiera.
5. Opcjonalnie: na stronie integracji **Konfiguruj** – co ile minut (min. 15) i w jakich godzinach
   czytać dziennik. Poza tymi godzinami integracja nie łączy się z portalem.

## Encje
| Encja | Stan | Atrybuty |
|---|---|---|
| Nieprzeczytane wiadomości | liczba nowych (wg HA) | lista z treścią (`body`), `unread_on_portal`, `unrecognised_icons` |
| Ostatnia wiadomość | temat | nadawca, data, załącznik, `new`, `body` |
| Oznacz wiadomości jako przeczytane (przycisk) | – | zeruje licznik nowych wiadomości w HA |
| Ostatnia ocena | wartość | przedmiot, data, opis, waga, nauczyciel |
| Oceny z ostatnich 14 dni | liczba | lista (do 20) |
| Najbliższe wydarzenie | nazwa | data, days_left, nauczyciel, opis |
| Najbliższy sprawdzian | nazwa | j.w. |
| Nadchodzące wydarzenia | liczba | lista (do 15) |
| Średnia – {przedmiot} | średnia | oceny, `final_grade`, `predicted_grade` |

Długie teksty w atrybutach są skracane (limit 16 KB rekordera HA).

Sprawdzian = wydarzenie z terminarza, którego nazwa lub opis zawiera: sprawdzian, kartkówk*, klasówk*,
praca klasowa, egzamin, dyktando, quiz, test (`TEST_KEYWORDS` w `parser.py`).

## Zdarzenia do automatyzacji
- `mantica_new_grade` – subject, value, date, description, weight, teacher
- `mantica_new_message` – id, subject, sender, received, unread, body
- `mantica_new_calendar_event` – name, date, days_left, teacher, description, added, is_test.
  Tylko wpisy dodane przez szkołę w ostatnich 7 dniach („Data dodania”), żeby przesunięcie okna
  terminarza na nowy miesiąc nie zgłaszało starych wpisów jako nowych.
- `mantica_bulk_update` – type (grades/messages/events), count, items (pierwsze 5).
  Wysyłane zamiast pojedynczych zdarzeń, gdy w jednym odczycie pojawi się więcej niż 5 nowych pozycji
  (np. zmiana strony albo start semestru), żeby nie było lawiny powiadomień.

Pierwszy odczyt po instalacji tylko zapamiętuje istniejące pozycje, bez powiadomień.

### Gotowe powiadomienia (blueprint)
[`blueprints/automation/mantica/powiadomienia.yaml`](blueprints/automation/mantica/powiadomienia.yaml):
Ustawienia → Automatyzacje i sceny → Blueprinty → **Importuj blueprint** → wklej adres tego pliku
na GitHubie. Potem „Utwórz automatyzację”, wybierz telefon i rodzaje powiadomień.

## Co się dzieje, gdy coś pójdzie nie tak
| Sytuacja | Zachowanie |
|---|---|
| Brak sieci, HTTP 4xx/5xx, przerwa techniczna, nieznana strona | Encje niedostępne, HA ponawia przy kolejnym odczycie. Po 4 nieudanych próbach z rzędu (~4 h przy odczycie co godzinę) komunikat w **Ustawienia → Naprawy**. Znika sam po udanym odczycie. |
| Serwer odsyła formularz logowania po wysłaniu hasła | Ponawianie. Dopiero po 3 razach z rzędu HA prosi o hasło. Jeśli hasło się nie zmieniło, mogła się zmienić strona logowania. |
| Strona po zalogowaniu ma nieznaną strukturę (brak tabeli, kolumny, daty oceny, nagłówek miesiąca nie zgadza się z zapytaniem, wydarzenie bez dnia) | Encje niedostępne zamiast błędnych danych. Po 2 próbach komunikat w Naprawach ze szczegółem, co nie pasuje. |
| Nieznana ikona wiadomości | Wiadomość nie jest liczona jako nieprzeczytana. Ostrzeżenie w Naprawach. |
| Wygasła sesja | Ponowne logowanie bez Twojego udziału. |

Odporność na drobne zmiany: kolumny ocen i wiadomości są brane po nazwach nagłówków (w tym nowa kolumna
„przewidywana”), wiersze po strukturze tabeli, a nie po klasach CSS. Identyfikator oceny nie zależy od
opisu, więc zmiana etykiet w dymku nie powoduje „nowych” ocen. Zalogowanie jest rozpoznawane po dwóch
niezależnych znacznikach.

## Uwagi
- Logowanie integracji odświeża „Ostatnie logowanie” w dzienniku, więc sekcja „Oceny dodane od ostatniego logowania” na stronie głównej będzie zwykle pusta.
- Semestr dobierany z daty: wrzesień–styczeń = 1, luty–sierpień = 2.
- Średnie per przedmiot powstają przy starcie; nowy przedmiot wymaga przeładowania integracji.
- Wiadomości: pierwsza strona skrzynki (10 najnowszych). Treść nowych wiadomości jest pobierana (max 5 na odświeżenie), co oznacza je jako przeczytane na portalu - dlatego „nowe” liczy sama integracja, do wciśnięcia przycisku „Oznacz wiadomości jako przeczytane”.
- Ikona nieprzeczytanej wiadomości nie była widoczna przy budowie integracji. Rozpoznawane są typowe
  nazwy, a nieznaną zgłosi komunikat w Naprawach.

## Testy
`python3 tests/run_all.py` – parser, scenariusze zmian na stronie, klient HTTP na fałszywym serwerze
(złe hasło, przerwa techniczna, HTTP 503, zmiana układu), progi błędów i blokada lawiny.
Bez Home Assistanta i bez dostępu do sieci.
