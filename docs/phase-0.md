# Phase 0: Gebiet und Datenverfügbarkeit

Stand: 22.10.2026. Geprüft über STAC-Metadaten (data.geo.admin.ch) und Wikipedia. Der Direktzugriff auf geo.admin.ch aus der Cloud-Umgebung ist gesperrt (Netzwerk-Policy), daher sind keine Daten geladen und keine Grenzen berechnet worden.

## Gebiet

- **Uzwil** (mit Niederuzwil, Henau u.a.) und **Oberuzwil**. **Bichwil ist ein Dorf der Gemeinde Oberuzwil** und damit bereits abgedeckt. Oberuzwil hat 1408 ha und rund 6'700 Einwohner (Wikipedia, Stand 2023).
- Die Bounding Box aus dem Plan (LV95 E 2'722'000–2'732'000, N 1'249'000–1'258'000) ist eine **Schätzung**. Sie muss mit den Gemeindegrenzen aus swissBOUNDARIES3D (+ ca. 1 km Puffer) berechnet werden. Das braucht Netzzugriff auf data.geo.admin.ch.

## Verfügbarkeit

| Datensatz | Abdeckung für Uzwil | Auflösung / Zeit | Lizenzfeld im STAC |
|---|---|---|---|
| swissBUILDINGS3D 3.0 (Beta) | ja (Bbox lon 5.2–11.3, lat 45.3–48.2) | Daten 2013–2026, letzte Aktualisierung 4.6.2026 | "Proprietary" |
| swissALTI3D | ja | 0.5 m und 2 m, Daten 2019–2026 | "Proprietary" |
| SWISSIMAGE 10 cm | ja | 10 cm im Flachland, Daten 2017–2025 | "Proprietary" |

Hinweise:
- Die STAC-Collections listen keine Asset-Formate. Die konkreten Dateien (Kachelliste je Gemeinde) müssen über die Items abgefragt werden.
- Das Feld "Proprietary" ist bei swisstopo generisch. Die Nutzungsbedingungen (OGD, Namensnennung "Quelle: swisstopo") sind vor dem Launch auf swisstopo.admin.ch zu bestätigen. Das wurde hier noch nicht geprüft.
- swissBUILDINGS3D 3.0 ist weiter als Beta geführt. Daten und Schema können sich ändern. Pipeline muss das Format kapseln.

## Noch nicht geprüft

- Nutzungsbedingungen der swisstopo-Daten und von opentransportdata.swiss (API-Key, Rate-Limits).
- Abdeckung von GTFS-Realtime für die lokalen Buslinien.
- Verfügbarkeit von uzwil3d.ch.
- Kantonsdaten SG (geodienste.ch).

## Nächste Schritte

1. Netzwerkfreigabe für `data.geo.admin.ch`, `api3.geo.admin.ch`, `wms.geo.admin.ch` und `api.opentransportdata.swiss` in der Cloud-Umgebung, sonst läuft die Pipeline nur lokal.
2. Bounding Box aus swissBOUNDARIES3D ableiten und in `pipeline/config.json` festhalten.
3. Pipeline-Skelett: Kachelliste via STAC, Download, Zuschnitt (Phase 1).
