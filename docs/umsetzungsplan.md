# Uzwil3D – Umsetzungsplan

Ziel: Geneva3D (geneva3d.ch) für Uzwil, Oberuzwil und Bichwil (SG) nachbauen. Stand: 22.10.2026. Nur Planung, noch kein Code.

## 1. Was Geneva3D ist (Analyse)

- Einzelentwickler Arnaud Ricci, Start Juli 2026, gebaut mit bis zu 15 KI-Agenten (Claude). Läuft komplett im Browser mit **Three.js**, Rendering auf dem Gerät des Nutzers, kostenlos.
- Umfang Genf: ca. 90'000 Gebäude, 239'000 Bäume, Relief, 121 Open-Data-Layer.
- Features: freie Navigation (Maus/WASD/Touch/VR), Zeitsteuerung (x1–x480, 24h-Timeline), Tag/Nacht, Wetter-Effekte, Jahreszeiten, Strassenlaternen, ÖV-Fahrzeuge live (Tram/Bus/Zug/Boot) mit Follow-Modus, simulierter Strassenverkehr aus Zählstellen, Flugzeuge, Gewässer (Temperatur/Abfluss), Naturgefahren/Erdbeben, Events, Adresssuche, geführte Tour, Layer-Schalter, Qualitätsstufen, mehrere Sprachen.
- Live-Daten: GTFS + GTFS-RT (opentransportdata.swiss), ASTRA-Verkehrszählung, OpenSky (Flugzeuge), MeteoSchweiz, BAFU (Hydrologie), SED/ETH (Erdbeben), OSM, Terrain Tiles, swisstopo.
- Ehrlich: Fahrzeugpositionen sind teils berechnet (Fahrplan + Verspätung), Strassenverkehr ist Simulation, nicht echte Fahrzeuge.

## 2. Zielgebiet

Gemeinden Uzwil, Oberuzwil, Bichwil (Wil-Toggenburg-Region, Kt. SG), ca. 12–15 km². Grob LV95: E 2'722'000–2'732'000, N 1'249'000–1'258'000 (mit ~1 km Puffer, genaue BBox in Phase 0 aus swissBOUNDARIES3D ableiten). Etwa 1/20 bis 1/30 der Datenmenge von Genf: **kein Server-Tiling nötig, alles statisch auslieferbar.**

## 3. Datenquellen (alle Open Government Data, Quellen vor Nutzung verifizieren)

| Zweck | Quelle | Bemerkung |
|---|---|---|
| Gebäude 3D | swisstopo **swissBUILDINGS3D 3.0** (LoD2, CityGML/FileGDB/glTF via STAC `data.geo.admin.ch`) | Dachformen vorhanden; Alternative: Kanton SG Gebäude + Höhen aus swissSURFACE3D |
| Terrain | **swissALTI3D** (0.5/2 m GeoTIFF) | auf Mesh/Heightmap reduzieren |
| Luftbild/Textur | **SWISSIMAGE** (10 cm, WMTS) | Boden-Textur; Gebäudefassaden später optional |
| Vegetation | swissSURFACE3D / Vegetationshöhe + swissTLM3D Wald; OSM Einzelbäume | Bäume aus Höhenmodell ableiten und instanziieren |
| Strassen, Gleise, Gewässer | **swissTLM3D** und/oder OSM | Linien auf Terrain drapieren |
| Gemeindegrenzen/Namen | swissBOUNDARIES3D | |
| Strassenlaternen | OSM `highway=street_lamp`, sonst prozedural | |
| ÖV Fahrplan + Live | **opentransportdata.swiss**: GTFS Static, GTFS-RT (Trip Updates, Alerts); API-Key nötig (gratis Registrierung) | Linien in Uzwil: SBB-Bahnhof Uzwil (Fürstenland-/Wil–St.Gallen-Strecke), Busse Uzwil/Oberuzwil/Flawil |
| Wetter | MeteoSchweiz Open Data (Stationen Umgebung), ergänzend Open-Meteo | |
| Gewässer | BAFU Hydrodaten (Uze/Glatt/Thur nahe) | |
| Verkehr | ASTRA-Zählstellen (falls in der Nähe), sonst OSM-Strassenklassen + Tagesgang-Simulation | |
| Sonne/Sterne | SunCalc o.ä., optional Sternkatalog | |
| Kanton SG Geodaten | geodienste.ch / geoportal.sg.ch (Bauzonen, Denkmäler, Solarkataster etc.) | Lizenz je Layer prüfen |

Offene Datenfrage: swissBUILDINGS3D 3.0 ist laut opendata.swiss teils noch "Beta"; Abdeckung/Version für Region SG in Phase 0 prüfen.

## 4. Architektur

