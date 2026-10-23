"""Optional, immutable UK street-detail index. No network or per-frame spatial queries."""
from functools import lru_cache
import atexit
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import threading

import numpy as np

ROOT = Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
DEFAULT = ROOT / '.road-data/uk-context.sqlite'
_local = threading.local()
_connections=[]
_lock=threading.Lock()


def close():
    with _lock:
        for db in _connections:
            db.close()
        _connections.clear()


atexit.register(close)


def _db():
    path = Path(os.environ.get('BEAMNG_EARTH_UK_CONTEXT_DB', DEFAULT))
    if not path.is_file():
        return None
    if getattr(_local, 'path', None) != str(path):
        if getattr(_local, 'db', None):
            _local.db.close()
        _local.db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True,check_same_thread=False)
        with _lock:_connections.append(_local.db)
        _local.path = str(path)
    return _local.db


@lru_cache(maxsize=128)
def features(bounds, kinds=()):
    db = _db()
    if db is None:
        return ()
    x0, y0, x1, y1 = bounds
    query='SELECT f.osm_id,f.kind,f.tags,f.geometry FROM bounds b JOIN features f ON f.id=b.id '
    query+='WHERE b.maxx>=? AND b.minx<=? AND b.maxy>=? AND b.miny<=?'
    if kinds:
        query+=' AND f.kind IN ('+','.join('?' for _ in kinds)+')'
    try:
        rows=db.execute(query+' ORDER BY f.id LIMIT 4096',(x0,x1,y0,y1,*kinds)).fetchall()
    except sqlite3.DatabaseError:
        return ()
    return tuple((oid, k, json.loads(t), np.asarray(json.loads(g), float)) for oid, k, t, g in rows)


def near(frame, box, margin=30., kinds=()):
    import roadcontext
    x0, y0, x1, y1 = box
    la, lo, _ = frame.enu_to_geodetic(np.array([x0-margin, x1+margin]), np.array([y0-margin, y1+margin]), 0.)
    if not roadcontext.region_at(float(la.mean()), float(lo.mean())):
        return ()
    return features((float(lo.min()), float(la.min()), float(lo.max()), float(la.max())),kinds)


def contains(p, ring):
    if len(ring) < 4:
        return False
    if not np.array_equal(ring[0],ring[-1]):
        ring=np.vstack([ring,ring[0]])
    a, b = ring[:-1], ring[1:]
    dy = b[:, 1] - a[:, 1]
    hit = ((a[:, 1] > p[1]) != (b[:, 1] > p[1])) & (p[0] <
           a[:, 0] + (b[:, 0] - a[:, 0]) * (p[1] - a[:, 1]) / np.where(abs(dy) > 1e-12, dy, 1e-12))
    return bool(np.count_nonzero(hit) % 2)


def building_use(frame, ring, x0, y0, records):
    """Only an explicit enclosing amenity area or contained point identifies use.

    Never reclassify the next building just because it is near a school or forecourt.
    """
    la, lo, _ = frame.enu_to_geodetic(ring[:, 0] + x0, ring[:, 1] + y0, 0.)
    footprint = np.c_[lo, la]
    centre = footprint.mean(0)
    for _, k, _, geom in records:
        if k not in ('school', 'fuel','supermarket'):
            continue
        if (len(geom) >= 4 and contains(centre, geom)) or (len(geom) == 1 and contains(geom[0], footprint)):
            return k
    return None


def match_road(frame, q, lines, max_dist=25.):
    """Closest resolved road, projection and travel tangent; reject ambiguous parallel roads."""
    candidates = []
    for fid, sp, line, _ in lines:
        if sp.profile is None or len(line) < 2:
            continue
        d = np.diff(line[:, :2], axis=0)
        l2 = np.maximum((d*d).sum(1), 1e-9)
        t = np.clip(((q - line[:-1, :2]) * d).sum(1)/l2, 0., 1.)
        pp = line[:-1, :2] + t[:, None]*d
        dist = np.linalg.norm(pp-q, axis=1)
        i = int(dist.argmin())
        if dist[i] <= max_dist:
            z = line[i, 2] + t[i]*(line[i+1, 2]-line[i, 2])
            candidates.append((float(dist[i]), fid, sp, np.r_[pp[i], z], d[i]/math.sqrt(l2[i])))
    candidates.sort(key=lambda r: (r[0], r[1]))
    if not candidates:
        return None
    if len(candidates) > 1 and candidates[1][0] < candidates[0][0] + 1. and abs(candidates[0][4] @ candidates[1][4]) > .95:
        return None
    return candidates[0]


