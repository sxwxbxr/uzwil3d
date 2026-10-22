import * as THREE from "three";
import { toScene, type Manifest, type Terrain } from "./terrain";

interface Transit {
  start_date: string;
  days: number;
  stops: [string, number, number][];
  routes: [string, number][];
  trips: [number, string, number, [number, number, number][]][];
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

  // Linien als gerade Verbindung aufeinanderfolgender Halte.
  // shortcut: GTFS der Schweiz hat keine shapes.txt, Strecken folgen nicht Strasse/Gleis; später mit swissTLM3D ersetzen.
  const segments = { rail: new Set<string>(), bus: new Set<string>() };
  for (const [route, , , stops] of t.trips) {
    const set = isRail(t.routes[route][1]) ? segments.rail : segments.bus;
    for (let i = 1; i < stops.length; i++) set.add(`${stops[i - 1][0]}-${stops[i][0]}`);
  }
  for (const [kind, color] of [["rail", 0xd32f2f], ["bus", 0xffb300]] as const) {
    const pts: THREE.Vector3[] = [];
    for (const s of segments[kind]) {
      const [a, b] = s.split("-").map(Number);
      pts.push(stopPos[a], stopPos[b]);
    }
    group.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color })));
  }

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
    const sec = (now.getTime() - midnight) / 1000;
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
        pos.lerpVectors(stopPos[a], stopPos[b], f);
        if (stopPos[a].distanceToSquared(stopPos[b]) > 1) {
          lookM.lookAt(stopPos[b], stopPos[a], up);
          quat.setFromRotationMatrix(lookM);
        }
        const rail = isRail(t.routes[route][1]);
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
