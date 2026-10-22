import * as THREE from "three";
import { MapControls } from "three/examples/jsm/controls/MapControls.js";
import { loadBuildings } from "./buildings";
import { Terrain, toScene, type Manifest } from "./terrain";
import { loadTransit } from "./transit";
import { loadTrees } from "./trees";
import { Weather } from "./weather";

const DATA_URL = import.meta.env.BASE_URL + "data/";

const renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: true });
// Auf Touch-Geräten weniger Pixel rendern, sonst wird es mit Bäumen und Gebäuden zäh.
renderer.setPixelRatio(Math.min(window.devicePixelRatio, matchMedia("(pointer: coarse)").matches ? 1.25 : 2));
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();

const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 1, 40000);
camera.position.set(-1500, 3500, 6500);

const sky = new THREE.HemisphereLight(0xffffff, 0x556655, 1.6);
scene.add(sky);
const sun = new THREE.DirectionalLight(0xfff4e0, 1.6);
sun.position.set(-3000, 5000, 2000);
scene.add(sun);

const controls = new MapControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI * 0.47;
controls.minDistance = 50;
controls.maxDistance = 15000;
controls.target.set(0, 150, 0);

// Optionale Startansicht per URL: ?cam=x,y,z,zielX,zielY,zielZ (Szenen-Meter)
const params = new URLSearchParams(location.search);
const cam = params.get("cam")?.split(",").map(Number);
if (cam?.length === 6 && cam.every(Number.isFinite)) {
  camera.position.set(cam[0], cam[1], cam[2]);
  controls.target.set(cam[3], cam[4], cam[5]);
}

const wParam = params.get("wetter");
const weather = new Weather(scene, sun, sky, camera, wParam === null ? undefined : Number(wParam));

const status = document.getElementById("status")!;

async function init() {
  const manifest: Manifest = await fetch(DATA_URL + "manifest.json").then((r) => {
    if (!r.ok) throw new Error(`manifest.json: HTTP ${r.status}`);
    return r.json();
  });
  document.getElementById("attribution")!.textContent = "© " + [...manifest.attribution, "Open-Meteo.com (Wetter)"].join(", ");

  const terrain = new Terrain(manifest, DATA_URL);
  scene.add(terrain.group);
  await terrain.load((done, total) => {
    status.textContent = `Gelände wird geladen … ${done}/${total}`;
  });

  const area = await fetch(DATA_URL + manifest.area).then((r) => r.json());
  const boundaries = boundaryLines(area, manifest, terrain);
  scene.add(boundaries);

  status.textContent = `Gebäude werden geladen … (${manifest.buildings_count.toLocaleString("de-CH")})`;
  const buildings = await loadBuildings(manifest, DATA_URL);
  scene.add(buildings);

  status.textContent = "Bäume werden geladen …";
  const trees = await loadTrees(manifest, DATA_URL);
  scene.add(trees);

  status.textContent = "Fahrplan wird geladen …";
  const transit = await loadTransit(manifest, terrain, DATA_URL + manifest.transit);
  scene.add(transit.group);
  status.hidden = true;

  const layers: Record<string, THREE.Object3D> = { buildings, trees, transit: transit.group, boundaries };
  for (const box of document.querySelectorAll<HTMLInputElement>("#panel input[data-layer]")) {
    box.addEventListener("change", () => (layers[box.dataset.layer!].visible = box.checked));
  }

  // Simulierte Uhr: Startzeit per ?t=HH:MM (heute), sonst jetzt; Zeitraffer über die Knöpfe.
  const clock = document.getElementById("clock")!;
  const [hh, mm] = (params.get("t") ?? "").split(":").map(Number);
  let sim = Number.isFinite(hh) && Number.isFinite(mm) ? new Date().setHours(hh, mm, 0, 0) : Date.now();
  let speed = 1;
  let last = performance.now();
  for (const btn of document.querySelectorAll<HTMLButtonElement>("#panel button[data-speed]")) {
    btn.addEventListener("click", () => {
      speed = Number(btn.dataset.speed);
      document.querySelectorAll("#panel button[data-speed]").forEach((b) => b.classList.toggle("on", b === btn));
    });
  }
  const tick = () => {
    const t = performance.now();
    sim += (t - last) * speed;
    last = t;
    const now = new Date(sim);
    const n = transit.update(now);
    simNow = now;
    clock.textContent = `${now.toLocaleTimeString("de-CH", { hour: "2-digit", minute: "2-digit" })} · ${n} Fahrzeuge unterwegs`;
  };
  tick();
  setInterval(tick, 100);


  // Kamera nicht unter das Gelände fallen lassen.
  controls.addEventListener("change", () => {
    const e = camera.position.x + manifest.origin_lv95[0];
    const n = -camera.position.z + manifest.origin_lv95[1];
    const h = terrain.heightAt(e, n);
    if (h !== undefined && camera.position.y < h + 20) camera.position.y = h + 20;
  });
}

interface GeoJSON {
  features: { properties: { name: string }; geometry: { type: string; coordinates: number[][][][] } }[];
}

function boundaryLines(area: GeoJSON, m: Manifest, terrain: Terrain): THREE.Group {
  const group = new THREE.Group();
  const material = new THREE.LineBasicMaterial({ color: 0xffffff, depthTest: false, transparent: true, opacity: 0.9 });
  for (const f of area.features) {
    const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates as unknown as number[][][]] : f.geometry.coordinates;
    for (const poly of polys) {
      for (const ring of poly) {
        const pts = ring.map(([e, n]) => {
          const [x, z] = toScene(m, e, n);
          return new THREE.Vector3(x, (terrain.heightAt(e, n) ?? 0) + 3, z);
        });
        group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), material));
      }
    }
  }
  group.renderOrder = 1;
  return group;
}

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

const nightBox = document.getElementById("night") as HTMLInputElement;
let simNow = new Date();
let lastFrame = performance.now();
renderer.setAnimationLoop((t) => {
  controls.update();
  weather.update(simNow, nightBox.checked, Math.min((t - lastFrame) / 1000, 0.5));
  lastFrame = t;
  renderer.render(scene, camera);
});

init().catch((err) => {
  console.error(err);
  status.textContent = "Daten konnten nicht geladen werden: " + err.message;
});
