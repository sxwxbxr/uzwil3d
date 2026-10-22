"""Bäume aus dem Oberflächenmodell swissSURFACE3D Raster minus Geländemodell swissALTI3D.

Pro 1-km-Kachel trees/{E}_{N}.bin: Int16 LE (x, z, Fuss, Höhe) pro Baum in dm,
x = Ost und z = Süd relativ zur Kachelmitte, Fuss = Höhe über height_min.
Ein Baum = höchster Punkt der Vegetation (> MIN_HEIGHT_M, kein Gebäude) in einer GRID_M-Zelle.
"""

from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling

from .common import ROOT, download
from .stac import latest_tiles

MIN_HEIGHT_M = 3.0
MAX_HEIGHT_M = 50.0
GRID_M = 8


def _cached(collection: str, bbox, gsd: float, cache: Path) -> dict:
    urls = latest_tiles(collection, bbox, gsd)
    return {k: download(u, cache / collection / u.rsplit("/", 1)[-1]) for k, u in urls.items()}


def build_trees(cfg: dict, area: dict, height_min: float, covered: np.ndarray, out: Path) -> dict:
    bbox = area["bbox_lv95"]
    e0, n0 = bbox[0], bbox[1]
    ts = cfg["tile_size_m"]
    cache = ROOT / cfg["cache_dir"]
    dsm = _cached("ch.swisstopo.swisssurface3d-raster", bbox, 0.5, cache)
    dtm = _cached("ch.swisstopo.swissalti3d", bbox, 2.0, cache)
    print(f"  swissSURFACE3D: {len(dsm)} Kacheln, swissALTI3D: {len(dtm)} Kacheln")

    (out / "trees").mkdir(parents=True, exist_ok=True)
    tiles, total = {}, 0
    n = ts // GRID_M
    for (ek, nk), path in sorted(dsm.items()):
        if (ek, nk) not in dtm:
            continue
        size = ts  # auf 1 m zusammenfassen: Oberfläche als Maximum, Gelände (2 m) bilinear
        with rasterio.open(path) as src:
            full = src.read(1).astype(np.float32)
        f = full.shape[0] // size
        top = full[: size * f, : size * f].reshape(size, f, size, f).max(axis=(1, 3))
        with rasterio.open(dtm[(ek, nk)]) as src:
            ground = src.read(1, out_shape=(size, size), resampling=Resampling.bilinear).astype(np.float32)
        veg = top - ground  # Zeile 0 = Norden

        r0 = nk * ts - n0  # Südkante der Kachel im covered-Raster
        c0 = ek * ts - e0
        bld = covered[r0:r0 + ts, c0:c0 + ts][::-1] if 0 <= r0 and 0 <= c0 else np.zeros_like(veg, bool)
        if bld.shape != veg.shape:
            bld = np.zeros_like(veg, bool)
        # Gebäuderand um 2 m erweitern, Dachkanten sind sonst "Bäume"
        pad = np.pad(bld, 2)
        bld = np.max([pad[2 + dy:2 + dy + ts, 2 + dx:2 + dx + ts] for dy in range(-2, 3) for dx in range(-2, 3)], axis=0)
        veg[bld | (veg < MIN_HEIGHT_M) | (veg > MAX_HEIGHT_M) | ~np.isfinite(veg)] = 0

        cells = veg.reshape(n, GRID_M, n, GRID_M).transpose(0, 2, 1, 3).reshape(n, n, -1)
        best = cells.argmax(axis=2)
        h = np.take_along_axis(cells, best[..., None], axis=2)[..., 0]
        rows, cols = np.nonzero(h > 0)
        if not len(rows):
            continue
        k = best[rows, cols]
        py = rows * GRID_M + k // GRID_M
        px = cols * GRID_M + k % GRID_M
        x = px + 0.5 - ts / 2
        z = py + 0.5 - ts / 2
        base = ground[py, px] - height_min
        data = np.round(np.stack([x, z, base, h[rows, cols]], axis=1) * 10).astype("<i2")
        name = f"trees/{ek}_{nk}.bin"
        (out / name).write_bytes(data.tobytes())
        tiles[(ek * ts, nk * ts)] = name
        total += len(data)

    print(f"  {total} Bäume")
    return {"tiles": tiles, "count": total}
