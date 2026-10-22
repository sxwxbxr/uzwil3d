import * as THREE from "three";

export interface TileInfo {
  e: number;
  n: number;
  terrain: string;
  ortho: string | null;
  buildings?: string | null;
}

export interface Manifest {
  bbox_lv95: [number, number, number, number];
  origin_lv95: [number, number];
  area: string;
  tile_size_m: number;
  terrain_spacing_m: number;
  terrain_samples: number;
  height_min: number;
  height_max: number;
  buildings_scale: number;
  buildings_count: number;
  tiles: TileInfo[];
  attribution: string[];
}

// Szene: x = Ost, -z = Nord, y = Höhe über height_min (Meter).
export function toScene(m: Manifest, e: number, n: number): [number, number] {
  return [e - m.origin_lv95[0], -(n - m.origin_lv95[1])];
}

interface LoadedTile {
  info: TileInfo;
  heights: Float32Array;
}

export class Terrain {
  readonly group = new THREE.Group();
  private tiles = new Map<string, LoadedTile>();

  constructor(
    readonly manifest: Manifest,
    private baseUrl: string,
  ) {}

  async load(onProgress: (done: number, total: number) => void): Promise<void> {
    const m = this.manifest;
    const loader = new THREE.TextureLoader();
    let done = 0;
    await Promise.all(
      m.tiles.map(async (info) => {
        const [buf, tex] = await Promise.all([
          fetch(this.baseUrl + info.terrain).then((r) => r.arrayBuffer()),
          info.ortho ? loader.loadAsync(this.baseUrl + info.ortho) : null,
        ]);
        const heights = decodeHeights(buf);
        this.tiles.set(key(info.e, info.n), { info, heights });
        this.group.add(this.buildMesh(info, heights, tex));
        onProgress(++done, m.tiles.length);
      }),
    );
  }

  private buildMesh(info: TileInfo, heights: Float32Array, tex: THREE.Texture | null): THREE.Mesh {
    const m = this.manifest;
    const s = m.terrain_samples;
    const geo = new THREE.PlaneGeometry(m.tile_size_m, m.tile_size_m, s - 1, s - 1);
    geo.rotateX(-Math.PI / 2);
    // PlaneGeometry läuft zeilenweise von oben (Norden) nach unten, wie das Raster.
    const pos = geo.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < pos.count; i++) pos.setY(i, heights[i]);
    geo.computeVertexNormals();
    geo.computeBoundingSphere();

    if (tex) {
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 8;
    }
    const mesh = new THREE.Mesh(geo, new THREE.MeshLambertMaterial(tex ? { map: tex } : { color: 0x8a9a7a }));
    const half = m.tile_size_m / 2;
    const [x, z] = toScene(m, info.e + half, info.n + half);
    mesh.position.set(x, 0, z);
    return mesh;
  }

  /** Höhe in Szenen-Metern an einer LV95-Koordinate, bilinear interpoliert. */
  heightAt(e: number, n: number): number | undefined {
    const m = this.manifest;
    const ts = m.tile_size_m;
    const te = Math.floor(e / ts) * ts;
    const tn = Math.floor(n / ts) * ts;
    const tile = this.tiles.get(key(te, tn));
    if (!tile) return undefined;
    const s = m.terrain_samples;
    const col = (e - te) / m.terrain_spacing_m;
    const row = (tn + ts - n) / m.terrain_spacing_m;
    const c0 = Math.min(Math.floor(col), s - 2);
    const r0 = Math.min(Math.floor(row), s - 2);
    const fc = col - c0;
    const fr = row - r0;
    const h = tile.heights;
    const at = (r: number, c: number) => h[r * s + c];
    return (
      at(r0, c0) * (1 - fc) * (1 - fr) +
      at(r0, c0 + 1) * fc * (1 - fr) +
      at(r0 + 1, c0) * (1 - fc) * fr +
      at(r0 + 1, c0 + 1) * fc * fr
    );
  }
}

function key(e: number, n: number): string {
  return `${e}_${n}`;
}

function decodeHeights(buf: ArrayBuffer): Float32Array {
  // Uint16 LE, Zentimeter über height_min. Szene nutzt height_min als Nullniveau.
  const view = new DataView(buf);
  const out = new Float32Array(buf.byteLength / 2);
  for (let i = 0; i < out.length; i++) out[i] = view.getUint16(i * 2, true) / 100;
  return out;
}
