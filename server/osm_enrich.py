"""Read-only, optional OSM tag join. Geometry/topology continue to come from Overture.

An immutable SQLite index is prepared once with tools/prepare_uk_roads.py. No queries
to public Overpass and no network on the tile path. Reject distant/ambiguous joins.
"""
import json
import hashlib
import logging
import os
from pathlib import Path
import re
import sqlite3
import sys
import threading
from collections import OrderedDict

import numpy as np

log = logging.getLogger("earthd.osm")


def reverse_tags(tags):
    """Forward/backward and left/right are relative to OSM digitisation, not the UK driving side."""
    out = {}
    swap = {"forward": "backward", "backward": "forward", "left": "right", "right": "left"}
    for key, val in tags.items():
        if key == '_nodes':
            val = [dict(n) for n in val]
            for n in val:
                for nk in ('direction', 'traffic_signals:direction'):
                    if n.get(nk) in ('forward', 'backward'):
                        n[nk] = swap[n[nk]]
        new = ":".join(swap.get(x, x) for x in key.split(":"))
        if key == "oneway":
            val = "-1" if val in {"yes", "true", "1"} else "yes" if val in {"-1", "reverse"} else val
        if key == "sidewalk" and val in {"left", "right"}:
            val = swap[val]
        # Unqualified lane arrays on one-way ways are viewed in the driving direction:
        # keep their order. Directional arrays also retain travel-relative lane order.
        out[new] = val
    return out