- **Frontend:** Vite + TypeScript + Three.js, ggf. React nur fürs UI-Panel (Layer, Zeitleiste, Suche). Instanced Meshes für Bäume/Fahrzeuge, Chunking der Gebäude in Kacheln, LOD, Qualitätsstufen.
- **Offline-Build-Pipeline** (Python/GDAL/Node, im Repo): Rohdaten laden → zuschneiden auf BBox → Terrain-Heightmap, Gebäude als gebündelte glTF/Binär-Kacheln, Vegetation, Linien-Layer als GeoJSON/FlatGeobuf → statische Assets.
- **Live-Backend (klein):** Serverless Proxy (z.B. Vercel/Cloudflare Worker), da GTFS-RT einen API-Key braucht und CORS/Rate-Limits (Polling alle ~30 s, gecacht). Liefert normalisiertes JSON für Fahrzeug-Positionen; Wetter/Hydro ebenfalls gecacht.
- **Hosting:** statisch (Vercel/Cloudflare Pages/GitHub Pages) + Proxy; Kosten voraussichtlich ~0 CHF. Domain z.B. uzwil3d.ch (Verfügbarkeit prüfen).
- **ÖV-Simulation:** GTFS Static (Shapes, Stop Times) → Fahrzeugposition entlang Shape interpoliert, korrigiert mit GTFS-RT-Verspätung; Fallback Fahrplan.

## 5. Phasen

**Phase 0 – Grundlagen (1–2 Tage):** Repo anlegen, BBox festlegen, Daten-Verfügbarkeit/Lizenzen prüfen, API-Key opentransportdata.swiss beantragen, Domain klären.
**Phase 1 – Statische Welt (1 Woche):** Terrain + SWISSIMAGE, Gebäude LoD2, Strassen/Gleise/Gewässer, Navigation (Orbit + Fly), Tag/Nacht. Pipeline reproduzierbar per Skript.
**Phase 2 – Details (1 Woche):** Bäume/Wald, Laternen, Gemeindegrenzen/Beschriftung, Adresssuche (geo.admin.ch Search API), Qualitätsstufen, Mobile-Performance.
**Phase 3 – Live-ÖV (1 Woche):** GTFS-Import, Haltestellen/Linien, Fahrzeuge animiert, Echtzeit-Verspätungen, Follow-Modus, Zeitraffer.
**Phase 4 – Umwelt & Verkehr (1 Woche):** Wetter live + Effekte, Jahreszeiten, Hydrologie, simulierter Strassenverkehr, Störungsmeldungen.
**Phase 5 – Politur & Launch (3–5 Tage):** geführte Tour, Mehrsprachigkeit (DE/EN), Quellenangaben/Impressum/Datenschutz, Tests, Deployment, Analytics (datensparsam).
**Optional später:** historische Ansicht (Uzwil früher), Solarkataster, Events (Gemeinde), VR, Fassadentexturen.

Grobe Dauer mit KI-Unterstützung: 4–6 Wochen Teilzeit bis zur ersten öffentlichen Version.

## 6. Risiken

- Gebäudedaten-Format/Grösse (CityGML schwer) → früh Konvertierungspipeline testen.
- Performance auf Mobile → Kachel-LOD, Instancing, Qualitätsstufen.
- GTFS-RT-Abdeckung für lokale Busse teils lückenhaft → Fahrplan-Fallback, klar kennzeichnen.
- Lizenzen/Namensnennung je Datensatz (swisstopo OGD, ODbL bei OSM).
- Visuelle Qualität schwer automatisch prüfbar → Screenshot-basierte Review-Schleife (wie bei Geneva3D).

## 7. Offene Entscheidungen (für Seya)

1. **Eigenständiges Projekt vs. Fork/Code-Nutzung:** Geneva3D ist nicht als Open Source ausgewiesen (© Arnaud Ricci) → Plan geht von komplettem Eigenbau aus. Optional Kontakt aufnehmen.
2. **Stack:** Three.js (wie Original) vs. CesiumJS/MapLibre-3D. Empfehlung: Three.js.
3. **Umfang v1:** nur Statik + Live-ÖV, oder gleich Wetter/Verkehr? Empfehlung: Phasen 1–3 als v1.
4. **Gebäude:** swissBUILDINGS3D (präzise, Datenhandling aufwendig) vs. OSM/Kantonsdaten + Extrusion (einfacher). Empfehlung: erst swissBUILDINGS3D prüfen.
5. **Hosting/Domain und Name** (uzwil3d.ch?), Repo-Ort (GitHub-Konto sxwxbxr?).
6. **Sprachen:** DE nur oder DE/EN.
7. **Gebiet:** exakt die 3 Gemeinden oder mit Puffer/Nachbargemeinden (Flawil, Niederuzwil ist Teil von Uzwil).

## Quellen
- geneva3d.ch; Digitec-Artikel zu Geneva 3D
- opendata.swiss: swissBUILDINGS3D 3.0 Beta, GTFS Realtime (opentransportdata.swiss)
