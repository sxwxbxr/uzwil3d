"""Uzwil3D-Datenpipeline: lädt echte swisstopo-Daten und schreibt statische Assets nach public/data."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from uzwil3d_pipeline.area import build_area  # noqa: E402
from uzwil3d_pipeline.common import ROOT, load_config, write_json  # noqa: E402
from uzwil3d_pipeline.terrain import build_terrain  # noqa: E402


def main() -> None:
    cfg = load_config()
    out = ROOT / cfg["output_dir"]

    print("Gebiet")
    area = build_area(cfg)
    write_json(out / "area.geojson", area["geojson"])
    print(f"  Bounding Box LV95: {area['bbox_lv95']}")

    print("Terrain und Orthofoto")
    terrain = build_terrain(cfg, area, out)
    print(f"  {len(terrain['tiles'])} Kacheln, Höhe {terrain['height_min']:.1f}–{terrain['height_max']:.1f} m")

    write_json(
        out / "manifest.json",
        {
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "crs": "EPSG:2056",
            "bbox_lv95": area["bbox_lv95"],
            "origin_lv95": area["origin_lv95"],
            "area": "area.geojson",
            **terrain,
            "attribution": ["swisstopo (swissBOUNDARIES3D, swissALTI3D, SWISSIMAGE)"],
        },
    )


if __name__ == "__main__":
    main()
