"""ÖV-Fahrplan (GTFS, opentransportdata.swiss) für das Gebiet aufbereiten.

Ausgabe transit.json:
- stops: [[name, E, N], ...]  (Haltepunkte im Gebiet, LV95)
- routes: [[Liniennummer, GTFS route_type], ...]
- trips: [[route, Ziel, Tagesmaske, [[stop, Ankunft s, Abfahrt s], ...]], ...]
  Tagesmaske: Bit i = Fahrt verkehrt am Tag start_date + i
"""

import csv
import io
import json
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from pyproj import Transformer

from .common import ROOT, download
from .network import route_segments

# shortcut: fester Fahrplanjahrgang 2026 (gültig bis 12.12.2026), zum Fahrplanwechsel auf 2027 umstellen
GTFS_URL = "https://data.opentransportdata.swiss/de/dataset/timetable-2026-gtfs2020/permalink"
DAYS = 28


def is_rail(route_type: int) -> bool:
    """GTFS route_type 2 und 100–199 (erweitert) sind Bahn, wie im Client."""
    return route_type == 2 or 100 <= route_type < 200

_to_lv95 = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)


def _rows(z: zipfile.ZipFile, name: str):
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))


def _seconds(t: str) -> int:
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def build_transit(cfg: dict, area: dict, out: Path, today: date | None = None) -> dict:
    e0, n0, e1, n1 = area["bbox_lv95"]
    start = today or datetime.now().date()
    days = [start + timedelta(i) for i in range(DAYS)]
    # Pro Kalenderwoche neu laden, damit der Cache in CI keinen veralteten Fahrplan liefert.
    zpath = download(GTFS_URL, ROOT / cfg["cache_dir"] / "gtfs" / f"gtfs-{start:%G-W%V}.zip")

    with zipfile.ZipFile(zpath) as z:
        stops, stop_idx = [], {}
        for r in _rows(z, "stops.txt"):
            e, n = _to_lv95.transform(float(r["stop_lon"]), float(r["stop_lat"]))
            if e0 <= e < e1 and n0 <= n < n1 and r["location_type"] in ("", "0"):
                stop_idx[r["stop_id"]] = len(stops)
                stops.append([r["stop_name"], round(e, 1), round(n, 1)])
        print(f"  {len(stops)} Haltepunkte im Gebiet")

        # stop_times ist mehrere GB gross: nur Halte im Gebiet behalten, Datei bleibt gezippt.
        times: dict[str, list] = {}
        for r in _rows(z, "stop_times.txt"):
            s = stop_idx.get(r["stop_id"])
            if s is not None:
                times.setdefault(r["trip_id"], []).append(
                    (int(r["stop_sequence"]), s, _seconds(r["arrival_time"]), _seconds(r["departure_time"])))
        times = {t: sorted(v) for t, v in times.items() if len(v) >= 2}

        trip_meta = {}
        for r in _rows(z, "trips.txt"):
            if r["trip_id"] in times:
                trip_meta[r["trip_id"]] = (r["route_id"], r["service_id"], r["trip_headsign"])
        services = {m[1] for m in trip_meta.values()}

        masks = {}
        weekday_cols = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for r in _rows(z, "calendar.txt"):
            if r["service_id"] in services:
                a = datetime.strptime(r["start_date"], "%Y%m%d").date()
                b = datetime.strptime(r["end_date"], "%Y%m%d").date()
                masks[r["service_id"]] = sum(
                    1 << i for i, d in enumerate(days) if a <= d <= b and r[weekday_cols[d.weekday()]] == "1")
        day_bit = {d.strftime("%Y%m%d"): 1 << i for i, d in enumerate(days)}
        for r in _rows(z, "calendar_dates.txt"):
            bit = day_bit.get(r["date"])
            if bit and r["service_id"] in services:
                m = masks.get(r["service_id"], 0)
                masks[r["service_id"]] = m | bit if r["exception_type"] == "1" else m & ~bit

        routes, route_idx = [], {}
        route_info = {r["route_id"]: r for r in _rows(z, "routes.txt")}

    trips = []
    for trip_id, (route_id, service_id, headsign) in trip_meta.items():
        mask = masks.get(service_id, 0)
        if not mask:
            continue
        if route_id not in route_idx:
            r = route_info[route_id]
            route_idx[route_id] = len(routes)
            routes.append([r["route_short_name"], int(r["route_type"])])
        trips.append([route_idx[route_id], headsign, mask, [[s, a, d] for _, s, a, d in times[trip_id]]])

    segments = {"rail": set(), "bus": set()}
    for route, _, _, st in trips:
        kind = "rail" if is_rail(routes[route][1]) else "bus"
        segments[kind].update((st[i - 1][0], st[i][0]) for i in range(1, len(st)) if st[i - 1][0] != st[i][0])
    paths = route_segments(cfg, area["bbox_lv95"], stops, segments)

    data = {"start_date": start.isoformat(), "days": DAYS, "stops": stops, "routes": routes, "trips": trips,
            "paths": paths}
    (out / "transit.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"  {len(routes)} Linien, {len(trips)} Fahrten an {DAYS} Tagen ab {start}")
    return {"transit": "transit.json"}