def alignment(segment, way):
    """+1 / -1 orientation for a close, unambiguous subline, None otherwise.

    Source ways may be split into many GERS segments; compare local tangent directions,
    not just the way endpoints (closed roundabouts have identical endpoints).
    """
    a, b = np.asarray(segment, float), np.asarray(way, float)
    if len(a) < 2 or len(b) < 2:
        return None
    scale = np.array([111320. * np.cos(np.radians(a[:, 1].mean())), 111320.])
    ref = a[0]
    a, b = (a - ref) * scale, (b - ref) * scale
    seg = np.diff(b, axis=0)
    lens = np.hypot(*seg.T)
    valid = lens > .05
    starts, seg, lens = b[:-1][valid], seg[valid], lens[valid]
    if not len(lens):
        return None
    # Include midpoints to reject a different nearby arm whose endpoints happen to match.
    samples = np.concatenate([a, (a[:-1] + a[1:]) / 2])
    step = max(1, len(samples) // 64)
    samples = samples[::step]
    delta = samples[:, None] - starts[None]
    t = np.clip((delta * seg).sum(2) / (lens * lens), 0, 1)
    dist = np.linalg.norm(delta - t[..., None] * seg, axis=2)
    nearest = dist.argmin(1)
    if np.quantile(dist[np.arange(len(samples)), nearest], .95) > 10.:
        return None
    mid = (a[:-1] + a[1:]) / 2
    dv = np.diff(a, axis=0)
    length = np.hypot(*dv.T)
    delta = mid[:, None] - starts[None]
    t = np.clip((delta * seg).sum(2) / (lens * lens), 0, 1)
    k = np.linalg.norm(delta - t[..., None] * seg, axis=2).argmin(1)
    dots = (dv * seg[k]).sum(1) / np.maximum(length * lens[k], 1e-9)
    good = length > .1
    if not good.any() or np.average(np.abs(dots[good]), weights=length[good]) < .8:
        return None
    mean = np.average(dots[good], weights=length[good])
    return (1 if mean > 0 else -1) if abs(mean) > .7 else None


def partial_alignment(segment, way):
    """Orientation and covered fraction when several OSM ways form one Overture segment."""
    direction = alignment(segment, way)
    if direction is not None:
        return direction, 0., 1.
    a, b = np.asarray(segment, float), np.asarray(way, float)
    if len(a) < 2 or len(b) < 2:
        return None
    scale = np.array([111320. * np.cos(np.radians(a[:, 1].mean())), 111320.])
    ref = a[0]
    a, b = (a - ref) * scale, (b - ref) * scale
    seg, wayseg = np.diff(a, axis=0), np.diff(b, axis=0)
    lengths, waylength = np.hypot(*seg.T), np.hypot(*wayseg.T)
    station, ws = np.r_[0., np.cumsum(lengths)], np.r_[0., np.cumsum(waylength)]
    if station[-1] < .1 or ws[-1] < .1:
        return None
    samples = np.linspace(0., ws[-1], min(512, max(3, int(ws[-1] / 5) + 1)))
    q = np.column_stack([np.interp(samples, ws, b[:, 0]), np.interp(samples, ws, b[:, 1])])
    delta = q[:, None] - a[None, :-1]
    f = np.clip((delta * seg).sum(2) / np.maximum(lengths * lengths, 1e-12), 0, 1)
    dist = np.linalg.norm(delta - f[..., None] * seg, axis=2)
    k = dist.argmin(1)
    near = dist[np.arange(len(q)), k] <= 8.
    if np.count_nonzero(near) < 3:
        return None
    wk = np.clip(np.searchsorted(ws, samples, side="right") - 1, 0, len(wayseg) - 1)
    dot = (seg[k] * wayseg[wk]).sum(1) / np.maximum(lengths[k] * waylength[wk], 1e-9)
    good = near & (np.abs(dot) > .8)
    if good.sum() < 3 or abs(float(np.mean(dot[good]))) < .8:
        return None
    s = station[k[good]] + f[np.flatnonzero(good), k[good]] * lengths[k[good]]
    start, end = max(0., float(s.min() / station[-1])), min(1., float(s.max() / station[-1]))
    if (end - start) * station[-1] < 2.:
        return None
    return (1 if np.mean(dot[good]) > 0 else -1), start, end


def merge_matches(matches):
    """Only promote attributes common to all covering source ways. Conflicts stay explicit."""
    intervals = sorted((a, b) for _, a, b in matches)
    end, coverage = 0., 0.
    for a, b in intervals:
        coverage += max(0., b - max(a, end))
        end = max(end, b)
    if coverage < .9:
        return None
    common = dict(matches[0][0])
    keys = set().union(*(t for t, _, _ in matches))
    for key in list(common):
        if key == "_nodes" or not all(t.get(key) == common[key] for t, _, _ in matches):
            common.pop(key, None)
    nodes = {json.dumps(n, sort_keys=True): n for t, _, _ in matches for n in t.get("_nodes", ())}
    if nodes:
        common["_nodes"] = [nodes[k] for k in sorted(nodes)]
    conflicts = sorted(k for k in keys if k not in common and k != "_nodes" and
                       k in {"width", "lanes", "lanes:forward", "lanes:backward", "sidewalk", "oneway"})
    if conflicts:
        common["_section_conflicts"] = ",".join(conflicts)
    return common


def section_plan(matches):
    """Preserve real lane/width changes where Overture merged several source ways."""
    # Every cross-section/control family must survive Overture combining source
    # ways, including roads whose only lane-count evidence is a turn-lane array.
    prefixes = ("width", "est_width", "lanes", "turn:lanes", "change:lanes", "destination:lanes", "destination:ref:lanes", "access:lanes", "sidewalk", "shoulder", "parking",
                "oneway", "junction", "bridge", "tunnel", "layer", "highway")
    important = sorted({k for t, _, _ in matches for k in t
                        if any(k == prefix or k.startswith(prefix + ":") for prefix in prefixes)})
    signatures = {json.dumps({k: t.get(k) for k in important}, sort_keys=True) for t, _, _ in matches}
    if len(signatures) <= 1 or merge_matches(matches) is None:
        return None
    bounds = sorted({0., 1.} | {round(v, 6) for _, a, b in matches for v in (a, b) if 0 < v < 1})
    out = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b - a < 1e-5:
            continue
        mid = (a + b) / 2
        active = [t for t, lo, hi in matches if lo - 1e-6 <= mid <= hi + 1e-6]
        if not active:
            # Small source/geometry offsets may leave a gap. Keep it unknown, not an invented lane count.
            t = {}
        elif len(active) == 1:
            t = active[0]
        else:
            t = merge_matches([(x, 0., 1.) for x in active]) or {}
        if out and t == out[-1][2]:
            out[-1] = (out[-1][0], b, t)
        else:
            out.append((a, b, t))
    return out


def _slice(line, start, end):
    scale = np.array([111320. * np.cos(np.radians(line[:, 1].mean())), 111320.])
    distances = np.r_[0., np.cumsum(np.linalg.norm(np.diff(line, axis=0) * scale, axis=1))]
    if distances[-1] <= 0:
        return line
    s = distances / distances[-1]
    at = np.r_[start, s[(s > start) & (s < end)], end]
    return np.column_stack([np.interp(at, s, line[:, 0]), np.interp(at, s, line[:, 1])])


def control_sections(sections, ll):
    """Give an explicitly mapped mid-block signal its own graph connector.

    Signals within 60 m of an existing end remain part of that junction, retaining
    their measured setback. Only a distant, on-road node splits the centreline.
    """
    if len(ll)<2:
        return sections
    scale=np.array([111320.*np.cos(np.radians(ll[:,1].mean())),111320.])
    xy=(ll-ll[0])*scale;d=np.diff(xy,axis=0);l2=np.maximum((d*d).sum(1),1e-12)
    lengths=np.sqrt(l2);s=np.r_[0.,np.cumsum(lengths)]
    if s[-1]<125.:
        return sections
    cuts=[]
    for a,b,tags in sections:
        if tags.get('bridge') not in (None,'no') or tags.get('tunnel') not in (None,'no'):
            continue
        for node in tags.get('_nodes',()):
            if node.get('highway')!='traffic_signals':
                continue
            q=(np.array([node['lon'],node['lat']])-ll[0])*scale
            t=np.clip(((q-xy[:-1])*d).sum(1)/l2,0.,1.)
            dist=np.linalg.norm(q-xy[:-1]-t[:,None]*d,axis=1);i=int(dist.argmin())
            at=(s[i]+t[i]*lengths[i])/s[-1]
            if dist[i]<=3. and (at-a)*s[-1]>60. and (b-at)*s[-1]>60.:
                cuts.append(round(float(at),6))
    out=[]
    for a,b,tags in sections:
        bounds=sorted({a,b}|{c for c in cuts if a<c<b})
        out.extend((x,y,tags) for x,y in zip(bounds[:-1],bounds[1:]))
    return out


def split_features(feats, plans):
    """Split only the interpretation view, retaining original vertices and ranged topology.

    New internal connectors are deterministic functions of parent GERS id and fraction,
    hence equal on either side of a tile/cell boundary. The downloaded cell stays unchanged.
    """
    import mapgeom
    rows, geometries, ids = [], [], []
    for i in range(len(feats)):
        parts = feats.parts(i)
        plan = plans.get(i) if len(parts) == 1 and len(parts[0]) == 1 else None
        for a, b, tags in plan or [(0., 1., None)]:
            fid = str(feats.ids[i])
            ids.append(f"{fid}~osm{round(a * 1e6)}_{round(b * 1e6)}" if plan else fid)
            geometries.append((int(feats.kind[i]), [[_slice(np.asarray(parts[0][0]), a, b)]] if plan else parts))
            rows.append((i, a, b, tags, fid))
    order = np.argsort(ids, kind="stable")
    rows = [rows[j] for j in order]
    out = mapgeom.build(feats.layer, np.asarray(ids)[order], [geometries[j] for j in order])
    for name, col in feats.attrs.items():
        out.attrs[name] = np.asarray(col)[[i for i, *_ in rows]]
    out.attrs["source_parent"] = np.asarray([fid for i, a, b, t, fid in rows])
    tags = [json.dumps(t, sort_keys=True, separators=(",", ":")) if t is not None else str(feats.attrs["osm_tags"][i])
            for i, a, b, t, fid in rows]
    out.attrs["osm_tags"] = np.asarray(tags, dtype=str)
    for name, table in feats.rules.items():
        entries = []
        for j, (i, a, b, tags, fid) in enumerate(rows):
            for r in table.rows(i):
                lo, hi = max(a, float(table.start[r])), min(b, float(table.end[r]))
                if name == "connectors" and table.start[r] == table.end[r]:
                    at = float(table.start[r])
                    if abs(at - a) < 1e-5:
                        lo = hi = a
                    elif abs(at - b) < 1e-5:
                        lo = hi = b
                if hi < lo or hi == lo and table.start[r] != table.end[r]:
                    continue
                value = table.value[r]
                value = value.item() if hasattr(value, "item") else value
                entries.append((j, value, [(lo - a) / (b - a), (hi - a) / (b - a)]))
            if name == "connectors":
                for at, local in ((a, 0.), (b, 1.)):
                    existing = any(abs(float(table.start[r]) - at) < 1e-5 for r in table.rows(i))
                    if 0 < at < 1 and not existing:
                        entries.append((j, f"osm:{fid}:{round(at * 1e6)}", [local, local]))
        kind = "text" if table.value.dtype.kind in "UOS" else "float"
        out.rules[name] = mapgeom.rule_table(entries, kind)
    if "connectors" not in out.rules:
        entries = [(j, f"osm:{fid}:{round(at * 1e6)}", [local, local])
                   for j, (i, a, b, tags, fid) in enumerate(rows) for at, local in ((a, 0.), (b, 1.)) if 0 < at < 1]
        out.rules["connectors"] = mapgeom.rule_table(entries, "text")
    for name in ("own", "clipped"):
        col = getattr(feats, name)
        if col is not None:
            setattr(out, name, col[[i for i, *_ in rows]])
    return out


class Enricher:
    def __init__(self, cache_dir):
        root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
        bundled = root / ".road-data" / "osm.sqlite"
        default = bundled if bundled.is_file() else Path(cache_dir) / "roads" / "osm.sqlite"
        self.path = Path(os.environ.get("BEAMNG_EARTH_OSM_DB", default)).resolve()
        extra=self.path.with_name('osm-extra.sqlite')
        self.extra_path=extra if extra.is_file() and extra!=self.path else None
        if not self.path.is_file() and self.extra_path is not None:
            self.path,self.extra_path=self.extra_path,None
        self.local = threading.local()
        self.lock = threading.RLock()
        self.connections = []
        self.closed = False
        self.metadata = {}
        self.signature = None
        self.match_cache=OrderedDict()
        self.match_cache_bytes=0
        if self.path.is_file():
            db = None
            try:
                db = sqlite3.connect(self.path.as_uri() + "?mode=ro&immutable=1", uri=True)
                metadata = dict(db.execute("SELECT key,value FROM metadata"))
                if self.extra_path is not None:
                    supplemental=sqlite3.connect(self.extra_path.as_uri()+'?mode=ro&immutable=1',uri=True)
                    try:
                        metadata['supplemental']=json.dumps(dict(supplemental.execute('SELECT key,value FROM metadata')),sort_keys=True)
                    finally:
                        supplemental.close()
                self.metadata = metadata
                db.execute("SELECT id,tags,geometry FROM ways LIMIT 0")
                self.signature = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()[:20]
            except sqlite3.Error as exc:
                log.warning("OSM index unavailable (%s); using mapped Overture widths / labelled UK estimates", exc)
            finally:
                if db is not None:
                    db.close()

    def _db(self):
        if not self.signature or self.closed:
            return None
        if not hasattr(self.local, "db"):
            self.local.db = sqlite3.connect(self.path.as_uri() + "?mode=ro&immutable=1", uri=True, check_same_thread=False)
            if self.extra_path is not None:
                self.local.db.execute('ATTACH DATABASE ? AS extra',(self.extra_path.as_uri()+'?mode=ro&immutable=1',))
            self.connections.append(self.local.db)
        return self.local.db

    def apply(self, feats):
        with self.lock:
            return self._apply(feats)

    def close(self):
        with self.lock:
            self.closed = True
            for db in self.connections:
                db.close()
            self.connections.clear()

    def _apply(self, feats):
        db = self._db()
        if db is None or not len(feats):
            return feats
        tags, statuses, plans = [], [], {}
        for i in range(len(feats)):
            refs = []
            if "source_refs" in feats.attrs:
                refs = json.loads(str(feats.attrs["source_refs"][i]))
            elif "src_record" in feats.attrs:
                refs = [{"dataset": str(feats.attrs.get("src_dataset", [""] * len(feats))[i]),
                         "record_id": str(feats.attrs["src_record"][i])}]
            ids = set()
            for ref in refs:
                m = re.fullmatch(r"w(\d+)(?:@(\d+))?", str(ref.get("record_id", "")))
                if m and any(x in str(ref.get("dataset", "")).lower() for x in ("osm", "openstreetmap")):
                    ids.add(int(m[1]))
            a = feats.coord_off[feats.ring_off[feats.part_off[i]]]
            b = feats.coord_off[feats.ring_off[feats.part_off[i + 1]]]
            ll = feats.lonlat[a:b]
            cache_key=(str(feats.ids[i]),tuple(sorted(ids)),hashlib.sha256(ll.tobytes()).digest())
            cached=self.match_cache.get(cache_key)
            if cached is not None:
                self.match_cache.move_to_end(cache_key)
                tag,status,sections,_=cached
                tags.append(tag);statuses.append(status)
                if sections!='null':plans[i]=json.loads(sections)
                continue
            matches = []
            for way_id in sorted(ids):
                row = db.execute("SELECT tags, geometry FROM ways WHERE id=?", (way_id,)).fetchone()
                if row is None and self.extra_path is not None:
                    row=db.execute('SELECT tags,geometry FROM extra.ways WHERE id=?',(way_id,)).fetchone()
                if row is None:
                    continue
                matched = partial_alignment(ll, json.loads(row[1]))
                if matched is not None:
                    orientation, start, end = matched
                    t = json.loads(row[0])
                    if "oneway" not in t and (t.get("junction") == "roundabout" or t.get("highway") == "motorway"):
                        t["oneway"] = "yes"
                    matches.append((t if orientation > 0 else reverse_tags(t), start, end))
            merged = merge_matches(matches) if matches else None
            if merged is not None:
                sections = control_sections(section_plan(matches) or [(0.,1.,merged)],ll)
                if sections and len(sections) > 1:
                    plans[i] = sections
                tags.append(json.dumps(merged, sort_keys=True, separators=(",", ":")))
                statuses.append("matched")
            else:
                tags.append("{}")
                statuses.append("ambiguous" if len(matches) > 1 else "unmatched")
            sections=json.dumps(plans.get(i),separators=(',',':'))
            size=len(tags[-1])+len(sections)+160
            self.match_cache[cache_key]=(tags[-1],statuses[-1],sections,size)
            self.match_cache_bytes+=size
            # Decoded map-cell eviction must not repeat expensive source
            # alignment. Keep the immutable result bounded per worker.
            while self.match_cache_bytes>16*1024*1024 or len(self.match_cache)>16384:
                _,old=self.match_cache.popitem(last=False)
                self.match_cache_bytes-=old[3]
        feats.attrs["osm_tags"] = np.asarray(tags, dtype=str)
        feats.attrs["osm_match"] = np.asarray(statuses, dtype=str)
        return split_features(feats, plans) if plans else feats
