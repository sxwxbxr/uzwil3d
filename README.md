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
