"""Ergänzung zu swissBUILDINGS3D: Gebäude, die seit dessen Erfassung entstanden sind oder fehlen.

Grundriss aus der amtlichen Vermessung (Bodenbedeckung Art=Gebaeude, geodienste.ch),
Geschosszahl aus dem GWR (api3.geo.admin.ch). Ein AV-Gebäude wird ergänzt, wenn weniger als
ein Drittel seiner Fläche von swissBUILDINGS3D bedeckt ist.

shortcut: Flachdach mit Höhe aus Geschosszahl (3 m pro Geschoss + 1 m), bis swissBUILDINGS3D nachgeführt ist.
"""

import json

import mapbox_earcut as earcut
import numpy as np
import shapely
from shapely.geometry import shape

from .common import ROOT, get_json

AV_WFS = "https://wfs.geodienste.ch/av_0/deu"
IDENTIFY = "https://api3.geo.admin.ch/rest/services/api/MapServer/identify"
FLOOR_M = 3.0
UNKNOWN_HEIGHT_M = 4.0


def _cells(bbox, cell=1000):
    e0, n0, e1, n1 = bbox
    for e in range(e0, e1, cell):
        for n in range(n0, n1, cell):
            yield e, n, e + cell, n + cell


def _av_buildings(bbox) -> list[dict]:
    feats = {}
    for e, n, e2, n2 in _cells(bbox):
        flt = (
            '<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0"><fes:And><fes:BBOX>'
            "<fes:ValueReference>msGeometry</fes:ValueReference>"
            '<gml:Envelope xmlns:gml="http://www.opengis.net/gml/3.2" srsName="urn:ogc:def:crs:EPSG::2056">'
            f"<gml:lowerCorner>{e} {n}</gml:lowerCorner><gml:upperCorner>{e2} {n2}</gml:upperCorner>"
            "</gml:Envelope></fes:BBOX><fes:PropertyIsEqualTo><fes:ValueReference>Art</fes:ValueReference>"
            "<fes:Literal>Gebaeude</fes:Literal></fes:PropertyIsEqualTo></fes:And></fes:Filter>"
        )
        res = get_json(AV_WFS, {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
                                "TYPENAMES": "ms:LCSF", "OUTPUTFORMAT": "geojson", "FILTER": flt})
        for f in res["features"]:
            # Gebäude an Zellgrenzen kommen doppelt; Geometrie als Schlüssel
            feats[json.dumps(f["geometry"]["coordinates"][0][:3])] = {
                "egid": f["properties"].get("GWR_EGID") or None, "geometry": f["geometry"]}
    return list(feats.values())


def _gwr_floors(bbox) -> dict[str, int]:
    floors = {}
    for e, n, e2, n2 in _cells(bbox):
        g = f"{e},{n},{e2},{n2}"
        offset = 0
        while True:
            res = get_json(IDENTIFY, {
                "geometryType": "esriGeometryEnvelope", "geometry": g, "mapExtent": g, "imageDisplay": "500,500,96",
                "tolerance": 0, "layers": "all:ch.bfs.gebaeude_wohnungs_register", "sr": 2056,
                "geometryFormat": "geojson", "returnGeometry": "false", "limit": 200, "offset": offset})["results"]
            for f in res:
                p = f["attributes"] if "attributes" in f else f["properties"]
                if p.get("gastw"):
                    floors[str(p["egid"])] = int(p["gastw"])
            if len(res) < 200:
                break
            offset += 200
    return floors


def _load(cfg, bbox):
    cache = ROOT / cfg["cache_dir"] / "av_gwr.json"
    if cache.exists():
        return json.loads(cache.read_text())
    data = {"av": _av_buildings(bbox), "floors": _gwr_floors(bbox)}
    cache.write_text(json.dumps(data))
    return data


def _ring_walls(ring: np.ndarray, z0: float, z1: float) -> np.ndarray:
    a, b = ring[:-1], ring[1:]
    lo = lambda p: np.column_stack([p, np.full(len(p), z0)])  # noqa: E731
    hi = lambda p: np.column_stack([p, np.full(len(p), z1)])  # noqa: E731
    t1 = np.stack([lo(a), lo(b), hi(b)], axis=1)
    t2 = np.stack([lo(a), hi(b), hi(a)], axis=1)
    return np.concatenate([t1, t2])


def supplement(cfg: dict, bbox, covered: np.ndarray, ground) -> list[dict]:
    """Fehlende Gebäude als {"wall", "roof"}-Dreiecke in LV95 + Höhe.

    covered: bool-Raster 1 m, Zeile 0 = Süden, Ursprung bbox[0:2]; ground(e, n) = Geländehöhe.
    """
    e0, n0 = bbox[0], bbox[1]
    data = _load(cfg, bbox)
    out = []
    for f in data["av"]:
        for poly in getattr(shape(f["geometry"]), "geoms", [shape(f["geometry"])]):
            if poly.area < 4:
                continue
            minx, miny, maxx, maxy = poly.bounds
            xs, ys = np.meshgrid(np.arange(int(minx), int(maxx) + 1) + 0.5, np.arange(int(miny), int(maxy) + 1) + 0.5)
            inside = shapely.contains_xy(poly, xs, ys)
            if not inside.any():
                continue
            r = (ys[inside] - n0).astype(int)
            c = (xs[inside] - e0).astype(int)
            ok = (r >= 0) & (r < covered.shape[0]) & (c >= 0) & (c < covered.shape[1])
            if not ok.any() or covered[r[ok], c[ok]].mean() >= 1 / 3:
                continue
  
            rings = [np.asarray(poly.exterior.coords)[:, :2]] + [np.asarray(i.coords)[:, :2] for i in poly.interiors]
            z0 = min(ground(x, y) for x, y in rings[0])
            floors = data["floors"].get(f["egid"] or "")
            z1 = z0 + (floors * FLOOR_M + 1 if floors else UNKNOWN_HEIGHT_M)
            walls = np.concatenate([_ring_walls(rg, z0, z1) for rg in rings])
            flat = np.concatenate([rg[:-1] for rg in rings])
            ends = np.cumsum([len(rg) - 1 for rg in rings]).astype(np.uint32)
            idx = earcut.triangulate_float64(flat, ends)
            roof = np.column_stack([flat[idx], np.full(len(idx), z1)]).reshape(-1, 3, 3)
            out.append({"wall": walls, "roof": roof})
    return out
