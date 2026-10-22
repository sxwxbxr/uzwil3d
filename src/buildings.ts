import * as THREE from "three";
import { toScene, type Manifest } from "./terrain";

// Die Flächenorientierung in swissBUILDINGS3D ist nicht einheitlich, daher beidseitig.
const WALL = new THREE.MeshLambertMaterial({ color: 0xe8e2d6, side: THREE.DoubleSide });
const ROOF = new THREE.MeshLambertMaterial({ color: 0xa55a43, side: THREE.DoubleSide });

/** Lädt die Gebäudekacheln aus der Pipeline (siehe pipeline/uzwil3d_pipeline/buildings.py). */
export async function loadBuildings(m: Manifest, baseUrl: string): Promise<THREE.Group> {
  const group = new THREE.Group();
  const half = m.tile_size_m / 2;
  await Promise.all(
    m.tiles
      .filter((t) => t.buildings)
      .map(async (t) => {
        const buf = await fetch(baseUrl + t.buildings).then((r) => r.arrayBuffer());
        const [walls, roofs] = new Uint32Array(buf, 0, 2);
        const raw = new Int16Array(buf, 8, (walls + roofs) * 3);
        const pos = new Float32Array(raw.length);
        for (let i = 0; i < raw.length; i++) pos[i] = raw[i] * m.buildings_scale;

        const [x, z] = toScene(m, t.e + half, t.n + half);
        for (const [mat, start, count] of [
          [WALL, 0, walls],
          [ROOF, walls, roofs],
        ] as const) {
          if (!count) continue;
          const geo = new THREE.BufferGeometry();
          geo.setAttribute("position", new THREE.BufferAttribute(pos.subarray(start * 3, (start + count) * 3), 3));
          geo.computeVertexNormals();
          const mesh = new THREE.Mesh(geo, mat);
          mesh.position.set(x, 0, z);
          group.add(mesh);
        }
      }),
  );
  return group;
}
