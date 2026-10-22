"""Uzwil3D-Datenpipeline: lädt echte swisstopo-Daten und schreibt statische Assets nach public/data."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from uzwil3d_pipeline.area import build_area  # noqa: E402
from uzwil3d_pipeline.buildings import build_buildings  # noqa: E402
from uzwil3d_pipeline.common import ROOT, load_config, write_json  # noqa: E402
from uzwil3d_pipeline.terrain import build_terrain  # noqa: E402
from uzwil3d_pipeline.transit import build_transit  # noqa: E402
from uzwil3d_pipeline.trees import build_trees  # noqa: E402


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

    print("Gebäude")
    buildings = build_buildings(cfg, area, terrain["height_min"], out)
    print("Bäume")
    trees = build_trees(cfg, area, terrain["height_min"], buildings["covered"], out)
    for t in terrain["tiles"]:
        t["buildings"] = buildings["tiles"].get((t["e"], t["n"]))
        t["trees"] = trees["tiles"].get((t["e"], t["n"]))

    print("ÖV-Fahrplan")
    transit = build_transit(cfg, area, out)

    write_json(
        out / "manifest.json",
        {
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "crs": "EPSG:2056",
            "bbox_lv95": area["bbox_lv95"],
            "origin_lv95": area["origin_lv95"],
            "area": "area.geojson",
            **terrain,
            "buildings_scale": buildings["scale"],
            "buildings_count": buildings["count"],
            "trees_count": trees["count"],
            **transit,
            "attribution": [f"swisstopo (swissBOUNDARIES3D, swissALTI3D, SWISSIMAGE, swissBUILDINGS3D 3.0 {buildings['year']}, swissSURFACE3D)", "Amtliche Vermessung, GWR", "opentransportdata.swiss (GTFS)"],
        },
    )


if __name__ == "__main__":
    main()
