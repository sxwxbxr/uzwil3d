"""Gemeindegrenzen aus swissBOUNDARIES3D laden und das Bearbeitungsgebiet bestimmen."""

import math

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from .common import get_json

FIND_URL = "https://api3.geo.admin.ch/rest/services/api/MapServer/find"
LAYER = "ch.swisstopo.swissboundaries3d-gemeinde-flaeche.fill"


def fetch_municipality(name: str):
    data = get_json(
        FIND_URL,
        {
            "layer": LAYER,
            "searchText": name,
            "searchField": "gemname",
            "contains": "false",
            "returnGeometry": "true",
            "geometryFormat": "geojson",
            "sr": "2056",
        },
    )
    hits = [r for r in data.get("results", []) if r.get("properties", {}).get("gemname") == name]
    if not hits:
        raise RuntimeError(f"Gemeinde {name!r} nicht gefunden: {data}")
    # Bei mehreren Jahrgängen den neuesten nehmen
    hits.sort(key=lambda r: r["properties"].get("jahr", 0), reverse=True)
    return hits[0]


def build_area(cfg: dict) -> dict:
    features = []
    geoms = []
    for name in cfg["municipalities"]:
        hit = fetch_municipality(name)
        geom = shape(hit["geometry"])
        geoms.append(geom)
        props = hit["properties"]
        features.append(
            {
                "type": "Feature",
                "properties": {"name": name, "bfs": props.get("gde_nr") or hit.get("id"), "jahr": props.get("jahr")},
                "geometry": mapping(geom),
            }
        )
        print(f"  {name}: {geom.area / 1e6:.2f} km²")

    union = unary_union(geoms)
    minx, miny, maxx, maxy = union.buffer(cfg["buffer_m"]).bounds
    ts = cfg["tile_size_m"]
    bbox = [
        math.floor(minx / ts) * ts,
        math.floor(miny / ts) * ts,
        math.ceil(maxx / ts) * ts,
        math.ceil(maxy / ts) * ts,
    ]
    return {
        "bbox_lv95": bbox,
        "origin_lv95": [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2],
        "geojson": {"type": "FeatureCollection", "crs": "EPSG:2056", "features": features},
    }
