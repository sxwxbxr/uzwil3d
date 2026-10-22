# MVP-Fahrplan Uzwil3D

Ziel: ein im Browser testbarer Stand für Uzwil und Oberuzwil (inkl. Bichwil), **ausschliesslich mit echten Daten**. "Testbar" heisst: eine Vorschau-URL öffnen, durch das Gebiet fliegen, Gelände, Orthofoto und Gebäude sehen, einen ÖV-Layer einschalten.

## Muss im MVP sein

1. Terrain aus swissALTI3D (2 m), mit SWISSIMAGE als Textur
2. Gebäude aus swissBUILDINGS3D 3.0, als Kacheln geladen
3. Navigation (Orbit und Fly), Tag/Nacht-Schalter, Layer-Panel
4. ÖV-Layer: Haltestellen und Linien aus dem GTFS-Fahrplan, Fahrzeuge nach Fahrplan (Echtzeit kommt nach dem MVP)
5. Quellenangaben im UI (swisstopo, opentransportdata.swiss, OSM)
6. Öffentliche Vorschau-URL, Build und Deploy in CI

## Nicht im MVP

Echtzeit-Verspätungen, Wetter, Strassenverkehr, Bäume, Suche, geführte Tour, Mehrsprachigkeit, VR.

## Schritte (je ein PR)

| # | PR | Inhalt |
|---|---|---|
| 1 | Pipeline: Gebiet + Terrain + Orthofoto | Bounding Box aus swissBOUNDARIES3D, STAC-Download swissALTI3D und SWISSIMAGE, Zuschnitt, Ausgabe als Heightmap + Textur-Kacheln |
| 2 | Client: Terrain | Laden der Heightmap und Orthofoto-Kacheln, Kamera-Steuerung |
| 3 | Pipeline + Client: Gebäude | swissBUILDINGS3D-Kacheln laden, nach glTF konvertieren, im Client kachelweise laden |
| 4 | Vorschau-Deployment | GitHub Actions: Pipeline-Ausgabe + Build, Deploy auf Vorschau-URL |
| 5 | ÖV-Layer | GTFS-Import (Haltestellen, Linien, Fahrten im Gebiet), Fahrzeuge nach Fahrplan |
| 6 | MVP-Politur | Layer-Panel, Quellenangaben, Ladeanzeige, Performance-Check mobil |

## Echte Daten und Netzwerksperre

Der MVP verwendet keine Platzhalter- oder synthetischen Daten. Die Cloud-Umgebung von Claude erreicht die Datenquellen aktuell nicht. Drei Wege, von denen mindestens einer nötig ist:

- **A (empfohlen):** In der Cloud-Umgebung die Domains `data.geo.admin.ch`, `api3.geo.admin.ch`, `wmts.geo.admin.ch` und `api.opentransportdata.swiss` (bzw. `opentransportdata.swiss`) freigeben. Dann lädt und verarbeitet Claude die Daten direkt.
- **B:** Die Pipeline läuft in GitHub Actions (dort ist das Netz offen) und legt die Ergebnisse als Artefakt bzw. im Deployment ab.
- **C:** Seya führt `npm run pipeline` einmal lokal aus.

Die Pipeline-Skripte werden so geschrieben, dass sie in allen drei Fällen gleich laufen. Code, der Daten braucht, wird erst als fertig gemeldet, wenn er mit echten Daten geprüft ist.

## Offene Entscheidungen

- Hosting der Vorschau: GitHub Pages (kostenlos, einfach) oder Vercel/Cloudflare
- Ablage der aufbereiteten Daten: im Deployment (Build-Artefakt), Git LFS oder Bucket
