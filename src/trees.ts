import * as THREE from "three";
import { toScene, type Manifest } from "./terrain";

/** Bäume aus der Pipeline (pipeline/uzwil3d_pipeline/trees.py) als ein InstancedMesh. */
export async function loadTrees(m: Manifest, baseUrl: string): Promise<THREE.InstancedMesh> {
  const tiles = m.tiles.filter((t) => t.trees);
  const bufs = await Promise.all(tiles.map((t) => fetch(baseUrl + t.trees).then((r) => r.arrayBuffer())));
  const total = bufs.reduce((s, b) => s + b.byteLength / 8, 0);

  const geo = new THREE.ConeGeometry(1, 1, 7);
  geo.translate(0, 0.5, 0);
  const mesh = new THREE.InstancedMesh(geo, new THREE.MeshLambertMaterial(), total);
  const mat = new THREE.Matrix4();
  const color = new THREE.Color();
  const half = m.tile_size_m / 2;
  let i = 0;
  tiles.forEach((t, k) => {
    const d = new Int16Array(bufs[k]);
    const [cx, cz] = toScene(m, t.e + half, t.n + half);
    for (let j = 0; j < d.length; j += 4) {
      const h = d[j + 3] / 10;
      const r = Math.min(Math.max(h * 0.22, 1.2), 6);
      mat.makeScale(r, h, r).setPosition(cx + d[j] / 10, d[j + 2] / 10, cz + d[j + 1] / 10);
      mesh.setMatrixAt(i, mat);
      // leichte Farbvariation, sonst wirkt der Wald wie eine Fläche
      mesh.setColorAt(i++, color.setHSL(0.27 + ((j * 7919) % 100) / 2000, 0.45, 0.17 + ((j * 104729) % 100) / 1500));
    }
  });
  return mesh;
}
