# Uzwil3D

3D-Live-Karte von Uzwil und Oberuzwil (inkl. Bichwil), inspiriert von [Geneva3D](https://geneva3d.ch).

Stack: Vite, TypeScript, Three.js. Datenaufbereitung (Terrain, Gebäude, Vegetation) läuft offline in `pipeline/`.

## Entwicklung

```sh
npm install
npm run dev
npm run build
```

## Struktur

- `src/` Browser-Client
- `pipeline/` Skripte für Download und Aufbereitung der Geodaten
- `data/` Rohdaten (nicht im Git)
- `public/` ausgelieferte Assets
- `docs/umsetzungsplan.md` Plan mit Phasen, Architektur und Datenquellen

## Datenquellen

swisstopo, opentransportdata.swiss, MeteoSchweiz, OpenStreetMap. Lizenzen und Quellenangaben siehe Plan.

## Wetter

Aktuelles Wetter kommt live von [Open-Meteo](https://open-meteo.com) (kein Key, alle 10 min). Himmel, Sonnenstand, Wolken, Sterne, Nebel, Regen und Schnee sind Shader; der Sonnenstand folgt der simulierten Uhr (Zeitraffer). Zum Testen überschreibt `?wetter=<WMO-Code>` (z. B. `63` Regen, `73` Schnee, `45` Nebel, `95` Gewitter) die Live-Daten.
