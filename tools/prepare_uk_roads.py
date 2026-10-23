"""Build an immutable OSM road index from regional .osm.pbf or .osm[.bz2/.gz].

PBF needs the optional `osmium` package (preparation only, never the running server).
Example: python tools/prepare_uk_roads.py derbyshire-latest.osm.pbf --output .road-data/osm.sqlite
Set BEAMNG_EARTH_OSM_DB to that absolute path before starting. Restart after replacing it.
Multiple extracts can be supplied; highest way version wins. The original files are kept.
"""
import argparse
import bz2
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import xml.etree.ElementTree as ET


def build(paths, output):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + f".{os.getpid()}.tmp")
    db = sqlite3.connect(temp)
    db.executescript("CREATE TABLE ways(id INTEGER PRIMARY KEY, version INTEGER, tags TEXT, geometry TEXT);"
                     "CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT);")
    total = 0

    def put(way_id, version, tags, coords):
        nonlocal total
        if "highway" not in tags or len(coords) < 2:
            return
        db.execute("INSERT INTO ways VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                   "version=excluded.version,tags=excluded.tags,geometry=excluded.geometry "
                   "WHERE excluded.version > ways.version", (way_id, version,
                   json.dumps(tags, sort_keys=True, separators=(",", ":")), json.dumps(coords, separators=(",", ":"))))
        total += 1
        if total % 10000 == 0:
            db.commit()

    provenance = []
    try:
        for path in map(Path, paths):
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            provenance.append({"file": path.name, "sha256": digest})
            if path.name.endswith(".pbf"):
                try:
                    import osmium
                except ImportError:
                    raise RuntimeError("PBF preparation requires osmium: install it in a Python 3.11-3.13 environment, or supply OSM XML") from None

                class Handler(osmium.SimpleHandler):
                    def __init__(self):
                        super().__init__()
                        self.controls = {}

                    def node(self, n):
                        if n.tags.get("highway") in {"traffic_signals", "stop", "give_way", "crossing", "mini_roundabout"}:
                            self.controls[n.id] = {"lon": n.location.lon, "lat": n.location.lat, **dict(n.tags)}

                    def way(self, w):
                        if "highway" not in w.tags:
                            return
                        if all(n.location.valid() for n in w.nodes):
                            tags = dict(w.tags)
                            controls = [self.controls[n.ref] for n in w.nodes if n.ref in self.controls]
                            if controls:
                                tags["_nodes"] = controls
                            put(w.id, w.version, tags, [(n.lon, n.lat) for n in w.nodes])
                # Disk-backed sparse location index: national imports must not consume all RAM.
                locations = temp.with_suffix(".locations")
                try:
                    Handler().apply_file(str(path), locations=True, idx=f"sparse_file_array,{locations.as_posix()}")
                finally:
                    import gc
                    gc.collect()
                    try:
                        locations.unlink(missing_ok=True)
                    except PermissionError:
                        # Windows can retain libosmium's mmap until interpreter shutdown.
                        print(f"Location scratch file can be removed after exit: {locations}", flush=True)
            else:
                opener = bz2.open if path.suffix == ".bz2" else gzip.open if path.suffix == ".gz" else open
                nodes, controls = {}, {}
                with opener(path, "rb") as stream:
                    # Clear only completed top-level elements, preserving way tags and node references.
                    for _, el in ET.iterparse(stream, events=("end",)):
                        if el.tag == "node":
                            nodes[int(el.attrib["id"])] = (float(el.attrib["lon"]), float(el.attrib["lat"]))
                            tags = {x.attrib["k"]: x.attrib["v"] for x in el.findall("tag")}
                            if tags.get("highway") in {"traffic_signals", "stop", "give_way", "crossing", "mini_roundabout"}:
                                controls[int(el.attrib["id"])] = {"lon": float(el.attrib["lon"]), "lat": float(el.attrib["lat"]), **tags}
                            el.clear()
                        elif el.tag == "way":
                            tags = {x.attrib["k"]: x.attrib["v"] for x in el.findall("tag")}
                            refs = [int(x.attrib["ref"]) for x in el.findall("nd")]
                            if any(n in controls for n in refs):
                                tags["_nodes"] = [controls[n] for n in refs if n in controls]
                            if all(n in nodes for n in refs):
                                put(int(el.attrib["id"]), int(el.attrib.get("version", 0)), tags, [nodes[n] for n in refs])
                            el.clear()
            print(f"Read {path.name}: {total:,} road ways", flush=True)
        for k, v in {"sources": provenance, "attribution": "© OpenStreetMap contributors (ODbL 1.0)",
                     "schema": 1}.items():
            db.execute("INSERT INTO metadata VALUES(?,?)", (k, json.dumps(v)))
        db.commit()
        count = db.execute("SELECT count(*) FROM ways").fetchone()[0]
        db.close()
        os.replace(temp, output)
        print(f"Indexed {count:,} ways in {output}", flush=True)
        return count
    except BaseException:
        db.close()
        temp.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("extracts", nargs="+")
    ap.add_argument("--output", default=str(Path(__file__).resolve().parents[1] / ".road-data" / "osm.sqlite"))
    args = ap.parse_args()
    build(args.extracts, args.output)
