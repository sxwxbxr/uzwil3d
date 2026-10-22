"""Strassen- und Bahnnetz aus swissTLM3D (api3.geo.admin.ch) und kürzeste Wege darauf."""

import heapq
import json
import math
from pathlib import Path

import numpy as np

from .common import ROOT, get_json

IDENTIFY = "https://api3.geo.admin.ch/rest/services/api/MapServer/identify"
LAYERS = {"road": "ch.swisstopo.swisstlm3d-strassen", "rail": "ch.swisstopo.swisstlm3d-eisenbahnnetz"}
# swissTLM3D Strassen objektart: 0–12 Strassen, Plätze, Zufahrten; 20 8m Strasse; 21 Autostrasse. Wege (15–19) nicht.
DRIVABLE = set(range(13)) | {20, 21}
PAGE = 200


def _fetch(layer: str, bbox, cell: int = 1000) -> list[list[list[float]]]:
    e0, n0, e1, n1 = bbox
    lines: dict[int, list] = {}
    for e in range(e0, e1, cell):
        for n in range(n0, n1, cell):
            g = f"{e},{n},{e + cell},{n + cell}"
            offset = 0
            while True:
                res = get_json(IDENTIFY, {
                    "geometryType": "esriGeometryEnvelope", "geometry": g, "mapExtent": g,
                    "imageDisplay": "500,500,96", "tolerance": 0, "layers": f"all:{layer}", "sr": 2056,
                    "geometryFormat": "geojson", "returnGeometry": "true", "limit": PAGE, "offset": offset,
                })["results"]
                for f in res:
                    if layer == LAYERS["road"] and f["properties"]["objektart"] not in DRIVABLE:
                        continue
                    geom = f["geometry"]
                    parts = geom["coordinates"] if geom["type"] == "MultiLineString" else [geom["coordinates"]]
                    lines[f["id"]] = [[p[:2] for p in part] for part in parts]
                if len(res) < PAGE:
                    break
                offset += PAGE
    return [part for parts in lines.values() for part in parts]


def load_networks(cfg: dict, bbox) -> dict[str, list]:
    cache = ROOT / cfg["cache_dir"] / "network.json"
    if cache.exists():
        return json.loads(cache.read_text())
    nets = {kind: _fetch(layer, bbox) for kind, layer in LAYERS.items()}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(nets))
    return nets


class Graph:
    """Ungerichteter Graph über die Stützpunkte der Linien; Knoten an gemeinsamen Koordinaten.

    shortcut: Einbahnstrassen und Abbiegeverbote werden ignoriert, reicht für die Darstellung.
    """

    def __init__(self, lines: list):
        ids: dict[tuple, int] = {}
        self.xy: list[tuple[float, float]] = []
        self.adj: list[list[tuple[int, float]]] = []
        for line in lines:
            prev = None
            for x, y in line:
                k = (round(x, 1), round(y, 1))
                if k not in ids:
                    ids[k] = len(self.xy)
                    self.xy.append(k)
                    self.adj.append([])
                i = ids[k]
                if prev is not None and prev != i:
                    d = math.dist(self.xy[prev], self.xy[i])
                    self.adj[prev].append((i, d))
                    self.adj[i].append((prev, d))
                prev = i
        self.arr = np.array(self.xy)

    def nearest(self, x: float, y: float) -> tuple[int, float]:
        d = np.hypot(self.arr[:, 0] - x, self.arr[:, 1] - y)
        i = int(d.argmin())
        return i, float(d[i])

    def paths_from(self, src: int, targets: set[int]) -> dict[int, list[int]]:
        dist, prev, todo = {src: 0.0}, {}, set(targets)
        heap = [(0.0, src)]
        while heap and todo:
            d, u = heapq.heappop(heap)
            if d > dist[u]:
                continue
            todo.discard(u)
            for v, w in self.adj[u]:
                if d + w < dist.get(v, math.inf):
                    dist[v], prev[v] = d + w, u
                    heapq.heappush(heap, (d + w, v))
        out = {}
        for t in targets:
            if t == src or t in prev:
                path = [t]
                while path[-1] != src:
                    path.append(prev[path[-1]])
                out[t] = path[::-1]
        return out


def route_segments(cfg: dict, bbox, stops: list, segments: dict[str, set]) -> dict[str, list]:
    """Pro Abschnitt "kind:a-b" eine Polylinie [[E, N], ...] entlang Strasse bzw. Gleis.

    Abschnitte ohne plausiblen Weg (Halt zu weit vom Netz, Umweg > 3x) bleiben gerade.
    """
    nets = load_networks(cfg, bbox)
    result, routed = {}, 0
    for kind, pairs in segments.items():
        g = Graph(nets["rail" if kind == "rail" else "road"])
        snap = {}
        for s in {s for pair in pairs for s in pair}:
            i, d = g.nearest(stops[s][1], stops[s][2])
            snap[s] = i if d < 150 else None
        by_src: dict[int, set] = {}
        for a, b in pairs:
            by_src.setdefault(a, set()).add(b)
        for a, bs in by_src.items():
            found = g.paths_from(snap[a], {snap[b] for b in bs if snap[b] is not None}) if snap[a] is not None else {}
            for b in bs:
                pa, pb = stops[a][1:3], stops[b][1:3]
                line = [pa, pb]
                nodes = found.get(snap[b]) if snap[b] is not None else None
                if nodes is not None:
                    cand = [pa] + [list(g.xy[i]) for i in nodes] + [pb]
                    length = sum(math.dist(p, q) for p, q in zip(cand, cand[1:]))
                    if length <= 3 * math.dist(pa, pb) + 300:
                        line, routed = cand, routed + 1
                result[f"{kind}:{a}-{b}"] = line
    print(f"  {routed} von {len(result)} Abschnitten auf Strasse/Gleis geführt")
    return result
