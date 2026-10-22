"""Strassen- und Bahnnetz aus swissTLM3D (api3.geo.admin.ch) und kürzeste Wege darauf."""

import heapq
import json
import math

import numpy as np

from .common import ROOT, get_json

IDENTIFY = "https://api3.geo.admin.ch/rest/services/api/MapServer/identify"
LAYERS = {"road": "ch.swisstopo.swisstlm3d-strassen", "rail": "ch.swisstopo.swisstlm3d-eisenbahnnetz"}
# Puffer um das Gebiet: Abschnitte zum nächsten Halt ausserhalb sollen auch geroutet werden
BUFFER_M = {"road": 2000, "rail": 6000}
# swissTLM3D Strassen objektart -> Kostenfaktor; Busse bevorzugen grosse Strassen. Wege (15–19) fehlen ganz.
ROAD_COST = {0: 1.0, 1: 1.0, 2: 1.0, 4: 1.0, 8: 1.0, 9: 1.0, 20: 1.0, 21: 1.0,
             10: 1.3, 3: 1.5, 12: 1.5, 11: 2.0, 5: 3.0, 6: 3.0, 7: 3.0}
NO_SNAP = {0, 1, 2, 21}  # Aus-/Einfahrt, Autobahn, Autostrasse: dort hält kein Bus
SNAP_M = 150
PAGE = 200


def _fetch(kind: str, bbox, cell: int = 1000) -> list[dict]:
    b = BUFFER_M[kind]
    e0, n0, e1, n1 = bbox[0] - b, bbox[1] - b, bbox[2] + b, bbox[3] + b
    lines: dict[int, dict] = {}
    for e in range(e0, e1, cell):
        for n in range(n0, n1, cell):
            g = f"{e},{n},{e + cell},{n + cell}"
            offset = 0
            while True:
                res = get_json(IDENTIFY, {
                    "geometryType": "esriGeometryEnvelope", "geometry": g, "mapExtent": g,
                    "imageDisplay": "500,500,96", "tolerance": 0, "layers": f"all:{LAYERS[kind]}", "sr": 2056,
                    "geometryFormat": "geojson", "returnGeometry": "true", "limit": PAGE, "offset": offset,
                })["results"]
                for f in res:
                    cost = ROAD_COST.get(f["properties"]["objektart"]) if kind == "road" else 1.0
                    if cost is None:
                        continue
                    geom = f["geometry"]
                    parts = geom["coordinates"] if geom["type"] == "MultiLineString" else [geom["coordinates"]]
                    snap = kind == "rail" or f["properties"]["objektart"] not in NO_SNAP
                    lines[f["id"]] = {"cost": cost, "snap": snap, "parts": [[p[:2] for p in part] for part in parts]}
                if len(res) < PAGE:
                    break
                offset += PAGE
    return list(lines.values())


def load_networks(cfg: dict, bbox) -> dict[str, list]:
    cache = ROOT / cfg["cache_dir"] / "network-v2.json"
    if cache.exists():
        return json.loads(cache.read_text())
    nets = {kind: _fetch(kind, bbox) for kind in LAYERS}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(nets))
    return nets


class Graph:
    """Ungerichteter Graph über die Stützpunkte der Linien; Knoten an gemeinsamen Koordinaten.

    shortcut: Einbahnstrassen und Abbiegeverbote werden ignoriert, reicht für die Darstellung.
    """

    def __init__(self, lines: list[dict]):
        ids: dict[tuple, int] = {}
        self.xy: list[tuple[float, float]] = []
        self.adj: list[list[tuple[int, float]]] = []
        seg_a, seg_b, seg_snap = [], [], []
        for line in lines:
            for part in line["parts"]:
                prev = None
                for x, y in part:
                    k = (round(x, 1), round(y, 1))
                    if k not in ids:
                        ids[k] = len(self.xy)
                        self.xy.append(k)
                        self.adj.append([])
                    i = ids[k]
                    if prev is not None and prev != i:
                        w = math.dist(self.xy[prev], self.xy[i]) * line["cost"]
                        self.adj[prev].append((i, w))
                        self.adj[i].append((prev, w))
                        seg_a.append(prev)
                        seg_b.append(i)
                        seg_snap.append(line["snap"])
                    prev = i
        arr = np.array(self.xy)
        keep = np.array(seg_snap)
        self.sa, self.sb = np.array(seg_a)[keep], np.array(seg_b)[keep]
        self.pa, self.pb = arr[self.sa], arr[self.sb]

    def snap(self, x: float, y: float) -> int | None:
        """Halt auf die nächste Kante projizieren und dort einen Knoten einfügen."""
        d = self.pb - self.pa
        t = np.clip(((x - self.pa[:, 0]) * d[:, 0] + (y - self.pa[:, 1]) * d[:, 1]) / (d ** 2).sum(1).clip(1e-9), 0, 1)
        proj = self.pa + d * t[:, None]
        dist = np.hypot(proj[:, 0] - x, proj[:, 1] - y)
        s = int(dist.argmin())
        if dist[s] > SNAP_M:
            return None
        a, b = int(self.sa[s]), int(self.sb[s])
        cost = next(w for v, w in self.adj[a] if v == b) / max(math.dist(self.xy[a], self.xy[b]), 1e-9)
        i = len(self.xy)
        self.xy.append(tuple(proj[s]))
        self.adj.append([(a, math.dist(self.xy[i], self.xy[a]) * cost), (b, math.dist(self.xy[i], self.xy[b]) * cost)])
        self.adj[a].append((i, self.adj[i][0][1]))
        self.adj[b].append((i, self.adj[i][1][1]))
        return i

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
        snap = {s: g.snap(stops[s][1], stops[s][2]) for s in {s for pair in pairs for s in pair}}
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
                    cand = [pa] + [[round(c, 1) for c in g.xy[i]] for i in nodes] + [pb]
                    length = sum(math.dist(p, q) for p, q in zip(cand, cand[1:]))
                    if length <= 3 * math.dist(pa, pb) + 300:
                        line, routed = cand, routed + 1
                result[f"{kind}:{a}-{b}"] = line
    print(f"  {routed} von {len(result)} Abschnitten auf Strasse/Gleis geführt")
    return result


def rail_lines(cfg: dict, bbox) -> list[list]:
    """Alle Gleise im Gebiet als Polylinien, für die Darstellung des Bahnnetzes."""
    e0, n0, e1, n1 = bbox
    out = []
    for line in load_networks(cfg, bbox)["rail"]:
        for part in line["parts"]:
            if any(e0 <= x < e1 and n0 <= y < n1 for x, y in part):
                out.append([[round(x, 1), round(y, 1)] for x, y in part])
    return out
