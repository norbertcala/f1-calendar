"""Generuje syntetyczne odpowiedzi API w formacie Jolpica/Ergast do testów offline."""
import json
from pathlib import Path

OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)

DRIVERS = [
    ("max_verstappen", "Max", "Verstappen", "VER", "Red Bull"),
    ("norris", "Lando", "Norris", "NOR", "McLaren"),
    ("leclerc", "Charles", "Leclerc", "LEC", "Ferrari"),
    ("hamilton", "Lewis", "Hamilton", "HAM", "Ferrari"),
    ("russell", "George", "Russell", "RUS", "Mercedes"),
    ("antonelli", "Andrea Kimi", "Antonelli", "ANT", "Mercedes"),
]


def drv(i):
    d = DRIVERS[i]
    return {"driverId": d[0], "givenName": d[1], "familyName": d[2], "code": d[3]}, {"name": d[4]}


def circuit(name, city, country):
    return {"circuitName": name, "Location": {"locality": city, "country": country}}


def mr(races, total):
    return {"MRData": {"total": str(total), "RaceTable": {"Races": races}}}


r1 = {"season": "2026", "round": "1", "raceName": "Australian Grand Prix", "url": "https://en.wikipedia.org/wiki/2026_Australian_Grand_Prix",
      "Circuit": circuit("Albert Park Grand Prix Circuit", "Melbourne", "Australia"), "date": "2026-03-08", "time": "04:00:00Z",
      "FirstPractice": {"date": "2026-03-06", "time": "01:30:00Z"}, "SecondPractice": {"date": "2026-03-06", "time": "05:00:00Z"},
      "ThirdPractice": {"date": "2026-03-07", "time": "01:30:00Z"}, "Qualifying": {"date": "2026-03-07", "time": "05:00:00Z"}}
r2 = {"season": "2026", "round": "2", "raceName": "Chinese Grand Prix", "url": "https://en.wikipedia.org/wiki/2026_Chinese_Grand_Prix",
      "Circuit": circuit("Shanghai International Circuit", "Shanghai", "China"), "date": "2026-03-15", "time": "07:00:00Z",
      "FirstPractice": {"date": "2026-03-13", "time": "03:30:00Z"}, "SprintQualifying": {"date": "2026-03-13", "time": "07:30:00Z"},
      "Sprint": {"date": "2026-03-14", "time": "03:00:00Z"}, "Qualifying": {"date": "2026-03-14", "time": "07:00:00Z"}}
r3 = {"season": "2026", "round": "3", "raceName": "Japanese Grand Prix",
      "Circuit": circuit("Suzuka Circuit", "Suzuka", "Japan"), "date": "2026-03-29",  # brak godziny -> wydarzenie całodniowe
      "FirstPractice": {"date": "2026-03-27", "time": "02:30:00Z"}, "Qualifying": {"date": "2026-03-28", "time": "06:00:00Z"}}

(OUT / "2026.json").write_text(json.dumps(mr([r1, r2, r3], 3)))

q_order1 = [2, 0, 1, 4, 3, 5]
q_order2 = [1, 0, 5, 2, 3, 4]


def quali(order):
    rows = []
    for pos, i in enumerate(order, 1):
        d, c = drv(i)
        row = {"position": str(pos), "Driver": d, "Constructor": c, "Q1": f"1:17.{100 + pos}"}
        if pos <= 5:
            row["Q2"] = f"1:16.{500 + pos}"
        if pos <= 3:
            row["Q3"] = f"1:15.{900 + pos}"
        rows.append(row)
    return rows


# kwalifikacje rozbite na dwie strony (test łączenia rund)
(OUT / "2026_qualifying.json").write_text(json.dumps(mr([
    {**{k: r1[k] for k in ("season", "round", "raceName")}, "QualifyingResults": quali(q_order1)[:4]},
    {**{k: r1[k] for k in ("season", "round", "raceName")}, "QualifyingResults": quali(q_order1)[4:]},
    {**{k: r2[k] for k in ("season", "round", "raceName")}, "QualifyingResults": quali(q_order2)},
], 12)))

# wyścig r1: Leclerc z pole, wygrywa Verstappen, Hamilton startuje z alei serwisowej, Antonelli DNF
finish = [(0, "2"), (2, "1"), (1, "3"), (3, "0"), (4, "4"), (5, "6")]
res = []
pts = ["25", "18", "15", "12", "10", "0"]
for pos, (i, grid) in enumerate(finish, 1):
    d, c = drv(i)
    row = {"position": str(pos), "positionText": str(pos) if pos < 6 else "R", "points": pts[pos - 1], "Driver": d, "Constructor": c,
           "grid": grid, "status": "Finished" if pos < 6 else "Engine"}
    if pos == 1:
        row["Time"] = {"time": "1:24:33.123"}
    elif pos < 6:
        row["Time"] = {"time": f"+{pos * 3}.456"}
    if pos == 2:
        row["FastestLap"] = {"rank": "1", "lap": "52", "Time": {"time": "1:19.813"}}
    res.append(row)
(OUT / "2026_results.json").write_text(json.dumps(mr([{**{k: r1[k] for k in ("season", "round", "raceName")}, "Results": res}], 6)))

sprint = []
for pos, i in enumerate([1, 0, 5, 2, 3, 4], 1):
    d, c = drv(i)
    sprint.append({"position": str(pos), "positionText": str(pos), "points": str(max(0, 9 - pos)), "Driver": d, "Constructor": c,
                   "grid": str([2, 1, 3, 4, 6, 5][pos - 1]), "status": "Finished", "Time": {"time": "30:11.000" if pos == 1 else f"+{pos}.1"}})
(OUT / "2026_sprint.json").write_text(json.dumps(mr([{**{k: r2[k] for k in ("season", "round", "raceName")}, "SprintResults": sprint}], 6)))
print("ok")
