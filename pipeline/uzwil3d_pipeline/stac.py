"""Kacheln aus der swisstopo-STAC-API für ein LV95-Gebiet auswählen."""

import re

from pyproj import Transformer

from .common import get_json

STAC = "https://data.geo.admin.ch/api/stac/v0.9"
TILE_RE = re.compile(r"_(\d{4})_(\d{4})-(\d{4})$")

_to_wgs84 = Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)


def bbox_wgs84(bbox_lv95):
    e0, n0, e1, n1 = bbox_lv95
    lons, lats = _to_wgs84.transform([e0, e1, e0, e1], [n0, n0, n1, n1])
    return [min(lons), min(lats), max(lons), max(lats)]


def items(collection: str, bbox_lv95) -> list[dict]:
    url = f"{STAC}/collections/{collection}/items"
    params = {"bbox": ",".join(f"{v:.6f}" for v in bbox_wgs84(bbox_lv95)), "limit": 100}
    result = []
    while url:
        page = get_json(url, params)
        result.extend(page.get("features", []))
        nxt = [l for l in page.get("links", []) if l.get("rel") == "next"]
        url, params = (nxt[0]["href"], None) if nxt else (None, None)
    return result


def latest_tiles(collection: str, bbox_lv95, gsd: float, suffix: str = ".tif") -> dict[tuple[int, int], str]:
    """Pro 1-km-Kachel (E-km, N-km) die URL des neuesten Assets mit passender Auflösung."""
    e0, n0, e1, n1 = bbox_lv95
    best: dict[tuple[int, int], tuple[int, str]] = {}
    for item in items(collection, bbox_lv95):
        m = TILE_RE.search(item["id"])
        if not m:
            continue
        year, ek, nk = (int(g) for g in m.groups())
        if not (e0 <= ek * 1000 < e1 and n0 <= nk * 1000 < n1):
            continue
        for asset in item.get("assets", {}).values():
            if asset.get("eo:gsd") == gsd and asset["href"].endswith(suffix):
                if (ek, nk) not in best or best[(ek, nk)][0] < year:
                    best[(ek, nk)] = (year, asset["href"])
    return {k: v[1] for k, v in best.items()}
