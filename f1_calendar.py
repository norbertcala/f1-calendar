#!/usr/bin/env python3
"""
F1 „live” kalendarz iCal.

Pobiera terminarz i wyniki z Jolpica-F1 API (następca Ergast) i generuje plik .ics:
  * wszystkie sesje weekendu (treningi, kwalifikacje, sprint, wyścig),
  * po kwalifikacjach -> w wydarzeniu wyścigu/sprintu lista pól startowych,
  * po wyścigu/sprincie -> zwycięzca w tytule i pełna klasyfikacja w opisie,
  * po kwalifikacjach -> pole position w tytule i wyniki Q1/Q2/Q3 w opisie.

Bez zależności zewnętrznych (tylko biblioteka standardowa Pythona).

Użycie:
  python f1_calendar.py                       # bieżący + poprzedni sezon -> public/f1.ics
  python f1_calendar.py --years 2026          # tylko jeden sezon
  python f1_calendar.py --fixtures tests/data # dane z plików zamiast API (testy)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

API = "https://api.jolpi.ca/ergast/f1"
PAGE = 100
CAL_NAME = "F1 – terminarz i wyniki"
UID_DOMAIN = "f1-calendar.norbertcala.github.io"

# klucz w JSON-ie API -> (kod sesji, nazwa po polsku, czas trwania w minutach)
SESSIONS = [
    ("FirstPractice", "fp1", "Trening 1", 60),
    ("SecondPractice", "fp2", "Trening 2", 60),
    ("ThirdPractice", "fp3", "Trening 3", 60),
    ("SprintQualifying", "sq", "Kwalifikacje do sprintu", 45),
    ("SprintShootout", "sq", "Kwalifikacje do sprintu", 45),  # nazwa z 2023
    ("Sprint", "sprint", "Sprint", 60),
    ("Qualifying", "quali", "Kwalifikacje", 60),
]
RACE_DURATION = 120


# --------------------------------------------------------------------------- dane


class Source:
    """Pobiera JSON z API (z paginacją i ponawianiem) albo z katalogu z plikami."""

    def __init__(self, fixtures: Path | None = None):
        self.fixtures = fixtures
        self._cache: dict[str, list[dict]] = {}

    def _get(self, path: str, offset: int = 0) -> dict:
        if self.fixtures:
            f = self.fixtures / (path.strip("/").replace("/", "_") + ".json")
            if not f.exists():
                return {"MRData": {"total": "0", "RaceTable": {"Races": []}}}
            return json.loads(f.read_text(encoding="utf-8"))

        url = f"{API}/{path}.json?limit={PAGE}&offset={offset}"
        last_err: Exception | None = None
        for attempt in range(5):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "f1-ical-calendar/1.0"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.load(r)
                time.sleep(0.4)  # limity Jolpica: ok. 4 zapytania/s
                return data
            except urllib.error.HTTPError as e:
                last_err = e
                wait = 10 * (attempt + 1) if e.code == 429 else 3 * (attempt + 1)
            except (urllib.error.URLError, TimeoutError) as e:
                last_err = e
                wait = 3 * (attempt + 1)
            print(f"  ! {url}: {last_err} – ponawiam za {wait}s", file=sys.stderr)
            time.sleep(wait)
        raise RuntimeError(f"Nie udało się pobrać {url}: {last_err}")

    def races(self, path: str) -> list[dict]:
        """Zwraca listę wyścigów z RaceTable, łącząc strony i rozbite rundy."""
        if path in self._cache:
            return self._cache[path]
        first = self._get(path)
        total = int(first["MRData"].get("total", 0))
        pages = [first]
        if not self.fixtures:
            offset = PAGE
            while offset < total:
                pages.append(self._get(path, offset))
                offset += PAGE

        merged: dict[str, dict] = {}
        for p in pages:
            for race in p["MRData"]["RaceTable"]["Races"]:
                key = f"{race.get('season')}-{race['round']}"
                if key not in merged:
                    merged[key] = race
                    continue
                # ta sama runda rozbita na dwie strony -> doklej wiersze
                for list_key in ("Results", "QualifyingResults", "SprintResults"):
                    if list_key in race:
                        merged[key].setdefault(list_key, []).extend(race[list_key])
        self._cache[path] = list(merged.values())
        return self._cache[path]


# --------------------------------------------------------------------- formatowanie


def parse_dt(d: str, t: str | None) -> datetime | date:
    if not t:
        return date.fromisoformat(d)
    t = t.rstrip("Z")
    return datetime.fromisoformat(f"{d}T{t}").replace(tzinfo=timezone.utc)


def driver_name(drv: dict) -> str:
    return f"{drv.get('givenName', '')} {drv.get('familyName', '')}".strip()


def short_name(drv: dict) -> str:
    return drv.get("familyName") or drv.get("code") or "?"


def team(row: dict) -> str:
    return row.get("Constructor", {}).get("name", "")


def gp_name(race: dict) -> str:
    return race["raceName"].replace("Grand Prix", "GP")


def grid_label(g: str) -> str:
    return "z alei serwisowej" if g in ("0", "") else f"P{g}"


def format_quali(rows: list[dict]) -> str:
    lines = ["Wyniki kwalifikacji:"]
    for r in sorted(rows, key=lambda x: int(x["position"])):
        best = r.get("Q3") or r.get("Q2") or r.get("Q1") or "brak czasu"
        seg = "Q3" if r.get("Q3") else "Q2" if r.get("Q2") else "Q1"
        lines.append(f"P{r['position']}  {driver_name(r['Driver'])} ({team(r)}) – {best} [{seg}]")
    return "\n".join(lines)


def format_starting_grid(rows: list[dict], from_results: bool) -> str:
    """Pola startowe. Z wyników wyścigu (oficjalne, po karach) albo z kwalifikacji."""
    if from_results:
        ordered = sorted(rows, key=lambda r: (int(r.get("grid") or 0) == 0, int(r.get("grid") or 0)))
        lines = ["Pola startowe (oficjalne):"]
        for r in ordered:
            lines.append(f"{grid_label(r.get('grid', '0'))}  {driver_name(r['Driver'])} ({team(r)})")
    else:
        lines = ["Pola startowe wg kwalifikacji (przed ewentualnymi karami):"]
        for r in sorted(rows, key=lambda x: int(x["position"])):
            lines.append(f"P{r['position']}  {driver_name(r['Driver'])} ({team(r)})")
    return "\n".join(lines)


def format_results(rows: list[dict], kind: str) -> str:
    lines = [f"Wyniki – {kind}:"]
    fastest = None
    for r in sorted(rows, key=lambda x: int(x["position"])):
        pos = r.get("positionText", r["position"])
        pos_lbl = f"P{pos}" if pos.isdigit() else pos  # R = nie ukończył, D = dyskwalifikacja
        grid = r.get("grid", "")
        move = ""
        if grid and grid != "0" and pos.isdigit():
            diff = int(grid) - int(pos)
            move = f" ▲{diff}" if diff > 0 else f" ▼{-diff}" if diff < 0 else " ="
        time_or_status = r.get("Time", {}).get("time") or r.get("status", "")
        pts = r.get("points", "0")
        pts_lbl = f", {pts} pkt" if pts not in ("0", "0.0") else ""
        lines.append(
            f"{pos_lbl}  {driver_name(r['Driver'])} ({team(r)}) – {time_or_status}"
            f" | start {grid_label(grid)}{move}{pts_lbl}"
        )
        fl = r.get("FastestLap", {})
        if fl.get("rank") == "1":
            fastest = f"{driver_name(r['Driver'])} – {fl.get('Time', {}).get('time', '')} (okr. {fl.get('lap', '?')})"
    if fastest:
        lines += ["", f"Najszybsze okrążenie: {fastest}"]
    return "\n".join(lines)


# ------------------------------------------------------ polskie nazwy i flagi

# fragment nazwy wyścigu (ang.) -> nazwa w dopełniaczu po polsku
GP_PL = [
    ("Bahrain Grand Prix in Malaysia", "Bahrajnu w Malezji"),
    ("Australian", "Australii"), ("Chinese", "Chin"), ("Japanese", "Japonii"), ("Bahrain", "Bahrajnu"),
    ("Saudi Arabian", "Arabii Saudyjskiej"), ("Miami", "Miami"), ("Emilia Romagna", "Emilii-Romanii"),
    ("Monaco", "Monako"), ("Barcelona", "Barcelony-Katalonii"), ("Spanish", "Hiszpanii"), ("Madrid", "Madrytu"),
    ("Canadian", "Kanady"), ("Austrian", "Austrii"), ("British", "Wielkiej Brytanii"), ("Belgian", "Belgii"),
    ("Hungarian", "Węgier"), ("Dutch", "Holandii"), ("Italian", "Włoch"), ("Azerbaijan", "Azerbejdżanu"),
    ("Singapore", "Singapuru"), ("United States", "USA"), ("Mexico City", "Meksyku"), ("Mexican", "Meksyku"),
    ("São Paulo", "São Paulo"), ("Brazilian", "Brazylii"), ("Las Vegas", "Las Vegas"), ("Qatar", "Kataru"),
    ("Abu Dhabi", "Abu Zabi"), ("Portuguese", "Portugalii"), ("Turkish", "Turcji"), ("French", "Francji"),
    ("German", "Niemiec"), ("Russian", "Rosji"), ("Malaysian", "Malezji"), ("Korean", "Korei"),
    ("Indian", "Indii"), ("European", "Europy"), ("Styrian", "Styrii"), ("Tuscan", "Toskanii"),
    ("Eifel", "Eifel"), ("Sakhir", "Sakhiru"), ("70th Anniversary", "70-lecia"),
]

COUNTRY_ISO = {
    "Australia": "au", "China": "cn", "Japan": "jp", "Bahrain": "bh", "Saudi Arabia": "sa", "USA": "us",
    "United States": "us", "Italy": "it", "Monaco": "mc", "Spain": "es", "Canada": "ca", "Austria": "at",
    "UK": "gb", "United Kingdom": "gb", "Belgium": "be", "Hungary": "hu", "Netherlands": "nl",
    "Azerbaijan": "az", "Singapore": "sg", "Mexico": "mx", "Brazil": "br", "Qatar": "qa", "UAE": "ae",
    "United Arab Emirates": "ae", "Malaysia": "my", "Portugal": "pt", "Turkey": "tr", "France": "fr",
    "Germany": "de", "Russia": "ru",
}


def gp_name_pl(race_name: str) -> str:
    for key, pl in GP_PL:
        if key in race_name:
            return f"GP {pl}"
    return race_name.replace("Grand Prix", "GP")


# ---------------------------------------------------------------------------- iCal


def ics_escape(s: str) -> str:
    return (
        s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\n").replace("\n", "\\n")
    )


def fold(line: str) -> str:
    """Zawijanie linii do 75 bajtów (RFC 5545), bez rozcinania znaków UTF-8."""
    out, cur, cur_len = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        limit = 75 if not out else 74  # linie kontynuacji zaczynają się spacją
        if cur_len + n > limit:
            out.append(cur)
            cur, cur_len = ch, n
        else:
            cur += ch
            cur_len += n
    out.append(cur)
    return "\r\n ".join(out)


def fmt_dt(v: datetime | date) -> str:
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return v.strftime("%Y%m%d")


def vevent(uid: str, start: datetime | date, minutes: int, summary: str, description: str,
           location: str, url: str | None, categories: str) -> list[str]:
    content_hash = hashlib.sha1(f"{summary}|{description}|{start}".encode()).hexdigest()
    # SEQUENCE rośnie, gdy zmienia się treść -> klienci kalendarza łatwiej wychwytują aktualizację
    seq = int(content_hash[:6], 16) % 100000
    lines = ["BEGIN:VEVENT", f"UID:{uid}"]
    stamp = start if isinstance(start, datetime) else datetime.combine(start, datetime.min.time(), timezone.utc)
    lines.append(f"DTSTAMP:{fmt_dt(stamp)}")
    if isinstance(start, datetime):
        lines.append(f"DTSTART:{fmt_dt(start)}")
        lines.append(f"DTEND:{fmt_dt(start + timedelta(minutes=minutes))}")
    else:
        lines.append(f"DTSTART;VALUE=DATE:{fmt_dt(start)}")
        lines.append(f"DTEND;VALUE=DATE:{fmt_dt(start + timedelta(days=1))}")
    lines += [
        f"SEQUENCE:{seq}",
        f"SUMMARY:{ics_escape(summary)}",
        f"DESCRIPTION:{ics_escape(description)}",
        f"LOCATION:{ics_escape(location)}",
        f"CATEGORIES:{categories}",
        "TRANSP:TRANSPARENT",
    ]
    if url:
        lines.append(f"URL:{url}")
    lines.append("END:VEVENT")
    return [fold(l) for l in lines]


# --------------------------------------------------------------------- budowa sezonu


def past_winners(src: Source, race: dict, n: int = 3) -> list[dict]:
    """Ostatnich n zwycięzców wyścigów na tym samym torze przed danym wyścigiem."""
    cid = race.get("Circuit", {}).get("circuitId")
    if not cid:
        return []
    out = []
    for r in src.races(f"circuits/{cid}/results/1"):
        if r.get("date", "") >= race["date"] or not r.get("Results"):
            continue
        w = r["Results"][0]
        out.append({"season": int(r["season"]), "date": r["date"], "raceName": r.get("raceName", ""),
                    "driver": driver_name(w["Driver"]), "team": team(w)})
    out.sort(key=lambda x: x["date"], reverse=True)
    return out[:n]


def format_past_winners(winners: list[dict]) -> str:
    if not winners:
        return ""
    return "Ostatni zwycięzcy na tym torze:\n" + "\n".join(f"{w['season']}  {w['driver']} ({w['team']})" for w in winners)


def build_season(src: Source, year: int, with_history: bool = False) -> list[list[str]]:
    print(f"Sezon {year}: terminarz…", file=sys.stderr)
    schedule = src.races(str(year))
    print(f"Sezon {year}: kwalifikacje, wyniki, sprinty…", file=sys.stderr)
    quali = {r["round"]: r.get("QualifyingResults", []) for r in src.races(f"{year}/qualifying")}
    results = {r["round"]: r.get("Results", []) for r in src.races(f"{year}/results")}
    sprints = {r["round"]: r.get("SprintResults", []) for r in src.races(f"{year}/sprint")}

    events: list[list[str]] = []
    for race in schedule:
        rnd = race["round"]
        circuit = race.get("Circuit", {})
        loc = circuit.get("Location", {})
        location = f"{circuit.get('circuitName', '')}, {loc.get('locality', '')}, {loc.get('country', '')}".strip(", ")
        gp = gp_name(race)
        header = f"{race['raceName']} {year} – runda {rnd}\n{location}"
        url = race.get("url")
        uid = lambda code: f"{year}-{int(rnd):02d}-{code}@{UID_DOMAIN}"  # noqa: E731

        q_rows, r_rows, s_rows = quali.get(rnd, []), results.get(rnd, []), sprints.get(rnd, [])

        seen = set()
        for key, code, label, minutes in SESSIONS:
            if key not in race or code in seen:
                continue
            seen.add(code)
            s = race[key]
            start = parse_dt(s["date"], s.get("time"))
            summary = f"F1 {label} – {gp}"
            desc = header

            if code == "quali" and q_rows:
                pole = next((r for r in q_rows if r["position"] == "1"), None)
                if pole:
                    summary = f"F1 Kwalifikacje – {gp} · Pole: {short_name(pole['Driver'])}"
                desc += "\n\n" + format_quali(q_rows)
            elif code == "sprint":
                if s_rows:
                    win = next((r for r in s_rows if r["position"] == "1"), None)
                    if win:
                        summary = f"🏁 F1 Sprint – {gp} · Wygrał: {short_name(win['Driver'])}"
                    desc += "\n\n" + format_results(s_rows, "Sprint")
                    desc += "\n\n" + format_starting_grid(s_rows, from_results=True)
                else:
                    desc += "\n\nPola startowe pojawią się po zakończeniu sprintu (API nie publikuje wyników kwalifikacji do sprintu)."
            elif code == "sq" and s_rows:
                sq_pole = next((r for r in s_rows if r.get("grid") == "1"), None)
                if sq_pole:
                    summary = f"F1 Kwalifikacje do sprintu – {gp} · Pole: {short_name(sq_pole['Driver'])}"
                desc += "\n\n" + format_starting_grid(s_rows, from_results=True)

            events.append(vevent(uid(code), start, minutes, summary, desc, location, url, "F1"))

        # wyścig
        start = parse_dt(race["date"], race.get("time"))
        summary = f"F1 Wyścig – {gp}"
        desc = header
        if r_rows:
            win = next((r for r in r_rows if r["position"] == "1"), None)
            if win:
                summary = f"🏆 F1 {gp} · Wygrał: {short_name(win['Driver'])} ({team(win)})"
            podium = [r for r in sorted(r_rows, key=lambda x: int(x["position"])) if int(r["position"]) <= 3]
            if podium:
                desc += "\n\nPodium: " + ", ".join(f"{r['position']}. {short_name(r['Driver'])}" for r in podium)
            desc += "\n\n" + format_results(r_rows, "Wyścig")
            desc += "\n\n" + format_starting_grid(r_rows, from_results=True)
        elif q_rows:
            pole = next((r for r in q_rows if r["position"] == "1"), None)
            if pole:
                summary = f"F1 Wyścig – {gp} · Pole: {short_name(pole['Driver'])}"
            desc += "\n\n" + format_starting_grid(q_rows, from_results=False)
        else:
            desc += "\n\nPola startowe pojawią się po kwalifikacjach."
        if with_history:
            hist = format_past_winners(past_winners(src, race))
            if hist:
                desc += "\n\n" + hist
        events.append(vevent(uid("race"), start, RACE_DURATION, summary, desc, location, url, "F1"))

    print(f"Sezon {year}: {len(events)} wydarzeń", file=sys.stderr)
    return events


def build_calendar(src: Source, years: list[int]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//norbertcala//F1 live calendar//PL",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        fold(f"X-WR-CALNAME:{ics_escape(CAL_NAME)}"),
        fold("X-WR-CALDESC:Sesje F1 z polami startowymi po kwalifikacjach i wynikami po wyścigu. Dane: Jolpica-F1 API."),
        "X-WR-TIMEZONE:UTC",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    latest = max(years)
    for y in years:
        for ev in build_season(src, y, with_history=(y == latest)):
            lines += ev
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def iso(v: datetime | date) -> str:
    return v.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if isinstance(v, datetime) else v.isoformat()


def build_gp_json(src: Source, year: int) -> dict:
    """Dane dla strony: terminarz sezonu, podium i zwycięzcy z poprzednich lat na danym torze."""
    results = {r["round"]: r.get("Results", []) for r in src.races(f"{year}/results")}
    races = []
    for race in src.races(str(year)):
        circuit = race.get("Circuit", {})
        loc = circuit.get("Location", {})
        sessions, seen = [], set()
        for key, code, label, minutes in SESSIONS:
            if key in race and code not in seen:
                seen.add(code)
                st = parse_dt(race[key]["date"], race[key].get("time"))
                sessions.append({"code": code, "label": label, "start": iso(st), "minutes": minutes,
                                 "allDay": not isinstance(st, datetime)})
        rs = parse_dt(race["date"], race.get("time"))
        sessions.append({"code": "race", "label": "Wyścig", "start": iso(rs), "minutes": RACE_DURATION,
                         "allDay": not isinstance(rs, datetime)})
        sessions.sort(key=lambda s: s["start"])
        podium = [{"pos": int(r["position"]), "driver": driver_name(r["Driver"]), "team": team(r)}
                  for r in sorted(results.get(race["round"], []), key=lambda x: int(x["position"]))[:3]]
        races.append({
            "season": year, "round": int(race["round"]), "raceName": race["raceName"],
            "namePl": gp_name_pl(race["raceName"]), "circuit": circuit.get("circuitName", ""),
            "locality": loc.get("locality", ""), "country": loc.get("country", ""),
            "iso": COUNTRY_ISO.get(loc.get("country", ""), ""),
            "sessions": sessions, "podium": podium,
            "pastWinners": [{k: w[k] for k in ("season", "driver", "team")} for w in past_winners(src, race)],
        })
    return {"generated": iso(datetime.now(timezone.utc)), "season": year, "races": races}


# ------------------------------------------------------------ kiedy aktualizować

# Sesje, po których pojawiają się nowe dane (treningi nie zmieniają kalendarza).
RESULT_SESSIONS = ("quali", "sq", "sprint", "race")
UPDATE_AFTER_HOURS = (3, 6, 8)
CHECK_WINDOW = timedelta(minutes=70)  # cron co godzinę + zapas na opóźnienia GitHuba


def update_due(ics_text: str, now: datetime) -> tuple[bool, str]:
    """Czy teraz przypada aktualizacja: 3, 6 lub 8 godzin po końcu sesji z wynikami."""
    uid = end = None
    for line in ics_text.replace("\r\n ", "").splitlines():
        if line.startswith("UID:"):
            uid = line[4:]
        elif line.startswith("DTEND:"):
            end = datetime.strptime(line[6:], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        elif line.startswith("DTEND;VALUE=DATE:"):
            # sesja bez godziny – traktujemy koniec dnia jako koniec sesji
            end = datetime.strptime(line[17:], "%Y%m%d").replace(tzinfo=timezone.utc)
        elif line == "END:VEVENT":
            code = (uid or "").split("@")[0].rsplit("-", 1)[-1]
            if end and code in RESULT_SESSIONS:
                for h in UPDATE_AFTER_HOURS:
                    t = end + timedelta(hours=h)
                    if now - CHECK_WINDOW < t <= now:
                        return True, f"{h} h po {uid}"
            uid = end = None
    return False, "brak sesji 3/6/8 h temu"


def check(url: str) -> int:
    now = datetime.now(timezone.utc)
    if now.weekday() == 0 and now.hour == 6:
        due, why = True, "cotygodniowe odświeżenie terminarza"
    else:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "f1-ical-calendar/1.0"}), timeout=30) as r:
                due, why = update_due(r.read().decode("utf-8"), now)
        except Exception as e:  # brak opublikowanego pliku -> zbuduj go
            due, why = True, f"nie udało się pobrać obecnego kalendarza ({e})"
    print(f"Aktualizacja: {'TAK' if due else 'nie'} – {why}", file=sys.stderr)
    if gh := os.environ.get("GITHUB_OUTPUT"):
        with open(gh, "a") as f:
            f.write(f"run={'true' if due else 'false'}\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    now = datetime.now(timezone.utc).year
    ap.add_argument("--years", type=int, nargs="+", default=[int(y) for y in os.environ.get("F1_YEARS", "").split()] or [now - 1, now])
    ap.add_argument("--out", type=Path, default=Path("public/f1.ics"))
    ap.add_argument("--fixtures", type=Path, help="katalog z zapisanymi odpowiedziami API (testy offline)")
    ap.add_argument("--check", metavar="ICS_URL", help="tylko sprawdź, czy teraz przypada aktualizacja (3/6/8 h po sesji)")
    args = ap.parse_args()

    if args.check:
        return check(args.check)

    src = Source(args.fixtures)
    years = sorted(set(args.years))
    ics = build_calendar(src, years)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(ics, encoding="utf-8", newline="")
    print(f"Zapisano {args.out} ({len(ics.encode()) // 1024} KB)", file=sys.stderr)

    gp = build_gp_json(src, max(years))
    gp_path = args.out.with_name("gp.json")
    gp_path.write_text(json.dumps(gp, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Zapisano {gp_path} ({len(gp['races'])} wyścigów)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
