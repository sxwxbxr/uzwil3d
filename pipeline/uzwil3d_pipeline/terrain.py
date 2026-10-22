"""swissALTI3D und SWISSIMAGE pro 1-km-Kachel aufbereiten.

Ausgabe pro Kachel:
- terrain/{E}_{N}.bin: Uint16 little-endian, (n+1)x(n+1) Höhen in cm über manifest.height_min, Zeile 0 = Norden
- ortho/{E}_{N}.jpg: Orthofoto, oben = Norden
"""

from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.merge import merge

from .common import ROOT, download
from .stac import latest_tiles


def _fetch(collection: str, bbox, gsd: float, cache: Path) -> dict[tuple[int, int], Path]:
    urls = latest_tiles(collection, bbox, gsd)
    print(f"  {collection}: {len(urls)} Kacheln")
    return {k: download(u, cache / collection / u.rsplit("/", 1)[-1]) for k, u in urls.items()}


def _bilinear(arr: np.ndarray, transform, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    inv = ~transform
    cols, rows = inv * (xs, ys)
    cols, rows = cols - 0.5, rows - 0.5  # Pixelzentren
    c0 = np.clip(np.floor(cols).astype(int), 0, arr.shape[1] - 2)
    r0 = np.clip(np.floor(rows).astype(int), 0, arr.shape[0] - 2)
    fc = np.clip(cols - c0, 0, 1)
    fr = np.clip(rows - r0, 0, 1)
    a = arr[r0, c0] * (1 - fc) + arr[r0, c0 + 1] * fc
    b = arr[r0 + 1, c0] * (1 - fc) + arr[r0 + 1, c0 + 1] * fc
    return a * (1 - fr) + b * fr


def build_terrain(cfg: dict, area: dict, out: Path) -> dict:
    bbox = area["bbox_lv95"]
    cache = ROOT / cfg["cache_dir"]
    ts, sp = cfg["tile_size_m"], cfg["terrain_spacing_m"]
    n = ts // sp

    dem_files = _fetch("ch.swisstopo.swissalti3d", bbox, 2.0, cache)
    if not dem_files:
        raise RuntimeError("Keine swissALTI3D-Kacheln gefunden")
    srcs = [rasterio.open(p) for p in dem_files.values()]
    mosaic, transform = merge(srcs, nodata=-9999)
    for s in srcs:
        s.close()
    dem = mosaic[0].astype(np.float64)
    valid = dem > -1000
    if not valid.all():
        dem[~valid] = np.nanmedian(np.where(valid, dem, np.nan))

    tiles = sorted(dem_files)
    grids = {}
    for ek, nk in tiles:
        e0, n0 = ek * 1000, nk * 1000
        xs = e0 + np.arange(n + 1) * sp
        ys = (n0 + ts) - np.arange(n + 1) * sp
        gx, gy = np.meshgrid(xs, ys)
        grids[(ek, nk)] = _bilinear(dem, transform, gx, gy)

    hmin = float(min(g.min() for g in grids.values()))
    hmax = float(max(g.max() for g in grids.values()))
    (out / "terrain").mkdir(parents=True, exist_ok=True)
    for (ek, nk), g in grids.items():
        cm = np.round((g - hmin) * 100).clip(0, 65535).astype("<u2")
        (out / "terrain" / f"{ek}_{nk}.bin").write_bytes(cm.tobytes())

    ortho_files = _fetch("ch.swisstopo.swissimage-dop10", bbox, cfg["ortho_gsd_m"], cache)
    (out / "ortho").mkdir(parents=True, exist_ok=True)
    for (ek, nk), path in ortho_files.items():
        with rasterio.open(path) as src:
            rgb = src.read([1, 2, 3])
        Image.fromarray(np.moveaxis(rgb, 0, -1)).save(out / "ortho" / f"{ek}_{nk}.jpg", quality=85)

    return {
        "tile_size_m": ts,
        "terrain_spacing_m": sp,
        "terrain_samples": n + 1,
        "height_min": hmin,
        "height_max": hmax,
        "tiles": [
            {"e": ek * 1000, "n": nk * 1000, "terrain": f"terrain/{ek}_{nk}.bin",
             "ortho": f"ortho/{ek}_{nk}.jpg" if (ek, nk) in ortho_files else None}
            for ek, nk in tiles
        ],
    }
