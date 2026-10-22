"""swissBUILDINGS3D 3.0 (CityGML, LoD2) pro 1-km-Kachel als Dreiecksnetz aufbereiten.

Ausgabe pro Kachel buildings/{E}_{N}.bin:
- Header: Uint32 LE Anzahl Wand-Vertices, Uint32 LE Anzahl Dach-Vertices
- danach Int16 LE (x, y, z) pro Vertex, erst Wände, dann Dächer, je 3 Vertices = 1 Dreieck
- Einheit 2 cm (BUILDING_SCALE), x = Ost und z = Süd relativ zur Kachelmitte, y = Höhe über height_min

Jedes Gebäude landet ganz in der Kachel, in der sein Schwerpunkt liegt.
"""

import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import mapbox_earcut as earcut
import numpy as np

from .av import supplement
from .common import ROOT, download
from .stac import items

COLLECTION = "ch.swisstopo.swissbuildings3d_3_0"
BUILDING_SCALE = 0.02
SHEET_RE = re.compile(r"_(\d{4})_(\d{4}-\d{2})$")

NS = {
    "bldg": "http://www.opengis.net/citygml/building/2.0",
    "gml": "http://www.opengis.net/gml",
}
BUILDING = f"{{{NS['bldg']}}}Building"
SURFACES = {f"{{{NS['bldg']}}}WallSurface": "wall", f"{{{NS['bldg']}}}RoofSurface": "roof"}
POSLIST = f"{{{NS['gml']}}}posList"


def _sheet_urls(bbox) -> dict[str, tuple[int, str]]:
    """Pro LK25-Blatt die CityGML-Datei des neuesten Jahrgangs."""
    best: dict[str, tuple[int, str]] = {}
    for item in items(COLLECTION, bbox):
        m = SHEET_RE.search(item["id"])
        if not m:
            continue
        year, sheet = int(m.group(1)), m.group(2)
        for asset in item.get("assets", {}).values():
            if asset["href"].endswith(".citygml.zip") and (sheet not in best or best[sheet][0] < year):
                best[sheet] = (year, asset["href"])
    return best


def _triangulate(ring: np.ndarray) -> np.ndarray:
    """Planares 3D-Polygon (ohne Schlusspunkt) in Dreiecke zerlegen, liefert (k, 3, 3)."""
    if len(ring) == 3:
        return ring[None]
    drop = int(np.argmax(np.abs(_newell(ring))))
    flat = np.delete(ring, drop, axis=1)
    idx = earcut.triangulate_float64(flat, np.array([len(ring)], dtype=np.uint32))
    return ring[idx.reshape(-1, 3)]


def _newell(ring: np.ndarray) -> np.ndarray:
    nxt = np.roll(ring, -1, axis=0)
    return np.array([
        ((ring[:, 1] - nxt[:, 1]) * (ring[:, 2] + nxt[:, 2])).sum(),
        ((ring[:, 2] - nxt[:, 2]) * (ring[:, 0] + nxt[:, 0])).sum(),
        ((ring[:, 0] - nxt[:, 0]) * (ring[:, 1] + nxt[:, 1])).sum(),
    ])


def _parse(gml: Path):
    """Liefert pro Gebäude {'wall': [Dreiecke], 'roof': [Dreiecke]} in LV95 + Höhe."""
    for _, el in ET.iterparse(gml, events=("end",)):
        if el.tag != BUILDING:
            continue
        tris = {"wall": [], "roof": []}
        for surf in el.iter():
            kind = SURFACES.get(surf.tag)
            if not kind:
                continue
            for pl in surf.iter(POSLIST):
                ring = np.array(pl.text.split(), dtype=np.float64).reshape(-1, 3)[:-1]
                if len(ring) >= 3:
                    tris[kind].append(_triangulate(ring))
        el.clear()
        if tris["wall"] or tris["roof"]:
            yield {k: np.concatenate(v) if v else np.empty((0, 3, 3)) for k, v in tris.items()}


