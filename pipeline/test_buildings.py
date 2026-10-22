"""Selbstcheck der Triangulierung: python -I pipeline/test_buildings.py"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uzwil3d_pipeline.buildings import _triangulate  # noqa: E402

# Senkrechte L-förmige Wand (nicht konvex), Fläche 3 m²
ring = np.array([[0, 0, 0], [2, 0, 0], [2, 0, 1], [1, 0, 1], [1, 0, 2], [0, 0, 2]], dtype=float)
tris = _triangulate(ring)
area = sum(np.linalg.norm(np.cross(b - a, c - a)) / 2 for a, b, c in tris)
assert len(tris) == 4 and abs(area - 3) < 1e-9, (len(tris), area)
assert _triangulate(ring[:3]).shape == (1, 3, 3)
print("ok")
