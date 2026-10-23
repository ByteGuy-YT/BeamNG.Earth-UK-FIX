"""Prepare a small offline UK street-detail index from a Geofabrik OSM PBF.

Two streaming passes retain locations only for relevant amenity polygons, not every
node in the country. Requires pyosmium only during preparation. Runtime uses SQLite.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3


def kind(t):
    if t.get('amenity') == 'parking' and t.get('parking') not in ('underground','multi-storey'):
        return 'parking'
    if t.get('shop') == 'supermarket':
        return 'supermarket'
    if t.get('man_made') == 'gantry':
        return 'gantry'
    if t.get('highway') in ('footway','path','cycleway','track') and t.get('tunnel') in ('yes','building_passage'):
        return 'underpass'
    if t.get('barrier') == 'hedge':
        return 'hedge'
    if t.get('highway') in ('speed_camera', 'traffic_signals', 'bus_stop', 'stop', 'give_way', 'mini_roundabout'):
        return t['highway']
    if t.get('traffic_sign'):
        return 'sign'
    if t.get('amenity') in ('fuel', 'school', 'post_box'):
        return t['amenity']
    if t.get('man_made') == 'fuel_pump':
        return 'fuel_pump'
    if t.get('building') in ('roof','carport'):
        return 'canopy'
    return None


def build(source, output):
    import osmium
    source, output = Path(source), Path(output)
    ways, needed, coords, relations, devices = {}, set(), {}, [], {}
    class Ways(osmium.SimpleHandler):
        def way(self, w):
            t = dict(w.tags)
            k = kind(t)
            if ((k in ('fuel', 'school', 'canopy','parking','supermarket') and len(w.nodes) >= 4 and w.nodes[0].ref == w.nodes[-1].ref)
                or (k in ('gantry','underpass','hedge') and 2 <= len(w.nodes) <= 160)):
                refs = [n.ref for n in w.nodes]
                ways[w.id] = (t, refs)
                needed.update(refs)
        def relation(self, r):
            if r.tags.get('type') == 'enforcement' and r.tags.get('enforcement') == 'maxspeed':
                members = {m.role: m.ref for m in r.members if m.type == 'n'}
                if 'device' in members and 'from' in members:
                    relations.append((dict(r.tags), members))
                    needed.update(members.values())
    Ways().apply_file(str(source))
    print('Amenity polygons:', len(ways), 'needed vertices:', len(needed), flush=True)
    temp = output.with_suffix('.tmp')
    output.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(temp)
    db.executescript('DROP TABLE IF EXISTS features; DROP TABLE IF EXISTS bounds; DROP TABLE IF EXISTS metadata;'
                     'CREATE TABLE features(id INTEGER PRIMARY KEY, osm_id TEXT UNIQUE, kind TEXT, tags TEXT, geometry TEXT);'
                     'CREATE VIRTUAL TABLE bounds USING rtree(id,minx,maxx,miny,maxy);'
                     'CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);')
    count = 0
    def put(oid, tags, xy):
        nonlocal count
        k = kind(tags)
        if not k or not xy:
            return
        count += 1
        x, y = zip(*xy)
        db.execute('INSERT INTO features VALUES(?,?,?,?,?)', (count, oid, k, json.dumps(tags), json.dumps(xy)))
        db.execute('INSERT INTO bounds VALUES(?,?,?,?,?)', (count, min(x), max(x), min(y), max(y)))
    class Nodes(osmium.SimpleHandler):
        def node(self, n):
            if n.id in needed:
                coords[n.id] = (n.location.lon, n.location.lat)
            if len(n.tags):
                t = dict(n.tags)
                if kind(t):
                    if kind(t) == 'speed_camera':
                        devices[n.id] = (t, (n.location.lon, n.location.lat))
                        return
                    put('n' + str(n.id), t, [(n.location.lon, n.location.lat)])
    Nodes().apply_file(str(source))
    for tags, members in relations:
        dev, src = members['device'], members['from']
        if dev in devices and src in coords:
            t, pos = devices[dev]
            t['_from'] = coords[src]
            if not t.get('maxspeed') and tags.get('maxspeed'):
                t['maxspeed'] = tags['maxspeed']
    for oid, (t, pos) in devices.items():
        put('n' + str(oid), t, [pos])
    for oid, (t, refs) in ways.items():
        if all(n in coords for n in refs):
            put('w' + str(oid), t, [coords[n] for n in refs])
    with source.open('rb') as f:
        sha = hashlib.file_digest(f, 'sha256').hexdigest()
    for k, v in {'schema': 1, 'source': source.name, 'sha256': sha,
                 'url': 'https://download.geofabrik.de/europe/united-kingdom.html',
                 'attribution': '© OpenStreetMap contributors (ODbL 1.0)', 'features': count}.items():
        db.execute('INSERT INTO metadata VALUES(?,?)', (k, json.dumps(v)))
    db.commit()
    db.close()
    temp.replace(output)
    print('Indexed', count, 'street features:', output, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source')
    p.add_argument('--output', default=str(Path(__file__).resolve().parents[1] / '.road-data/uk-context.sqlite'))
    a = p.parse_args()
    build(a.source, a.output)
