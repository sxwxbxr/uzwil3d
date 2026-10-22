# Daten-Pipeline

Lädt echte Geodaten von swisstopo und schreibt statische Assets nach `public/data/`.

```sh
pip install -r pipeline/requirements.txt
python pipeline/run.py
```

Schritte:
1. Gemeindegrenzen (swissBOUNDARIES3D) für die Gemeinden in `config.json`, daraus die Bounding Box (mit Puffer, auf 1 km gerundet)
2. swissALTI3D (2 m) pro 1-km-Kachel, Höhenraster mit `terrain_spacing_m` Abstand
3. SWISSIMAGE (2 m) pro 1-km-Kachel als JPEG
4. swissBUILDINGS3D 3.0 (CityGML, LoD2, neuester Jahrgang pro LK25-Blatt) als Dreiecke pro 1-km-Kachel, Format in `buildings.py`
5. ÖV-Fahrplan (GTFS von opentransportdata.swiss, ohne API-Key): Haltepunkte im Gebiet und Fahrten der nächsten 28 Tage als `transit.json`

Selbstcheck: `python -I pipeline/test_buildings.py`

Rohdaten werden in `data/raw/` zwischengespeichert. In CI läuft die Pipeline über `.github/workflows/pipeline.yml` und legt das Ergebnis als Artefakt `uzwil3d-data` ab.

## Ausgabeformat

`manifest.json` beschreibt Gebiet, Ursprung (LV95) und Kacheln. Terrain-Kacheln sind Uint16 little-endian, `terrain_samples`² Werte, Höhe in cm über `height_min`, Zeile 0 im Norden.
