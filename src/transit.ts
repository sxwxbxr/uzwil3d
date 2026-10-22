import * as THREE from "three";
import { toScene, type Manifest, type Terrain } from "./terrain";

interface Transit {
  start_date: string;
  days: number;
  stops: [string, number, number][];
  routes: [string, number][];
  trips: [number, string, number, [number, number, number][]][];
  paths: Record<string, [number, number][]>;
}

interface Path {
  pts: THREE.Vector3[];
  /** kumulierte Länge bis pts[i] */
  len: number[];
}

const DAY = 86400;
const MAX_VEHICLES = 1000;
// GTFS route_type: 2 und 100–199 Bahn, sonst Bus
const isRail = (type: number) => type === 2 || (type >= 100 && type < 200);

export async function loadTransit(m: Manifest, terrain: Terrain, url: string) {
  const t: Transit = await fetch(url).then((r) => r.json());
  const group = new THREE.Group();

  const stopPos = t.stops.map(([, e, n]) => {
    const [x, z] = toScene(m, e, n);
    return new THREE.Vector3(x, (terrain.heightAt(e, n) ?? 0) + 2, z);
  });

  const stopMesh = new THREE.InstancedMesh(
    new THREE.CylinderGeometry(4, 4, 6, 12),
    new THREE.MeshLambertMaterial({ color: 0x1565c0 }),
    stopPos.length,
  );
  const mat = new THREE.Matrix4();
  stopPos.forEach((p, i) => stopMesh.setMatrixAt(i, mat.makeTranslation(p.x, p.y + 3, p.z)));
  group.add(stopMesh);

  // Abschnitte zwischen zwei Halten folgen Strasse bzw. Gleis (swissTLM3D, in der Pipeline geroutet).
  const paths = new Map<string, Path>();
  const lines = { rail: [] as THREE.Vector3[], bus: [] as THREE.Vector3[] };
  for (const [key, coords] of Object.entries(t.paths)) {
    const pts = coords.map(([e, n]) => {
      const [x, z] = toScene(m, e, n);
      return new THREE.Vector3(x, (terrain.heightAt(e, n) ?? 0) + 1.5, z);
    });
    const len = [0];
    for (let i = 1; i < pts.length; i++) len.push(len[i - 1] + pts[i].distanceTo(pts[i - 1]));
    paths.set(key, { pts, len });
    const out = lines[key.startsWith("rail") ? "rail" : "bus"];
    for (let i = 1; i < pts.length; i++) out.push(pts[i - 1], pts[i]);
  }
  for (const [kind, color] of [["rail", 0xd32f2f], ["bus", 0xffb300]] as const) {
    group.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(lines[kind]), new THREE.LineBasicMaterial({ color })));
  }

  /** Punkt und Fahrtrichtung bei Anteil f eines Abschnitts. */
  const along = (p: Path, f: number, out: THREE.Vector3): [THREE.Vector3, THREE.Vector3] => {
    const d = f * p.len[p.len.length - 1];
    let i = 1;
    while (i < p.pts.length - 1 && p.len[i] < d) i++;
    const a = p.pts[i - 1];
    const b = p.pts[i];
    const seg = p.len[i] - p.len[i - 1];
    out.lerpVectors(a, b, seg > 0 ? (d - p.len[i - 1]) / seg : 0);
    return [a, b];
  };

  const vehicles = new THREE.InstancedMesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshLambertMaterial(),
    MAX_VEHICLES,
  );
  vehicles.count = 0;
  group.add(vehicles);

  const startMs = new Date(t.start_date + "T00:00:00").getTime();
  const railColor = new THREE.Color(0xd32f2f);
  const busColor = new THREE.Color(0xffb300);
  const pos = new THREE.Vector3();
  const quat = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  const up = new THREE.Vector3(0, 1, 0);
  const lookM = new THREE.Matrix4();

  /** Fahrzeuge für einen Zeitpunkt setzen, liefert die Anzahl aktiver Fahrten. */
  function update(now: Date): number {
    const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    // GTFS-Zeiten sind lokale Uhrzeit, auch an Tagen mit Zeitumstellung.
    const sec = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds() + now.getMilliseconds() / 1000;
    // Ausserhalb des Datenfensters gleichen Wochentag im Fenster verwenden.
    let day = Math.round((midnight - startMs) / (DAY * 1000));
    if (day < 0 || day >= t.days) day = ((day % 7) + 7) % 7;
    let n = 0;
    for (const [route, , mask, stops] of t.trips) {
      // Fahrten des Vortags laufen mit Zeiten über 24:00 weiter.
      for (const [d, s] of [[day, sec], [day - 1, sec + DAY]]) {
        if (d < 0 || !(mask & (1 << d)) || s < stops[0][2] || s > stops[stops.length - 1][1]) continue;
        let i = 1;
        while (stops[i][1] < s) i++;
        const [a, , depA] = stops[i - 1];
        const [b, arrB] = stops[i];
        const f = arrB > depA ? Math.min(1, Math.max(0, (s - depA) / (arrB - depA))) : 1;
        const rail = isRail(t.routes[route][1]);
        const path = paths.get(`${rail ? "rail" : "bus"}:${a}-${b}`);
        const [from, to] = path ? along(path, f, pos) : [stopPos[a], stopPos[b]];
        if (!path) pos.lerpVectors(from, to, f);
        if (from.distanceToSquared(to) > 0.01) {
          lookM.lookAt(to, from, up);
          quat.setFromRotationMatrix(lookM);
        }
        scale.set(rail ? 4 : 3, rail ? 4.5 : 3.5, rail ? 75 : 12);
        pos.y += scale.y / 2 + 1;
        if (n < MAX_VEHICLES) {
          vehicles.setMatrixAt(n, mat.compose(pos, quat, scale));
          vehicles.setColorAt(n, rail ? railColor : busColor);
          n++;
        }
      }
    }
    vehicles.count = n;
    vehicles.instanceMatrix.needsUpdate = true;
    if (vehicles.instanceColor) vehicles.instanceColor.needsUpdate = true;
    return n;
  }

  return { group, update, stopCount: t.stops.length };
}
