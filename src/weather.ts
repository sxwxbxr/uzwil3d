import * as THREE from "three";

// Uzwil, Zentrum
const LAT = 47.4386;
const LON = 9.1349;
const API =
  `https://api.open-meteo.com/v1/forecast?latitude=${LAT}&longitude=${LON}` +
  "&current=temperature_2m,precipitation,snowfall,weather_code,cloud_cover,wind_speed_10m,wind_direction_10m&timezone=Europe%2FZurich";

interface Current {
  temperature_2m: number;
  precipitation: number;
  snowfall: number;
  weather_code: number;
  cloud_cover: number;
  wind_speed_10m: number;
  wind_direction_10m: number;
}

const SNOW = new Set([71, 73, 75, 77, 85, 86]);
const RAIN = new Set([51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99]);
// WMO-Code: erster Eintrag, dessen Obergrenze den Code abdeckt
const LABEL: [number, string][] = [
  [1, "klar"], [2, "teils bewölkt"], [3, "bedeckt"], [48, "Nebel"], [57, "Nieselregen"],
  [67, "Regen"], [77, "Schnee"], [82, "Regenschauer"], [86, "Schneeschauer"], [99, "Gewitter"],
];

/** Sonnenrichtung (Szenen-Koordinaten: x Ost, y oben, -z Nord) und Höhe über dem Horizont, NOAA-Näherung. */
export function sunPosition(date: Date): { dir: THREE.Vector3; elevation: number } {
  const rad = Math.PI / 180;
  const d = date.getTime() / 86400000 + 2440587.5 - 2451545.0;
  const g = (357.528 + 0.9856003 * d) * rad;
  const lam = (280.46 + 0.9856474 * d + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * rad;
  const eps = 23.439 * rad;
  const dec = Math.asin(Math.sin(eps) * Math.sin(lam));
  const ra = Math.atan2(Math.cos(eps) * Math.sin(lam), Math.cos(lam));
  const h = (280.46061837 + 360.98564736629 * d + LON) * rad - ra;
  const lat = LAT * rad;
  const elevation = Math.asin(Math.sin(lat) * Math.sin(dec) + Math.cos(lat) * Math.cos(dec) * Math.cos(h));
  const az = Math.atan2(Math.sin(h), Math.cos(h) * Math.sin(lat) - Math.tan(dec) * Math.cos(lat)) + Math.PI; // ab Nord, im Uhrzeigersinn
  const c = Math.cos(elevation);
  return { dir: new THREE.Vector3(Math.sin(az) * c, Math.sin(elevation), -Math.cos(az) * c), elevation };
}

const NOISE = /* glsl */ `
// Hash ohne sin(): bleibt auch bei grossen Argumenten (lange Laufzeit, Mobil-GPUs) stabil
float hash(vec2 p) {
  vec3 q = fract(vec3(p.xyx) * 0.1031);
  q += dot(q, q.yzx + 33.33);
  return fract((q.x + q.y) * q.z);
}
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}
float fbm(vec2 p) {
  float s = 0.0, a = 0.5;
  for (int i = 0; i < 5; i++) { s += a * noise(p); p = p * 2.03 + 11.7; a *= 0.5; }
  return s;
}`;

const SKY_VERT = /* glsl */ `
varying vec3 vDir;
void main() {
  vDir = position;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const SKY_FRAG = /* glsl */ `
uniform vec3 uSun, uZenith, uHorizon, uCloud;
uniform float uCover, uNight, uSunVis, uTime;
uniform vec2 uWind;
varying vec3 vDir;
${NOISE}
void main() {
  vec3 d = normalize(vDir);
  float h = max(d.y, 0.0);
  vec3 col = mix(uHorizon, uZenith, pow(h, 0.45));

  float sd = max(dot(d, uSun), 0.0);
  col += vec3(1.0, 0.85, 0.6) * (pow(sd, 48.0) * 0.5 + pow(sd, 6.0) * 0.12) * uSunVis;
  col += vec3(1.0, 0.95, 0.85) * smoothstep(0.9996, 0.9999, sd) * 2.0 * uSunVis;

  // Sterne: nur bei klarer Nacht
  vec2 sp = d.xz / (d.y + 1.2) * 400.0;
  float star = step(0.995, hash(floor(sp))) * smoothstep(0.0, 0.1, d.y);
  col += vec3(star) * uNight * (1.0 - uCover);

  // Wolken: FBM auf einer Ebene über dem Betrachter, mit dem Wind verschoben
  vec2 uv = d.xz / (h + 0.12) * 0.55 - uWind * uTime;
  float n = fbm(uv);
  float t = mix(0.85, 0.25, uCover);
  float c = max(smoothstep(t, t + 0.22, n), smoothstep(0.9, 1.0, uCover));
  c *= smoothstep(0.0, 0.1, d.y);
  vec3 cloud = uCloud * mix(1.0, 0.65, smoothstep(t, 1.0, n));
  cloud += vec3(1.0, 0.85, 0.6) * pow(sd, 10.0) * uSunVis * 0.25 * (1.0 - uCover);
  col = mix(col, cloud, c * 0.95);

  gl_FragColor = vec4(col, 1.0);
  #include <colorspace_fragment>
}`;

// Regen (Striche) und Schnee (Punkte): feste Zufallsbox um die Kamera, im Shader per mod() umgebrochen.
const PRECIP_VERT = /* glsl */ `
#include <common>
#include <logdepthbuf_pars_vertex>
attribute float aRand;
attribute float aEnd;
uniform float uTime, uBox, uIntensity, uAlpha, uSize;
uniform vec3 uCam;
uniform vec2 uWind;
uniform bool uSnow;
varying float vAlpha;
void main() {
  vec3 vel = uSnow ? vec3(uWind.x * 0.3, -1.3, uWind.y * 0.3) : vec3(uWind.x * 0.4, -9.0, uWind.y * 0.4);
  vec3 p = position * uBox + vel * uTime;
  if (uSnow) p.xz += vec2(sin(uTime * 0.7 + aRand * 40.0), cos(uTime * 0.6 + aRand * 31.0)) * 1.5;
  p = mod(p - uCam + uBox * 0.5, uBox) - uBox * 0.5;
  if (!uSnow) p -= normalize(vel) * 1.8 * aEnd;
  vAlpha = uAlpha * step(aRand, uIntensity) * (1.0 - smoothstep(0.3, 0.5, length(p.xz) / uBox));
  vec4 mv = viewMatrix * vec4(uCam + p, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = clamp(uSize * 300.0 / -mv.z, 1.0, 12.0);
  #include <logdepthbuf_vertex>
}`;

const PRECIP_FRAG = /* glsl */ `
#include <common>
#include <logdepthbuf_pars_fragment>
uniform bool uSnow;
uniform vec3 uColor;
varying float vAlpha;
void main() {
  #include <logdepthbuf_fragment>
  float a = vAlpha;
  if (uSnow) a *= smoothstep(0.5, 0.2, length(gl_PointCoord - 0.5));
  else a *= 0.45;
  if (a < 0.01) discard;
  gl_FragColor = vec4(uColor, a);
  #include <colorspace_fragment>
}`;

function precipitation(snow: boolean, count: number): THREE.Object3D {
  const geo = new THREE.BufferGeometry();
  const v = snow ? 1 : 2; // Regen: zwei Eckpunkte je Strich
  const pos = new Float32Array(count * v * 3);
  const rand = new Float32Array(count * v);
  const end = new Float32Array(count * v);
  for (let i = 0; i < count; i++) {
    const seed = [Math.random(), Math.random(), Math.random()];
    const r = Math.random();
    for (let k = 0; k < v; k++) {
      pos.set(seed, (i * v + k) * 3);
      rand[i * v + k] = r;
      end[i * v + k] = k;
    }
  }
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("aRand", new THREE.BufferAttribute(rand, 1));
  geo.setAttribute("aEnd", new THREE.BufferAttribute(end, 1));
  const mat = new THREE.ShaderMaterial({
    vertexShader: PRECIP_VERT,
    fragmentShader: PRECIP_FRAG,
    transparent: true,
    depthWrite: false,
    uniforms: {
      uTime: { value: 0 }, uBox: { value: snow ? 120 : 160 }, uIntensity: { value: 0 }, uAlpha: { value: 1 },
      uSize: { value: 0.9 }, uCam: { value: new THREE.Vector3() }, uWind: { value: new THREE.Vector2() },
      uSnow: { value: snow }, uColor: { value: new THREE.Color(snow ? 0xffffff : 0xb8c4d6) },
    },
  });
  const obj = snow ? new THREE.Points(geo, mat) : new THREE.LineSegments(geo, mat);
  obj.frustumCulled = false;
  obj.visible = false;
  return obj;
}

const lerp = THREE.MathUtils.lerp;
const smooth = THREE.MathUtils.smoothstep;
const col = (hex: number) => new THREE.Color(hex);

export class Weather {
  readonly label = document.getElementById("weather")!;
  private current: Current | undefined;
  private readonly sky: THREE.Mesh;
  private readonly rain = precipitation(false, 5000);
  private readonly snow = precipitation(true, 6000);
  // Geglättete Zustände, die ans Wetter nachgeführt werden
  private cover = 0.2;
  private dark = 0; // 0..1: Regen/Gewitter verdunkeln
  private fogNear = 8000;
  private fogFar = 20000;
  private intensity = 0;
  private time = 0;

  constructor(
    private readonly scene: THREE.Scene,
    private readonly sun: THREE.DirectionalLight,
    private readonly hemi: THREE.HemisphereLight,
    private readonly camera: THREE.PerspectiveCamera,
    override?: number,
  ) {
    const m = new THREE.ShaderMaterial({
      vertexShader: SKY_VERT,
      fragmentShader: SKY_FRAG,
      side: THREE.BackSide,
      depthTest: false,
      depthWrite: false,
      uniforms: {
        uSun: { value: new THREE.Vector3(0, 1, 0) }, uZenith: { value: new THREE.Color() }, uHorizon: { value: new THREE.Color() },
        uCloud: { value: new THREE.Color() }, uCover: { value: 0 }, uNight: { value: 0 }, uSunVis: { value: 1 },
        uTime: { value: 0 }, uWind: { value: new THREE.Vector2() },
      },
    });
    this.sky = new THREE.Mesh(new THREE.SphereGeometry(30000, 32, 16), m);
    this.sky.renderOrder = -1000;
    this.sky.frustumCulled = false;
    scene.add(this.sky, this.rain, this.snow);
    scene.background = null;
    scene.fog = new THREE.Fog(0xffffff, this.fogNear, this.fogFar);
    if (override !== undefined) this.set(synthetic(override));
    else void this.fetch();
  }

  private async fetch() {
    try {
      const r = await fetch(API, { signal: AbortSignal.timeout(15000) });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const c = (await r.json()).current;
      if (typeof c?.weather_code !== "number") throw new Error("keine Wetterdaten");
      this.set(c);
    } catch (e) {
      console.warn("Wetter:", e);
      if (!this.current) this.label.textContent = "Wetter nicht verfügbar"; // sonst bleiben die letzten Daten stehen
    }
    setTimeout(() => this.fetch(), 10 * 60 * 1000);
  }

  private set(c: Current) {
    this.current = c;
    const text = LABEL.find(([max]) => c.weather_code <= max)?.[1] ?? "";
    this.label.textContent = `${Math.round(c.temperature_2m)} °C · ${text} · Wind ${Math.round(c.wind_speed_10m)} km/h`;
  }

  /** Sonne, Himmel, Licht, Nebel und Niederschlag für die simulierte Zeit. `night` erzwingt die Nacht. */
  update(now: Date, night: boolean, dt: number) {
    this.time += dt;
    const c = this.current;
    const code = c?.weather_code ?? 0;
    const fog = code === 45 || code === 48;
    const snow = c ? SNOW.has(code) || (c.snowfall > 0 && !RAIN.has(code)) : false;
    const wet = c ? snow || RAIN.has(code) || c.precipitation > 0 : false;
    const targetCover = fog ? 1 : (c?.cloud_cover ?? 20) / 100;
    const k = 1 - Math.exp(-dt / 2);
    this.cover = lerp(this.cover, targetCover, k);
    this.dark = lerp(this.dark, code >= 95 ? 0.7 : wet ? 0.4 : fog ? 0.2 : 0, k);
    this.intensity = lerp(this.intensity, wet ? Math.min(1, 0.3 + (c?.precipitation ?? 0) / 3) : 0, k);
    // Nebel soll auch aus der Startansicht (grosse Höhe) noch Gelände übrig lassen
    const fogFar = Math.max(1600, this.camera.position.y * 2.5);
    this.fogNear = lerp(this.fogNear, fog ? fogFar * 0.03 : wet ? 2000 : 8000, k);
    this.fogFar = lerp(this.fogFar, fog ? fogFar : wet ? 9000 : 20000, k);

    const s = sunPosition(now);
    const sunDir = night ? new THREE.Vector3(0.3, -0.5, 0.8).normalize() : s.dir;
    const e = night ? -0.5 : Math.sin(s.elevation);
    const day = smooth(e, -0.12, 0.2);
    const twilight = Math.max(0, 1 - Math.abs(e - 0.03) / 0.22);
    const grey = Math.min(1, this.cover * 0.75 + this.dark * 0.5);
    const bright = day * (1 - 0.55 * this.dark);

    const horizon = col(0x0b1530).lerp(col(0x9cc3e6), day).lerp(col(0xf0a070), twilight * 0.6);
    const zenith = col(0x040814).lerp(col(0x3a78c8), day).lerp(col(0x6a5a8a), twilight * 0.3);
    const overcast = col(0x2a3040).lerp(col(0xb4bcc6), day);
    horizon.lerp(overcast, grey).multiplyScalar(1 - 0.35 * this.dark);
    zenith.lerp(overcast.clone().multiplyScalar(0.8), grey).multiplyScalar(1 - 0.35 * this.dark);
    if (fog) horizon.lerp(col(0x9aa3ab).multiplyScalar(0.25 + 0.75 * day), 0.8);

    const u = (this.sky.material as THREE.ShaderMaterial).uniforms;
    u.uSun.value.copy(sunDir);
    u.uZenith.value.copy(zenith);
    u.uHorizon.value.copy(horizon);
    u.uCloud.value.copy(col(0xffffff).lerp(col(0x9aa0a8), this.dark + this.cover * 0.25).multiplyScalar(0.12 + 0.88 * bright).lerp(col(0xf0a070).multiplyScalar(0.8), twilight * 0.35 * (1 - this.dark)));
    u.uCover.value = this.cover;
    u.uNight.value = 1 - day;
    u.uSunVis.value = day * (1 - this.cover * 0.85);
    u.uTime.value = this.time;
    const rad = ((c?.wind_direction_10m ?? 0) * Math.PI) / 180; // Richtung, aus der der Wind weht
    const wind = (c?.wind_speed_10m ?? 5) / 3.6;
    const wx = -Math.sin(rad) * wind, wz = Math.cos(rad) * wind;
    u.uWind.value.set(wx * 0.002, wz * 0.002);
    this.sky.position.copy(this.camera.position);

    (this.scene.fog as THREE.Fog).color.copy(horizon);
    (this.scene.fog as THREE.Fog).near = this.fogNear;
    (this.scene.fog as THREE.Fog).far = this.fogFar;

    this.sun.position.copy(sunDir).multiplyScalar(5000);
    this.sun.color.copy(col(0xfff4e0).lerp(col(0xff9050), twilight));
    this.sun.intensity = 1.6 * smooth(e, 0, 0.15) * (1 - 0.85 * this.cover) * (1 - this.dark) + 0.08;
    this.hemi.intensity = 0.25 + 1.35 * bright * (1 - 0.3 * this.cover);

    for (const [obj, active] of [[this.rain, !snow], [this.snow, snow]] as const) {
      const m = (obj as THREE.Points).material as THREE.ShaderMaterial;
      m.uniforms.uTime.value = this.time;
      m.uniforms.uIntensity.value = this.intensity;
      m.uniforms.uCam.value.copy(this.camera.position);
      m.uniforms.uWind.value.set(wx, wz);
      m.uniforms.uColor.value.setScalar(0.25 + 0.75 * bright).multiply(snow ? col(0xffffff) : col(0xc0ccdc));
      // Niederschlag nur nahe am Boden zeigen, aus der Höhe übernehmen Himmel und Nebel
      m.uniforms.uAlpha.value = 1 - smooth(this.camera.position.y, 1100, 2300);
      obj.visible = active && this.intensity > 0.02 && m.uniforms.uAlpha.value > 0.01;
    }
  }
}

/** Testmodus `?wetter=<WMO-Code>`: überschreibt die Live-Daten mit einem festen Wettercode. */
function synthetic(code: number): Current {
  const wet = RAIN.has(code) || SNOW.has(code);
  return {
    weather_code: code,
    temperature_2m: SNOW.has(code) ? -1 : 8,
    precipitation: wet ? 2 : 0,
    snowfall: SNOW.has(code) ? 1 : 0,
    cloud_cover: code === 0 ? 5 : code === 1 ? 20 : code === 2 ? 55 : 100,
    wind_speed_10m: 12,
    wind_direction_10m: 270,
  };
}
