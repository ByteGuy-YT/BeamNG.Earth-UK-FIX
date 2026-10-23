"""Export resolved roads, provenance and optional reference/orthophoto comparisons.

Reference input: licensed WGS84 GeoJSON LineStrings, with a width_m (or --width-field)
property. It is used only for comparison, never silently copied into the road database.
Orthophoto input: a north-up image with explicitly supplied WGS84 geographic bounds.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
import geodesy
import mapcells
import mapdata
import netfetch
import osm_enrich
import roadprofile
import roads


def inspect(lat, lon, cache_dir, output, offline=False, reference=None, width_field="width_m",
            image=None, image_bounds=None):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    md = mapdata.MapData(str(cache_dir), netfetch.Fetcher(offline=offline))
    try:
        cell = md.cell(mapcells.cell_of(lat, lon), layers=("roads", "landcover"))
        f, lc = cell.layers["roads"], cell.layers.get("landcover")
        urban = (lambda la, lo: lc.sample(lo, la) == 50) if lc is not None else None
        specs = roads.road_specs(f, urban)
        refs = []
        if reference:
            doc = json.loads(Path(reference).read_text(encoding="utf-8"))
            if "crs" in doc and "4326" not in json.dumps(doc["crs"]) and "CRS84" not in json.dumps(doc["crs"]):
                raise ValueError("Reproject reference data to WGS84 before comparison")
            refs = [r for r in doc["features"] if r["geometry"]["type"] == "LineString" and width_field in r["properties"]]
        features, summary = [], Counter()
        for i, sp in enumerate(specs):
            if sp is None or sp.profile is None:
                continue
            a = f.coord_off[f.ring_off[f.part_off[i]]]
            b = f.coord_off[f.ring_off[f.part_off[i + 1]]]
            ll = f.lonlat[a:b]
            data = asdict(sp.profile)
            data.update(id=str(f.ids[i]), name=str(f.attrs.get("name", [""] * len(f))[i] or ""),
                        road_class=sp.cls, osm_match=str(f.attrs.get("osm_match", ["no-index"] * len(f))[i]))
            summary[data["source"]] += 1
            matches = [r for r in refs if r["properties"].get("gers_id") == data["id"] or
                       osm_enrich.alignment(ll, r["geometry"]["coordinates"]) is not None]
            if len(matches) == 1:
                value = roadprofile.metres(matches[0]["properties"][width_field])
                if value is not None:
                    data.update(reference_width_m=value, width_difference_m=round(sp.width - value, 3))
            elif matches:
                data["reference_match"] = "ambiguous"
            features.append({"type": "Feature", "properties": data,
                             "geometry": {"type": "LineString", "coordinates": ll.tolist()}})
        doc = {"type": "FeatureCollection", "source_versions": md.versions(),
               "attribution": cell.credit_line(), "interpretation": "Mapped values and estimates are distinguished per feature.",
               "width_sources": dict(summary), "features": features}
        output.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        if image:
            if image_bounds is None:
                raise ValueError("An orthophoto requires --image-bounds west south east north")
            im = Image.open(image).convert("RGB")
            draw = ImageDraw.Draw(im)
            west, south, east, north = image_bounds
            if not (east > west and north > south):
                raise ValueError("Invalid image bounds")
            def pixels(coords):
                return [((x - west) / (east - west) * im.width, (north - y) / (north - south) * im.height) for x, y in coords]
            for f in features:
                ll = np.asarray(f["geometry"]["coordinates"])
                frame = geodesy.EnuFrame(float(ll[0, 1]), float(ll[0, 0]))
                e, n, _ = frame.geodetic_to_enu(ll[:, 1], ll[:, 0], 0.)
                line = np.column_stack([e, n, np.zeros(len(e))])
                p = f["properties"]
                for side, walk in ((1, p["walk_left"]), (-1, p["walk_right"])):
                    for offset, colour in ((p["width"] / 2, "cyan"), (p["width"] / 2 + walk, "yellow")):
                        edge = roads.offset_polyline(line, side * offset)
                        la, lo, _ = frame.enu_to_geodetic(edge[:, 0], edge[:, 1], 0.)
                        draw.line(pixels(zip(lo, la)), fill=colour, width=2)
            im.save(output.with_suffix(".overlay.png"))
        print(json.dumps({"roads": len(features), "width_sources": dict(summary),
                          "osm_matches": dict(Counter(f["properties"]["osm_match"] for f in features)), "output": str(output)}), flush=True)
        return doc
    finally:
        md.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("lat", type=float)
    ap.add_argument("lon", type=float)
    ap.add_argument("--cache-dir", default=mapdata.DEFAULT_CACHE)
    ap.add_argument("--output", required=True)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--reference")
    ap.add_argument("--width-field", default="width_m")
    ap.add_argument("--image")
    ap.add_argument("--image-bounds", nargs=4, type=float)
    args = ap.parse_args()
    inspect(**vars(args))
