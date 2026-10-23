"""Offline UK country membership. ONS 20 m boundaries, independent of airport rendering.

The polygons choose a ruleset, never road edges. Points outside the UK return None so
the existing worldwide country resolver remains available. No network or anchor state.
"""
import gzip
import json
from functools import lru_cache
from pathlib import Path

import numpy as np


@lru_cache(maxsize=1)
def _polygons():
    path = Path(__file__).with_name("data") / "uk_countries_2024.geojson.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        data = json.load(stream)
    rows = []
    for f in data["features"]:
        g = f["geometry"]
        for poly in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]):
            rings = [np.asarray(r, np.float64)[:, :2] for r in poly]
            a = rings[0]
            rows.append((f["properties"]["name"], (a[:, 0].min(), a[:, 1].min(),
                         a[:, 0].max(), a[:, 1].max()), rings))
    return rows


def _inside(lon, lat, ring):
    a, b = ring[:-1], ring[1:]
    hit = (a[:, 1] > lat) != (b[:, 1] > lat)
    a, b = a[hit], b[hit]
    return bool(np.count_nonzero(lon < (b[:, 0] - a[:, 0]) *
                                (lat - a[:, 1]) / (b[:, 1] - a[:, 1]) + a[:, 0]) % 2)


@lru_cache(maxsize=65536)
def region_at(lat, lon):
    """England, Wales, Scotland, Northern Ireland, or None (including the Republic)."""
    if not (-8.7 <= lon <= 2.0 and 49.7 <= lat <= 61.0):
        return None
    for name, (x0, y0, x1, y1), rings in _polygons():
        if x0 <= lon <= x1 and y0 <= lat <= y1 and _inside(lon, lat, rings[0]):
            if not any(_inside(lon, lat, r) for r in rings[1:]):
                return name
    return None


def feature_region(feats, i):
    memo = feats.__dict__.setdefault("_uk_regions", {})
    if i not in memo:
        a = feats.coord_off[feats.ring_off[feats.part_off[i]]]
        b = feats.coord_off[feats.ring_off[feats.part_off[i + 1]]]
        ll = feats.lonlat[(a + b) // 2] if b > a else (0., 0.)
        region = region_at(float(ll[1]), float(ll[0]))
        flags = feats.rules.get("flags")
        bridge = flags is not None and any(str(flags.value[r]) == "is_bridge" for r in flags.rows(i))
        if region is None and bridge and b > a:
            # Coastal bridges can have their centre over water outside the clipped land polygons.
            ends = [region_at(float(feats.lonlat[j, 1]), float(feats.lonlat[j, 0])) for j in (a, b - 1)]
            present = {r for r in ends if r is not None}
            if len(present) == 1:
                region = present.pop()
        memo[i] = region
    return memo[i]