def cameras(frame, records, lines, box, surface_centres=True):
    """Mapped fixed cameras only. Unknown direction/limit => visible asset, no invented enforcement."""
    import furniture
    rows = []
    for oid, k, tags, geom in records:
        if k != 'speed_camera' or len(geom) != 1:
            continue
        x, y, _ = frame.geodetic_to_enu(geom[0, 1], geom[0, 0], 0.)
        q = np.array([x, y])
        if not (box[0] <= x < box[2] and box[1] <= y < box[3]):
            continue
        hit = match_road(frame, q, lines)
        if hit is None:
            continue
        _, fid, sp, p, tangent = hit
        value = tags.get('direction', tags.get('camera:direction', ''))
        direction = None
        facing = None
        if '_from' in tags:
            la0, lo0 = tags['_from'][1], tags['_from'][0]
            fx, fy, _ = frame.geodetic_to_enu(la0, lo0, 0.)
            v = p[:2] - [fx, fy]
            if np.linalg.norm(v) > 2.:
                direction = tangent * (1 if v @ tangent > 0 else -1)
        if value not in ('forward', 'backward'):
            try:
                deg = float(value)
                if 0 <= deg <= 360:
                    # OSM direction is the direction in which the camera looks.
                    facing = np.array([math.sin(math.radians(deg)), math.cos(math.radians(deg))])
            except (ValueError, TypeError):
                pass
        if direction is None and sp.oneway:
            direction = tangent * (1 if sp.dir > 0 else -1)
        f = direction if direction is not None else tangent
        side = np.array([-f[1], f[0]])
        visual = q.copy()
        # Road-centre nodes identify the road, not a pole in the live lane.
        if hit[0] < sp.width/2 + .6:
            visual = p[:2] + side*(sp.width/2+1.)
        limit = None
        v = tags.get('maxspeed', '')
        try:
            limit = float(v.lower().replace('mph', '').strip()) * (.44704 if 'mph' in v.lower() else 1/3.6)
        except (ValueError, AttributeError):
            if sp.profile.speed_mph is not None:
                limit = sp.profile.speed_mph * .44704
        offset=0. if sp.profile.mainline and not surface_centres else sp.profile.offset
        drive_centre=p[:2]+np.array([-tangent[1],tangent[0]])*offset
        row = {'id': oid, 'pos': [float(visual[0]), float(visual[1]), float(p[2])],
               'point': [float(drive_centre[0]), float(drive_centre[1]), float(p[2])], 'dir': f.tolist(),
               'yaw': furniture._yaw(*(np.array([-facing[1], facing[0]]) if facing is not None else side)),
               'width': sp.profile.drive,
               'motorway': sp.cls=='motorway',
               'limit': limit if limit and direction is not None and not tags.get('maxspeed:conditional')
                        and 'red light' not in tags.get('description','').lower() else None}
        rows.append(row)
    return rows