def _ground(cfg: dict, out: Path, bbox, height_min: float):
    """Geländehöhe (m ü. M.) aus den bereits geschriebenen Terrain-Kacheln, nächster Stützpunkt."""
    ts, sp = cfg["tile_size_m"], cfg["terrain_spacing_m"]
    s = ts // sp + 1
    grids = {}

    def h(e: float, n: float) -> float:
        k = (int(e // ts), int(n // ts))
        if k not in grids:
            f = out / "terrain" / f"{k[0]}_{k[1]}.bin"
            grids[k] = np.frombuffer(f.read_bytes(), "<u2").reshape(s, s) if f.exists() else None
        g = grids[k]
        if g is None:
            return height_min
        col = round((e - k[0] * ts) / sp)
        row = round((k[1] * ts + ts - n) / sp)
        return height_min + g[min(row, s - 1), min(col, s - 1)] / 100

    return h


def build_buildings(cfg: dict, area: dict, height_min: float, out: Path) -> dict:
    bbox = area["bbox_lv95"]
    e0, n0, e1, n1 = bbox
    ts = cfg["tile_size_m"]
    cache = ROOT / cfg["cache_dir"] / COLLECTION

    sheets = _sheet_urls(bbox)
    print(f"  {COLLECTION}: {len(sheets)} LK25-Blätter, Jahrgang {sorted({y for y, _ in sheets.values()})}")

    per_tile: dict[tuple[int, int], dict[str, list]] = defaultdict(lambda: {"wall": [], "roof": []})
    count = 0
    for sheet, (_, url) in sorted(sheets.items()):
        zpath = download(url, cache / url.rsplit("/", 1)[-1])
        gml_dir = cache / zpath.name.removesuffix(".zip")
        if not gml_dir.exists():
            with zipfile.ZipFile(zpath) as z:
                z.extractall(gml_dir)
        for gml in sorted(gml_dir.glob("*.gml")):
            for b in _parse(gml):
                allv = np.concatenate([b["wall"], b["roof"]]).reshape(-1, 3)
                ce, cn = allv[:, 0].mean(), allv[:, 1].mean()
                if not (e0 <= ce < e1 and n0 <= cn < n1):
                    continue
                key = (int(ce // ts), int(cn // ts))
                per_tile[key]["wall"].append(b["wall"])
                per_tile[key]["roof"].append(b["roof"])
                count += 1

    # Von swissBUILDINGS3D bedeckte Fläche (1 m, Bounding Box je Dachdreieck reicht dafür)
    covered = np.zeros((n1 - n0, e1 - e0), bool)
    for parts in per_tile.values():
        for roof in parts["roof"]:
            lo = np.floor(roof[:, :, :2].min(axis=1)).astype(int) - (e0, n0)
            hi = np.ceil(roof[:, :, :2].max(axis=1)).astype(int) - (e0, n0)
            for (a, c), (b, d) in zip(lo.clip(0), hi.clip(0)):
                covered[c:d, a:b] = True
    extra = supplement(cfg, bbox, covered, _ground(cfg, out, bbox, height_min))
    for b in extra:
        ce, cn = b["roof"][:, :, 0].mean(), b["roof"][:, :, 1].mean()
        key = (int(ce // ts), int(cn // ts))
        if key in per_tile or (e0 <= ce < e1 and n0 <= cn < n1):
            per_tile[key]["wall"].append(b["wall"])
            per_tile[key]["roof"].append(b["roof"])
    count += len(extra)
    print(f"  {len(extra)} Gebäude aus amtlicher Vermessung + GWR ergänzt")

    (out / "buildings").mkdir(parents=True, exist_ok=True)
    tiles = {}
    total_tris = 0
    for (ek, nk), parts in sorted(per_tile.items()):
        cx, cy = ek * ts + ts / 2, nk * ts + ts / 2
        chunks, counts = [], []
        for kind in ("wall", "roof"):
            v = np.concatenate(parts[kind]).reshape(-1, 3) if parts[kind] else np.empty((0, 3))
            local = np.stack([v[:, 0] - cx, v[:, 2] - height_min, -(v[:, 1] - cy)], axis=1)
            q = np.round(local / BUILDING_SCALE)
            if len(q) and (np.abs(q).max() > 32767):
                raise ValueError(f"Gebäudekoordinaten ausserhalb Int16 in Kachel {ek}_{nk}")
            chunks.append(q.astype("<i2"))
            counts.append(len(v))
        name = f"buildings/{ek}_{nk}.bin"
        header = np.array(counts, dtype="<u4").tobytes()
        (out / name).write_bytes(header + b"".join(c.tobytes() for c in chunks))
        tiles[(ek * ts, nk * ts)] = name
        total_tris += sum(counts) // 3

    print(f"  {count} Gebäude, {total_tris} Dreiecke, {len(tiles)} Kacheln")
    return {"tiles": tiles, "scale": BUILDING_SCALE, "count": count, "covered": covered,
            "year": max(y for y, _ in sheets.values())}
