# Kalendarz F1 z wynikami (iCal)

Subskrybowalny kalendarz `.ics` z wszystkimi sesjami Formuły 1, który aktualizuje się w trakcie sezonu:

| Moment | Co widać w kalendarzu |
|---|---|
| Przed weekendem | Treningi, kwalifikacje, sprint, wyścig – godziny w Twojej strefie czasowej |
| Po kwalifikacjach | Tytuł kwalifikacji: `· Pole: Norris`, w opisie wyniki Q1/Q2/Q3. Wyścig: tytuł z pole position, w opisie pełne wyniki kwalifikacji (= pola startowe) |
| Po kwalifikacjach do sprintu | To samo dla sprintu: pole w tytule, wyniki SQ1/SQ2/SQ3 w opisie sprintu |
| Po sprincie | Tytuł: `🏁 … · Wygrał: …`, w opisie klasyfikacja i oficjalne pola startowe sprintu |
| Po wyścigu | Tytuł: `🏆 … · Wygrał: Verstappen (Red Bull)`, w opisie podium, pełna klasyfikacja (start → meta, zyski/straty pozycji, punkty), najszybsze okrążenie i oficjalne pola startowe |

Domyślnie kalendarz zawiera bieżący i poprzedni sezon.

## Adres subskrypcji

`https://norbertcala.github.io/f1-calendar/f1.ics`
(strona z przyciskiem: `https://norbertcala.github.io/f1-calendar/`)

## Jak to działa

- `f1_calendar.py` pobiera dane z darmowego [Jolpica-F1 API](https://github.com/jolpica/jolpica-f1) (następca Ergast) i generuje `f1.ics`. Używa wyłącznie biblioteki standardowej Pythona.
- GitHub Actions (`.github/workflows/update.yml`) co 15 minut robi szybkie sprawdzenie (bez zapytań do API F1). Pełna aktualizacja rusza, gdy minął próg 3, 6 lub 8 godzin po kwalifikacjach, sprincie i wyścigu, a opublikowany kalendarz jest starszy niż ten próg – dzięki temu opóźnione lub pominięte uruchomienia harmonogramu GitHuba nie gubią aktualizacji. Dodatkowo gdy kalendarz ma ponad 7 dni, po każdym pushu i po ręcznym uruchomieniu.
- Jeśli API chwilowo nie działa, publikacja się nie wykona i zostaje poprzednia wersja pliku. Kalendarz nigdy nie zostanie wyczyszczony.
- UID wydarzeń są stałe, więc aplikacja kalendarza aktualizuje istniejące wpisy zamiast tworzyć duplikaty.

## Strona techlove.pl/f1

Statyczna strona z przyciskiem subskrypcji jest w `techlove/f1/index.html`. Wgraj folder `f1` do katalogu głównego WordPressa (obok `wp-config.php`), a będzie dostępna pod `https://techlove.pl/f1/`. Podgląd: `https://norbertcala.github.io/f1-calendar/podglad-techlove/`.

## Ograniczenia

- Pola startowe przed wyścigiem pochodzą z wyników kwalifikacji, więc nie uwzględniają kar. Po wyścigu pokazywane są oficjalne pola startowe.
- Wyniki kwalifikacji do sprintu pochodzą z [OpenF1](https://openf1.org) (Jolpica ich nie publikuje). Są pobierane tylko dla bieżącego sezonu; jeśli OpenF1 nie odpowiada, kalendarz generuje się bez nich.
- Wyniki trafiają do API zwykle w ciągu kilku godzin od sesji.
- Odświeżanie zależy od aplikacji: Apple Calendar można ustawić na „co godzinę”, Google Calendar odświeża subskrypcje co kilka–kilkanaście godzin.

## Uruchomienie lokalne

```bash
python f1_calendar.py                 # bieżący + poprzedni sezon -> public/f1.ics
python f1_calendar.py --years 2026    # wybrane sezony
F1_YEARS="2025 2026" python f1_calendar.py
```

Test offline na danych przykładowych:

```bash
python tests/make_fixtures.py
python f1_calendar.py --years 2026 --fixtures tests/data --out /tmp/f1.ics
```

Ten sam plik można hostować na własnym serwerze (np. QNAP) – wystarczy cron uruchamiający skrypt co godzinę i serwer WWW udostępniający `public/`.