def street_props(frame, box, lines, elev):
    """Small mapped details, bounded per tile and instanced by the existing Forest streamer."""
    import furniture
    records = near(frame, box,kinds=('speed_camera','sign','bus_stop','post_box','fuel_pump','hedge'))
    rows = []
    import fast
    hedge_clear=fast.Others([(fid,sp.width/2+max(sp.profile.walk_left,sp.profile.walk_right)+.5,line)
                            for fid,sp,line,_ in lines if sp.profile is not None])
    for camera in cameras(frame, records, lines, box):
        if not camera['motorway']:
            rows.append(['ukcamera', *camera['pos'], camera['yaw'], 1., 3.75, 0.])
    signs = {'GB:601.1': 'ukgiveway', 'GB:602': 'ukstop', 'GB:671': 'uknsl',
             'GB:610': 'ukkeep_left', 'GB:510': 'ukroundabout', 'GB:545': 'ukschool'}
    hedge_count=0
    for _, k, tags, geom in records:
        if k=='hedge' and len(geom)>=2:
            if hedge_count>=128:continue
            x,y,_=frame.geodetic_to_enu(geom[:,1],geom[:,0],0.)
            line=np.c_[x,y,np.zeros(len(x))]
            length=furniture._arclen(line)[-1]
            pp,_=furniture._at(line,np.arange(0.,length,4.))
            for p in pp:
                if not (box[0]<=p[0]<box[2] and box[1]<=p[1]<box[3]):continue
                if not furniture._clear(p,hedge_clear,None):continue
                rows.append(['shrub',float(p[0]),float(p[1]),0.,0.,1.,1.5,0.])
                hedge_count+=1
                if hedge_count>=128:break
            continue
        if len(geom) != 1 or k not in ('bus_stop', 'post_box', 'sign', 'fuel_pump'):
            continue
        group = {'bus_stop': 'ukbus_stop', 'post_box': 'ukpostbox', 'fuel_pump': 'ukfuelpump'}.get(k)
        if k == 'sign':
            group = next((signs[v.strip()] for v in tags.get('traffic_sign','').split(';') if v.strip() in signs),None)
        if group is None:
            continue
        x,y,_=frame.geodetic_to_enu(geom[0,1],geom[0,0],0.)
        q=np.array([x,y])
        if not (box[0] <= x < box[2] and box[1] <= y < box[3]):
            continue
        hit=match_road(frame,q,lines,40.)
        yaw=0.
        if hit and k != 'fuel_pump':
            dist,_,sp,p,tangent=hit
            f=tangent*(1 if sp.dir>=0 else -1)
            side=np.array([-f[1],f[0]])
            if dist < sp.width/2+.6:
                q=p[:2]+side*(sp.width/2+1.)
            elif (q-p[:2])@side<0:
                side=-side
            yaw=furniture._yaw(*side)
            direction=tags.get('direction')
            try:
                angle=math.radians(float(direction))
                yaw=furniture._yaw(-math.cos(angle),math.sin(angle))
            except (TypeError,ValueError):
                pass
        elif k in ('sign','bus_stop'):
            continue
        rows.append([group,float(q[0]),float(q[1]),0.,yaw,1.,
                     1.25 if k=='post_box' else 2.2 if k=='fuel_pump' else 2.85,0.])
        if len(rows)>=128:
            break
    if rows:
        xy=np.array([r[1:3] for r in rows]);la,lo,_=frame.enu_to_geodetic(xy[:,0],xy[:,1],0.)
        z=frame.geodetic_to_enu(la,lo,elev(la,lo))[2]
        for row,h in zip(rows,z):row[3]=float(h)
    return rows


def decorate_buildings(frame, box, items):
    """Appearance only; do not change any ring, floor, height or roof dimensions."""
    import roadcontext
    la,lo,_=frame.enu_to_geodetic((box[0]+box[2])/2,(box[1]+box[3])/2,0.)
    if not roadcontext.region_at(float(la),float(lo)):
        return items
    records=near(frame,box,kinds=('fuel','school','supermarket','canopy'))
    for spec,_,_ in items:
        spec.uk_region=True
        use=building_use(frame,spec.ring,box[0],box[1],records)
        if spec.cls == 'school':
            use='school'
        spec.uk_use=use
        if use=='supermarket':
            la,lo,_=frame.enu_to_geodetic(spec.ring[:,0]+box[0],spec.ring[:,1]+box[1],0.)
            footprint=np.c_[lo,la]; centre=footprint.mean(0)
            spec.uk_brand='morrisons' if any(k=='supermarket' and 'morrisons' in (t.get('brand','')+' '+t.get('name','')).lower()
                and (contains(centre,geom) or len(geom)==1 and contains(geom[0],footprint))
                for _,k,t,geom in records) else None
        if use=='fuel':
            la,lo,_=frame.enu_to_geodetic(spec.ring[:,0].mean()+box[0],spec.ring[:,1].mean()+box[1],0.)
            spec.uk_canopy=any(k=='canopy' and contains(np.array([lo,la]),geom) for _,k,_,geom in records)
    return items
