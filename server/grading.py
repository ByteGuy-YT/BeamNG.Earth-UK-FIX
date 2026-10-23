"""Ground graded under roads (docs/ROADMAP.md v1.6; docs/research/2026-10-11-official-road-study.md §3, §5.3):
the physics block and the near mesh tiles sample one graded elevation, so tyres, DecalRoads and the
visible ground agree.

Per road (roads.road_specs; bridges, tunnels and off-ground segments are left out by it):
- along: the centreline height is the DEM sampled every PROFILE_STEP m and smoothed (Gaussian,
  SIGMA_M m; dirt roads DIRT_SIGMA_M), so grades stay real and small bumps go (the official maps:
  |2nd difference| per 10 m 0.02-0.1 m);
- across: flat over the core (the carriageway as a city street would have it, parking included, plus
  SHOULDER_M, or the sidewalk plus SIDEWALK_MARGIN_M on the classes that get sidewalks in towns, so a
  raised sidewalk slab sits on flat ground), then back to the natural ground over a transition of 2x the height difference (a
  1:2 cut or fill slope), clamped to [T_MIN, T_MAX] m;
- several roads at one point (junctions, divided carriageways) blend their targets by inverse distance
  from each centreline (BLEND_R), so they meet in a gradual slope.
The core width never depends on the land cover (it is taken as urban for every built road), and
each map cell's plan is made once per anchor and cached, so the block and the tiles built later from
the same anchor always agree.

GradedDem(dem, grader) is a drop-in for dem.Dem where only sample() is graded; use it for the block
and the levels <= 0 tiles only (coarser tiles sink under the block and cover far more ground).
"""
import logging
import math
import os
import threading
import time

import numpy as np

import mapcells
import roads as roadsmod

log = logging.getLogger("earthd.grading")

VERSION = 3
PROFILE_STEP = 2.0          # m between profile samples
SIGMA_M = 12.0              # m, profile smoothing of built roads
DIRT_SIGMA_M = 5.0          # m, profile smoothing of gravel / dirt roads
SHOULDER_M = 1.0            # m of flat shoulder beyond the carriageway, each side
SIDEWALK_MARGIN_M = 0.5     # m of flat ground beyond a sidewalk (roads.SIDEWALK_CLASSES)
T_MIN, T_MAX = 5.0, 12.0    # m, transition back to the natural ground (5: roads close together meet gently)
SLOPE_RUN = 2.0             # transition = SLOPE_RUN x the height difference (1:2 slope)
VERTEX_STEP = 4.0           # m between the plan's vertices (segments for the grading pass; linear between: at 16 m a
                            # crest or a sag was a kink every 16 m, 'bumpy roads, worst uphill and at speed' on r/BeamNG,
                            # 2026-10-17: a San Francisco street's slope changed 4.4 % rms per 2 m, 1.2 % at 4 m;
                            # grading a 1 km block 0.06 -> 0.14 s)
BUCKET = 32.0               # m, query-point buckets
PAIR_BATCH = 2_000_000      # (segment, point) pairs graded at once (bounds the temporaries, ~200 MB)
ROAD_LIFT = 0.04            # m the physics ground is raised under roads (see Grader.apply)
BLEND_R = 4.0               # m: roads near each other blend their targets by 1 / (1 + (d / BLEND_R)^2)
PROFILE_ZOOM = 15           # DEM zoom of the profiles (one zoom for every caller)
WALL_CUT_M = 2.0            # a road cut deeper than this into the ground: a retaining wall at the core's edge
WALL_T_M = 0.8              # (roadmesh.retaining_walls) and the ground at its natural height right behind it, over
                            # this; on a 1:2 slope Central Park's sunken transverse was a grassy ditch between its
                            # stone walls (the user, 2026-10-17)
WALL_FLAT_M = 2.0           # ... after one terrain grid step at the road's level behind the wall: rising at the wall
                            # itself, the 2 m grid's triangles stood as dark wedges in front of its face; the wall's
                            # top (roadmesh.WALL_THICK_M) covers the strip
TUNNEL_TAG = ":tun"          # in the fid of the tunnels' own plans (open sections, mouths): apply(roads_only) skips them
MOUTH_PLAN_M = 4.0          # m into a tunnel from a portal its floor is a grading plan too (Grader._mouth_plans)
TUNNEL_KEEP_IN_M = 3.0      # (roads.LOW_HOLE_M: a low arch's mouths, flat at its floor)
TUNNEL_KEEP_M = 5.0         # m beside a covered tunnel's road where the ground over it is left ungraded
WALL_AHEAD_M = 2.5          # ... only beside a segment or this little past its end (a joint between two: VERTEX_STEP)
RETRY_S = 60.0              # s before a cell whose road data failed is asked for again
# KyzoFox 1.5.4: overpass approach ramps. A short bridge over a road had its ends on the ground on both sides
# (the DEM is too coarse for the real approach embankments), and roads.deck_profile_once caps how steeply a deck climbs
# from its ends: the deck over I-20 near Temple, GA reached ~2.5 m over the lanes (the user's truck hit it,
# 2026-10-19). The roads leading onto such a bridge are now graded up to the height the deck needs, over a smooth ramp,
# as real approach fills are: the bridge's ends (sampled from this graded ground) then sit high enough.
APPROACH_ON = os.environ.get("BNE_APPROACH_RAMPS", "on") != "off"
APPROACH_GRADE = float(os.environ.get("BNE_APPROACH_GRADE", "0.05"))   # steepest grade of a ramp (its middle)
APPROACH_MAX_LIFT = 10.0    # m an abutment is raised at most
APPROACH_MIN_LIFT = 0.5     # m: less is left as it is
APPROACH_MIN_RUN = 30.0     # m: the shortest ramp
APPROACH_MAX_RUN = 320.0    # m: the longest ramp
APPROACH_TOUCH_M = 2.5      # m: a road whose end is this close to an abutment leads onto the bridge
APPROACH_MIN_CROSS_M = 6.0  # m: a road crossing a deck closer than this to its end is a junction at grade (not under it)
APPROACH_FLAT_M = 20.0      # m from an abutment the deck needs its full clearance (beyond: it may fall at DECK_GRADE)
APPROACH_MARGIN_M = 0.3     # m over the clearance (the deck profile's smoothing takes a little off near its ends)
APPROACH_SKIP = ("motorway", "trunk")   # never raised (nor their links): the overpasses over them are what is
APPROACH_GAP_M = 1.0        # m of flat ground kept between a ramp's fill slope and the road beside it
APPROACH_CELL_M = 450.0     # m: a plan's end this far from a cell cannot raise what that cell's queries see


def smooth_profile(z, step, sigma):
    """Gaussian smoothing of a profile sampled every `step` m (reflected at the ends). Pure."""
    z = np.asarray(z, np.float64)
    import fast
    if fast.AVAILABLE:          # the Rust loop (~7000 roads a 9-tile set; equal to ~1e-12 m)
        return fast._ef.smooth_profile(np.ascontiguousarray(z), float(step), float(sigma))
    if len(z) < 3 or sigma <= 0:
        return z.copy()
    r = int(math.ceil(3 * sigma / step))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) * step / sigma) ** 2)
    k /= k.sum()
    pad = np.pad(z, r, mode="reflect") if len(z) > r else np.pad(z, r, mode="edge")
    return np.convolve(pad, k, mode="valid")


def resample(xy, step):
    """Points every `step` m along a polyline (xy (k, 2)), the last point kept, and their arc lengths."""
    import fast
    if fast.AVAILABLE and len(xy):
        return fast._ef.resample(np.ascontiguousarray(np.asarray(xy, np.float64)[:, :2]), float(step))
    seg = np.hypot(*np.diff(xy, axis=0).T)
    s = np.r_[0.0, np.cumsum(seg)]
    if s[-1] <= 0:
        return xy[:1].copy(), np.zeros(1)
    t = np.r_[np.arange(0.0, s[-1], step), s[-1]]
    return np.stack([np.interp(t, s, xy[:, 0]), np.interp(t, s, xy[:, 1])], axis=1), t


class Plan:
    """One road's grading: vertices (n, 2) in the frame's ENU metres, their target heights, core half width."""
    __slots__ = ("xy", "z", "half", "bbox", "end_ids", "caps")

    def __init__(self, xy, z, half, end_ids=(None,None), caps=(True,True)):
        self.xy, self.z, self.half = xy, z, float(half)
        self.end_ids=tuple(end_ids)
        self.caps=tuple(caps)
        pad = half + T_MAX
        self.bbox = (xy[:, 0].min() - pad, xy[:, 1].min() - pad, xy[:, 0].max() + pad, xy[:, 1].max() + pad)


def plan_road(frame, lonlat, spec, elev):
    """The Plan of one road part (lonlat (k, 2)); elev(lat, lon) -> m at PROFILE_ZOOM. Pure given elev."""
    return plan_roads(frame, [(lonlat, spec)], elev)[0]


def plan_roads(frame, parts, elev):
    """plan_road for many (lonlat, spec) parts with one elev call (its cost is per call). Pure given elev."""
    if not parts:
        return []
    ll = np.concatenate([lonlat for lonlat, _ in parts])
    E, N, _ = frame.geodetic_to_enu(ll[:, 1], ll[:, 0], 0.0)
    prof, k = [], 0
    for lonlat, spec in parts:
        m = len(lonlat)
        xy, _ = resample(np.stack([E[k:k + m], N[k:k + m]], axis=1), PROFILE_STEP)
        k += m
        prof.append(xy if len(xy) >= 2 else None)
    pts = [xy for xy in prof if xy is not None]
    if not pts:
        return [None] * len(parts)
    allxy = np.concatenate(pts)
    la, lo, _ = frame.enu_to_geodetic(allxy[:, 0], allxy[:, 1], 0.0)
    zall = np.asarray(elev(la, lo), np.float64)
    out, k = [], 0
    for (lonlat, spec), xy in zip(parts, prof):
        if xy is None:
            out.append(None)
            continue
        z = zall[k:k + len(xy)]
        k += len(xy)
        out.append(_plan(xy, z, spec))
    return out


def _plan(xy, z, spec):
    built = spec.kind in roadsmod.BUILT
    zs = smooth_profile(z, PROFILE_STEP, SIGMA_M if built else DIRT_SIGMA_M)
    # thin to VERTEX_STEP (the profile stays smooth between: linear in the grading pass)
    every = max(1, int(round(VERTEX_STEP / PROFILE_STEP)))
    keep = np.r_[np.arange(0, len(xy) - 1, every), len(xy) - 1]
    # the carriageway as a city street would have it (never from the land cover), or the measured one
    width = spec.width if spec.profile is not None else max(spec.width, roadsmod.carriageway(spec.cls, spec.kind, True, None, spec.oneway)) if built else spec.width
    if spec.profile is not None and spec.profile.surface_offset:
        xy=roadsmod.offset_polyline(np.c_[xy,np.zeros(len(xy))],spec.profile.surface_offset)[:,:2]
    return Plan(xy[keep], zs[keep], width / 2 + shoulder(spec))


def shoulder(spec):
    """m of flat ground beyond the carriageway edge, each side. Like the core width, never from the land
    cover: a road class that gets sidewalks in towns keeps a sidewalk-wide verge everywhere."""
    if spec.profile is not None:
        return max(spec.profile.walk_left, spec.profile.walk_right) + SIDEWALK_MARGIN_M
    if spec.kind not in roadsmod.BUILT:
        return 0.0
    if spec.cls in roadsmod.SIDEWALK_CLASSES or (spec.cls == "trunk" and (not spec.oneway
                                                                          or roadsmod._arterial(spec))):
        return spec.walk + SIDEWALK_MARGIN_M
    return SHOULDER_M


class Grader:
    """The road plans of one anchor frame, per map cell, made once (worker threads; it fetches the road
    cells it lacks)."""

    def __init__(self, frame, mapdata, elev, widths=None, structure_elev=None):
        self.frame, self.md, self.elev, self.widths = frame, mapdata, elev, widths
        self.cells = {}
        self.failed = {}        # cell key -> monotonic time of the last failed fetch
        self.lock = threading.Lock()
        self.key_locks = {}     # cell key -> Lock: one thread plans a cell, the others wait for it
        self.covers = {}        # cell key -> [(xy (k, 2), half width)]: the tunnels whose ground over them stays
        self.opens = {}         # cell key -> [(xy (k, 2), Spec)]: the tunnels' open sections (roads in the open)
        import ukvertical
        self.uk_vertical = ukvertical.Model(frame, mapdata, elev)
        self.base_cells = {}
        self.base_specs = {}
        self.resolved_plans = {}
        self.structure_elev=structure_elev or elev
        self.tunnel_model = roadsmod.TunnelProfiles(frame,
            lambda k: self.md.cell(k,layers=('roads',),kind='demand').layers.get('roads'),self.structure_elev)
        self.tunnel_model.ends = self._base_height
        self.bridge_model=roadsmod.BridgeProfiles(frame,
            lambda k:self.md.cell(k,layers=('roads',),kind='demand').layers.get('roads'),self._base_height)
        self.bridge_model.vertical=self.uk_vertical

    def _base_height(self, lat, lon):
        """Portal levels from surface roads only, without recursing into tunnels."""
        lat=np.asarray(lat,float);lon=np.asarray(lon,float)
        e,n,_=self.frame.geodetic_to_enu(lat.ravel(),lon.ravel(),0.)
        plans=[];seen=set()
        low=np.array([e.min(),n.min()]);high=np.array([e.max(),n.max()])
        pad=.0005
        for key in mapcells.cells_for_bbox(float(lat.min())-pad,float(lon.min())-pad,
                                          float(lat.max())+pad,float(lon.max())+pad):
            for fid,p in self._base_cell(key):
                ident=(fid,*p.xy[0])
                if ident not in seen:
                    if (np.asarray(p.bbox[2:])<low).any() or (np.asarray(p.bbox[:2])>high).any():continue
                    plans.append(self._resolve_plan(fid,p));seen.add(ident)
        base=np.asarray(self.structure_elev(lat,lon),float)
        return grade_points(e,n,base.ravel(),plans).reshape(base.shape)

    def _base_cell(self, key, feats=None):
        with self.lock:got=self.base_cells.get(key)
        if got is not None:return got
        if feats is None:feats=self.md.cell(key,layers=('roads',),kind='demand').layers.get('roads')
        plans=[];pspecs=[]
        if feats is not None and len(feats):
            specs=roadsmod.road_specs(feats,self._urban,self.widths);parts=[];ids=[]
            for i,sp in enumerate(specs):
                if sp is None:continue
                for ring in roadsmod.ground_parts(feats,i):
                    parts.append((np.asarray(ring,float),sp));ids.append(str(feats.ids[i]))
            by_fid={str(feats.ids[i]):i for i in range(len(feats))}
            for fid,part,p in zip(ids,parts,plan_roads(self.frame,parts,self.elev)):
                if p is not None:
                    # Connector identities belong to mapped centreline ends.
                    # Reconstructing them from a shoulder-shifted pavement
                    # missed every motorway connector by 1.4 m, disconnecting
                    # otherwise adjoining source sections in the height model.
                    p.end_ids=roadsmod._route_end_ids(feats,by_fid[fid],part[0])
                    plans.append((fid,p));pspecs.append(part[1])
            for (_,p),sp in zip(plans,pspecs):self.base_specs[p]=sp
            if APPROACH_ON and plans:
                try:self._lift_approaches(key,plans,pspecs)
                except Exception as ex:log.debug('approaches of %s: %s',key,ex)
        with self.lock:
            self.base_cells.setdefault(key,plans)
            return self.base_cells[key]

    def _resolve_plan(self,fid,p):
        """Resolve a complete source road only when its corridor is requested.

        A map cell contains complete ways extending kilometres outside it.
        Eagerly solving all of them forced one local block to prepare bridges
        across dozens of distant cells in each worker process.
        """
        sp=self.base_specs.get(p)
        if sp is None or sp.profile is None:return p
        with self.uk_vertical.lock:
            if p not in self.resolved_plans:
                rows=[(fid,p)];self.uk_vertical.adjust(rows,[sp])
                self.resolved_plans[p]=rows[0][1]
            return self.resolved_plans[p]

    def _urban(self, lat, lon):
        """UK interpretation uses real land cover here too; worldwide legacy plans stay unchanged."""
        import roadcontext
        if not any(roadcontext.region_at(float(la), float(lo)) for la, lo in zip(np.ravel(lat)[::max(1, np.size(lat) // 8)], np.ravel(lon)[::max(1, np.size(lon) // 8)])):
            return np.zeros(np.shape(lat), bool)
        out = np.zeros(np.shape(lat), bool)
        for key in {mapcells.cell_of(float(la), float(lo)) for la, lo in zip(np.ravel(lat), np.ravel(lon))}:
            r = self.md.cell(key, layers=("landcover",)).layers.get("landcover")
            if r is not None:
                out |= r.sample(lon, lat) == 50
        return out

    def _cell_plans(self, key):
        with self.lock:
            got = self.cells.get(key)
            kl = self.key_locks.setdefault(key, threading.Lock())
        if got is not None:
            return got
        with kl:
            return self._plan_cell(key)

    def _plan_cell(self, key):
        with self.lock:
            got = self.cells.get(key)
            failed = self.failed.get(key)
        if got is not None:
            return got
        if failed is not None and time.monotonic() - failed < RETRY_S:
            return []               # offline: no block waits on the same failing fetch again
        try:
            feats = self.md.cell(key, layers=("roads",), kind="demand").layers.get("roads")
        except Exception as e:      # no road data: ungraded (asked again after RETRY_S)
            log.debug("grading: roads of %s: %s: %s", key, type(e).__name__, e)
            with self.lock:
                self.failed[key] = time.monotonic()
            return []
        plans = []
        if feats is not None and len(feats):
            plans = list(self._base_cell(key,feats))
            self._global_approaches(key,feats,plans)
            secs = self._tunnel_sections(feats, key, [p for _f, p in plans])
            plans.extend((fid + TUNNEL_TAG, Plan(xy, z, spec.width / 2 + shoulder(spec)))
                         for fid, spec, xy, z, k in secs if k == 0)
            plans.extend(self._mouth_plans(secs))
            covers = self._covered_tunnels_from_sections(secs)
            opens = [(xy, spec) for _f, spec, xy, _z, k in secs if k == 0]
        else:
            covers, opens = [], []
        with self.lock:
            self.cells.setdefault(key, plans)
            self.covers.setdefault(key, covers)
            self.opens.setdefault(key, opens)
            return self.cells[key]

    def _global_approaches(self,key,feats,plans):
        """Connect non-UK surface approaches to the shared bridge solution.

        The model reads base surface plans only, so this cannot recurse into
        its own approach grading or an underground road. A lower crossing is
        not a graph connection and cannot be dug down to fit the upper road.
        """
        if not plans or not any(sp is not None and sp.profile is None for sp in roadsmod.bridge_specs(feats)):return
        bp=self.bridge_model
        bp.parts([feats],(-np.inf,-np.inf,np.inf,np.inf))
        parts=[v for v in bp.done.values() if v[0].profile is None and np.isfinite(v[2]).all()]
        if not parts:return
        _,be,_=roadsmod._chain_graph([v[1] for v in parts]);degree={}
        for a,b,_ in be:
            for node in (a,b):degree[node]=degree.get(node,0)+1
        targets=[];target_nodes=set()
        for (_,xy,z,_),(a,b,_) in zip(parts,be):
            for node,at in ((a,0),(b,-1)):
                # A surface approach can branch from an interior bridge node
                # too. The mapped identity, not just bridge degree, determines
                # whether it belongs to this height at the junction.
                if node in target_nodes:continue
                target_nodes.add(node)
                la,lo,h=self.frame.enu_to_geodetic(*xy[at,:2],float(z[at]))
                targets.append((xy[at,:2],float(h),getattr(xy,'end_ids',(None,None))[at]))
        if not targets:return
        lon0,lat0,lon1,lat1=key.bounds();pad=APPROACH_MAX_RUN/111320.;pl=pad/max(.05,math.cos(math.radians((lat0+lat1)/2)))
        network=[];seen=set()
        for ck in sorted(mapcells.cells_for_bbox(lat0-pad,lon0-pl,lat1+pad,lon1+pl),key=str):
            for fid,p in self._base_cell(ck):
                signature=(fid,*np.round(p.xy[0],3),*np.round(p.xy[-1],3))
                if signature not in seen:network.append((fid,p));seen.add(signature)
        nodes,edges,adj=roadsmod._chain_graph([roadsmod.RouteLine(p.xy,p.end_ids) for _,p in network]);nodes=np.asarray(nodes)
        if not len(nodes):return
        seeds=[]
        identities={}
        for (_,p),(a,b,_) in zip(network,edges):
            for node,identity in zip((a,b),p.end_ids):
                if identity is not None:identities.setdefault(identity,set()).add(node)
        for xy,top,identity in targets:
            candidates=identities.get(identity,()) if identity is not None else range(len(nodes))
            node=min(candidates,key=lambda j:np.linalg.norm(nodes[j]-xy),default=None)
            if node is None or np.linalg.norm(nodes[node]-xy)>(2.5 if identity is not None else .6):continue
            base=min((p.z[0 if a==node else -1] for (_,p),(a,b,_) in zip(network,edges) if node in (a,b)),default=top)
            delta=top-base
            if delta<.01:continue
            reach=max(APPROACH_MIN_RUN,delta*math.pi/(2*APPROACH_GRADE))
            seeds.append((roadsmod._dijkstra(adj,{node:0.}),top,reach))
        if not seeds:return
        index={(fid,*np.round(p.xy[0],3),*np.round(p.xy[-1],3)):e for (fid,p),e in zip(network,edges)}
        for i,(fid,p) in enumerate(plans):
            edge=index.get((fid,*np.round(p.xy[0],3),*np.round(p.xy[-1],3)))
            if edge is None:continue
            a,b,s=edge;raise_by=np.zeros(len(s))
            for distances,top,reach in seeds:
                d=np.minimum(distances[a]+s,distances[b]+s[-1]-s)
                blend=.5*(1+np.cos(np.pi*np.clip(d/reach,0.,1.)))
                raise_by=np.maximum(raise_by,np.maximum(0.,top-p.z)*blend)
            if raise_by.max()>.001:plans[i]=(fid,Plan(p.xy,p.z+raise_by,p.half,p.end_ids))

    def _lift_approaches(self, key, plans, specs):
        """Raise, in place, the plans of the roads leading onto overpasses (APPROACH_ON). A road is raised where one of
        its ends is a bridge's abutment that must go up for the deck to clear the road under it (_end_lift); the raise
        falls off along the road (approach_add) and never comes nearer another road than its fill slope allows. Only
        what the plan's own line and the map around its ends say counts, the same in every cell that plans it (a long
        road is planned in each cell it passes; two cells raising the same road differently drew the road under a
        raised ground, 2026-10-20 I-20 in Greene County, AL). Major roads (APPROACH_SKIP) are never raised."""
        # UK grade separation is solved jointly with the lower road and terrain
        # by uk_vertical; do not add another clearance ramp on top of it.
        for i, (fid, p) in enumerate(plans):
            spec = specs[i]
            if spec is None or spec.profile is not None or spec.cls in APPROACH_SKIP or _is_link(spec):
                continue
            add = None
            for at_end in (False, True):
                e = p.xy[-1] if at_end else p.xy[0]
                if not self._near_cell(key, e):
                    continue
                got = self._end_lift(e)
                if got is None:
                    continue
                lift, others = got
                a = approach_add(p.xy, at_end, lift, p.half, others)
                if a is not None:
                    add = a if add is None else np.maximum(add, a)
            if add is not None:
                plans[i] = (fid, Plan(p.xy, p.z + add, p.half,p.end_ids))

    def _lift_uk_approaches(self, key, plans, specs):
        """Continuous bridge approaches across source-way and map-cell boundaries.

        A ramp belongs to the connected road, not one OSM section. Major roads can
        be the overpass too. Use nearby raw network geometry for routing (never
        recursively grade a neighbour), then apply the same distance-based fill
        to every affected local plan. Existing real embankments need no lift.
        """
        lon0, lat0, lon1, lat1 = key.bounds()
        pad = (APPROACH_MAX_RUN + 40.) / 111320.
        padlon = pad / max(.05, math.cos(math.radians((lat0 + lat1) / 2)))
        keys = mapcells.cells_for_bbox(lat0 - pad, lon0 - padlon, lat1 + pad, lon1 + padlon)
        ground, bridges, levels, seen_g, seen_b = [], [], [], set(), set()
        for ck in sorted(set(keys) | {key}, key=str):
            c = self._cell_enu(ck)
            for line, half, cls in c["ground"]:
                sig = tuple(np.round(np.r_[line[0], line[-1]], 3)) + (len(line),)
                if sig not in seen_g:
                    seen_g.add(sig)
                    ground.append(line)
            for j, line in enumerate(c["bridges"]):
                sig = tuple(np.round(np.r_[line[0], line[-1]], 3)) + (len(line),)
                if sig not in seen_b:
                    seen_b.add(sig)
                    bridges.append(line)
                    levels.append(c.get("bridge_levels", [1.] * len(c["bridges"]))[j])
        if not ground or not bridges:
            return
        nodes, edges, adj = roadsmod._chain_graph(ground)
        bn, be, ba = roadsmod._chain_graph(bridges)
        ends = np.array([p for p, links in zip(bn, ba) if len(links) == 1])
        if not len(ends):
            return
        nodes = np.asarray(nodes)
        seeds = []
        for node, p in enumerate(nodes):
            if np.linalg.norm(ends - p, axis=1).min() <= APPROACH_TOUCH_M:
                got = self._end_lift(p)
                if got is not None:
                    lift, _ = got
                    seeds.append((node, p, lift))
        if not seeds:
            return
        # Adjacent carriageways of one bridge are merged to one deck height. Their
        # approach fills must share that target too, otherwise the lower ends stay
        # pinned while the interior jumps up to the other carriageway's deck.
        points = np.array([p for _, p, _ in seeds])
        la, lo, _ = self.frame.enu_to_geodetic(points[:, 0], points[:, 1], 0.)
        base = np.asarray(self.elev(la, lo), float)
        targets = paired_abutment_targets(points, base + [lift for _, _, lift in seeds], bridges, levels)
        seeds = [(roadsmod._dijkstra(adj, {node: 0.}), z + min(APPROACH_MAX_LIFT, max(lift, target - z)),
                  min(APPROACH_MAX_LIFT, max(lift, target - z)))
                 for (node, _, lift), target, z in zip(seeds, targets, base)]
        for i, (fid, p) in enumerate(plans):
            if specs[i] is None or specs[i].profile is None:
                continue
            nearest = [int(np.argmin(np.linalg.norm(nodes - q, axis=1))) for q in (p.xy[0], p.xy[-1])]
            if any(np.linalg.norm(nodes[n] - q) > .6 for n, q in zip(nearest, (p.xy[0], p.xy[-1]))):
                continue
            s = np.r_[0., np.cumsum(np.linalg.norm(np.diff(p.xy, axis=0), axis=1))]
            add = np.zeros(len(s))
            for distances, target, lift in seeds:
                d = np.minimum(distances[nearest[0]] + s, distances[nearest[1]] + s[-1] - s)
                run = float(np.clip(lift * math.pi / (2 * APPROACH_GRADE), APPROACH_MIN_RUN, APPROACH_MAX_RUN))
                blend = .5 * (1. + np.cos(math.pi * np.clip(d / run, 0., 1.)))
                # Clearance is an absolute target. Adding a raw-DEM lift again to
                # an already smoothed embankment doubled the fill at short spans.
                add = np.maximum(add, np.maximum(0., target - p.z) * blend)
            if add.max() > 1e-3:
                plans[i] = (fid, Plan(p.xy, p.z + add, p.half))

    def _near_cell(self, key, xy):
        """Is xy (ENU) within APPROACH_CELL_M of cell key? (A plan's far end cannot raise anything that cell's
        queries see: its ramp ends APPROACH_MAX_RUN from it.)"""
        la, lo, _ = self.frame.enu_to_geodetic(np.array([xy[0]]), np.array([xy[1]]), 0.0)
        lon0, lat0, lon1, lat1 = key.bounds()
        la, lo = float(la[0]), float(lo[0])
        dla = max(lat0 - la, la - lat1, 0.0) * 111320.0
        dlo = max(lon0 - lo, lo - lon1, 0.0) * 111320.0 * math.cos(math.radians(la))
        return math.hypot(dla, dlo) <= APPROACH_CELL_M

    def _end_lift(self, xy):
        """(lift m, other road lines [(xy (k, 2), half width)]) when the road end xy is a bridge abutment to raise, else
        None. A pure function of the map around the bridge (its cells, fetched as needed), cached per point."""
        k = (round(float(xy[0]) * 2), round(float(xy[1]) * 2))
        with self.lock:
            if not hasattr(self, "end_cache"):
                self.end_cache = {}
            if k in self.end_cache:
                return self.end_cache[k]
        res = None
        try:
            res = self._end_lift_calc(np.asarray(xy, np.float64))
        except Exception as e:      # no ramp rather than no grading
            log.debug("grading: approach at %s: %s: %s", k, type(e).__name__, e)
        with self.lock:
            return self.end_cache.setdefault(k, res)

    def _cell_enu(self, k):
        """Cell k's road parts in the anchor frame, made once: {"bridges": [line (k, 2)], "ends": (n, 2) bridge end points,
        "end_of": [bridge index per end], "ground": [(line, half width, cls)]} (the longest copy of each part)."""
        with self.lock:
            if not hasattr(self, "enu_cache"):
                self.enu_cache = {}
            got = self.enu_cache.get(str(k))
        if got is not None:
            return got
        parts, levels = {}, {}
        f = self.md.cell(k, layers=("roads",), kind="demand").layers.get("roads")
        if f is not None and len(f):
            bs = roadsmod.bridge_specs(f)
            rs = roadsmod.road_specs(f, self._urban, self.widths)
            for i in range(len(f)):
                fid = str(f.ids[i])
                lvls = roadsmod.bridge_levels(f, i) if bs[i] is not None else ()
                for kind, sp, ps in (("bridge", bs[i], roadsmod.bridge_parts(f, i) if bs[i] is not None else ()),
                                     ("ground", rs[i], roadsmod.ground_parts(f, i) if rs[i] is not None else ())):
                    for j, ring in enumerate(ps):
                        ring = np.asarray(ring, np.float64)
                        kk = (fid, kind, j)
                        if len(ring) >= 2 and (kk not in parts or len(ring) > len(parts[kk][0])):
                            parts[kk] = (ring, sp)
                            levels[kk] = lvls[j] if kind == "bridge" and j < len(lvls) else 1.
        bridges, ground, ends, end_of, bridge_levels = [], [], [], [], []
        for (fid, kind, j), (ring, sp) in sorted(parts.items()):
            e, n, _ = self.frame.geodetic_to_enu(ring[:, 1], ring[:, 0], 0.0)
            line = np.stack([np.asarray(e), np.asarray(n)], axis=1)
            if kind == "bridge":
                end_of += [len(bridges), len(bridges)]
                ends += [line[0], line[-1]]
                bridges.append(line)
                bridge_levels.append(levels[(fid, kind, j)])
            else:
                ground.append((line, sp.width / 2 + shoulder(sp), sp.cls))
        out = {"bridges": bridges, "ground": ground, "end_of": end_of,
               "bridge_levels": bridge_levels,
               "ends": np.asarray(ends, np.float64).reshape(-1, 2)}
        with self.lock:
            if len(self.enu_cache) > 64:
                self.enu_cache.clear()
            self.enu_cache[str(k)] = out
        return out

    def _end_lift_calc(self, xy):
        la, lo, _ = self.frame.enu_to_geodetic(np.array([xy[0]]), np.array([xy[1]]), 0.0)
        home = mapcells.cell_of(float(la[0]), float(lo[0]))
        hc = self._cell_enu(home)
        if not len(hc["ends"]):
            return None
        d = np.hypot(hc["ends"][:, 0] - xy[0], hc["ends"][:, 1] - xy[1])
        hit = np.flatnonzero(d <= APPROACH_TOUCH_M)
        if not len(hit):
            return None
        bridge = hc["bridges"][hc["end_of"][int(hit[0])]]
        # the bridge's own cells (a few, it is short): the roads crossing under it and the parts it joins
        lam, lom, _ = self.frame.enu_to_geodetic(bridge[:, 0], bridge[:, 1], 0.0)
        pad = 50.0 / 111320.0
        padlon = pad / max(0.05, math.cos(math.radians(float(np.mean(lam)))))
        keys = sorted(set(mapcells.cells_for_bbox(float(lam.min()) - pad, float(lom.min()) - padlon,
                                                  float(lam.max()) + pad, float(lom.max()) + padlon)) | {home}, key=str)
        cs = [self._cell_enu(k) for k in keys]
        bridges = [b for c in cs for b in c["bridges"]]
        lo_b, hi_b = bridge.min(0) - APPROACH_MAX_RUN - 50.0, bridge.max(0) + APPROACH_MAX_RUN + 50.0
        ground, others, seen = [], [], set()
        for c in cs:
            for line, half, _cls in c["ground"]:
                key = (round(float(line[0, 0]), 1), round(float(line[0, 1]), 1), len(line))
                if key in seen:
                    continue
                seen.add(key)
                if (line.max(0) < lo_b).any() or (line.min(0) > hi_b).any():
                    continue                # nowhere near the bridge or its ramps
                ground.append(line)
                touches = min(np.hypot(*(line[0] - xy)), np.hypot(*(line[-1] - xy))) <= APPROACH_TOUCH_M
                under = bool(roadsmod._crossings([bridge], [line]))
                # the roads beside the ramp, which its fill slope must not reach (not the ones the bridge spans: its
                # abutment stands between)
                if not touches and not under:
                    others.append((line, half))

        def z_at(p):
            la_, lo_, _ = self.frame.enu_to_geodetic(p[:, 0], p[:, 1], 0.0)
            return np.asarray(self.elev(la_, lo_), np.float64)
        for end, lift in bridge_lifts(bridge, bridges, ground, z_at):
            if np.hypot(*(end - xy)) <= APPROACH_TOUCH_M:
                return lift, others
        return None

    def _longest(self, fid, j, ring, key):
        """Part j of tunnel fid as the cells at its ends have it, the longest (a part comes clipped differently in
        the cells around: graded as the 30 m piece, 97th Street's 45 m arch got an open road graded in it; the
        same rule as roads.BridgeProfiles._load, 2026-10-17)."""
        best = ring
        for p in (ring[0], ring[-1]):
            ck = mapcells.cell_of(float(p[1]), float(p[0]))
            if key is not None and str(ck) == str(key):
                continue
            try:
                f = self.md.cell(ck, layers=("roads",), kind="demand").layers.get("roads")
            except Exception:
                continue
            if f is None or not len(f):
                continue
            ids = [str(x) for x in f.ids]
            if fid not in ids:
                continue
            i = ids.index(fid)
            parts = roadsmod.tunnel_parts(f, i)
            if j < len(parts) and len(parts[j]) > len(best):
                best = parts[j]
        return best

    def _tunnel_sections(self, feats, key=None, road_plans=()):
        """[(fid, spec, xy, z, kind)] of the tunnels' sections (roads.tunnel_sections on the ungraded ground, its
        ends graded by road_plans: the cell's road Plans, as roads.TunnelProfiles.ends grades them with the roads'
        plans alone): kind 0 an open road at z, 1 a low arch, 2 a full tunnel."""
        out = []
        # Terrain, rendered tubes, collision floors and portal holes consume the
        # same complete chain. Re-solving each feature with both ends at ground
        # level created false portals and vertical drops inside urban tunnels.
        model=self.tunnel_model
        whole=roadsmod.BridgeProfiles.parts(model,[feats],(-np.inf,-np.inf,np.inf,np.inf))
        for fid,spec,xy,z,_ in whole:
            for n,(a,b,kind) in enumerate(model.sections.get(fid,())):
                if b>a:out.append((f'{fid}#{n}',spec,np.asarray(xy)[a:b+1],np.asarray(z)[a:b+1],kind))
        return out

    def _mouth_plans(self,secs):
        """(fid, Plan) of the covered sections' mouths: the floor MOUTH_PLAN_M into the tube from a portal (where an
        open section or nothing comes before / after it): the ground at the portal graded to the road on both sides
        of it (the grading faded from the road's plan into the ungraded hill there, and the road tile and the
        terrain block, sampled at different zooms, came out a few cm apart: the block poked through the road
        outside 97th Street's arch, 2026-10-17)."""
        out = []
        for n, (fid, spec, xy, z, kind) in enumerate(secs):
            if not kind or len(xy) < 2:
                continue
            same = lambda m: 0 <= m < len(secs) and secs[m][0] == fid     # noqa: E731
            s = np.r_[0.0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
            hw = spec.width / 2 + shoulder(spec)
            for at_start in (True, False):
                if not self.tunnel_model.mouth(fid)[0 if at_start else 1]:
                    continue                    # connected underground, not a surface entrance
                nb = n - 1 if at_start else n + 1
                if same(nb) and secs[nb][4] != 0:
                    continue                    # inside the hill: a full tunnel goes on
                if at_start:
                    m = s <= MOUTH_PLAN_M
                    t = np.interp(MOUTH_PLAN_M, s, np.arange(len(s)))
                else:
                    m = s >= s[-1] - MOUTH_PLAN_M
                    t = np.interp(s[-1] - MOUTH_PLAN_M, s, np.arange(len(s)))
                i0 = int(np.floor(t))
                p = xy[i0] + (t - i0) * (xy[min(i0 + 1, len(xy) - 1)] - xy[i0])
                pz = z[i0] + (t - i0) * (z[min(i0 + 1, len(z) - 1)] - z[i0])
                if at_start:
                    pxy, pzz = np.r_[xy[m], p[None]], np.r_[z[m], pz]
                else:
                    pxy, pzz = np.r_[p[None], xy[m]], np.r_[pz, z[m]]
                if len(pxy) >= 2:
                    out.append((fid + TUNNEL_TAG + ("m0" if at_start else "m1"), Plan(pxy, pzz, hw)))
        return out

    def _covered_tunnels(self, feats):
        """[(xy, half width)] of the tunnels' covered sections (not open roads): the grading leaves the ground over
        them as it is (apply): the approaches' grading reached up to T_MAX past a portal and cut a park bridge's soil
        down under its arch's vault, the terrain then cut away over it (2026-10-17)."""
        return self._covered_tunnels_from_sections(self._tunnel_sections(feats))

    def _covered_tunnels_from_sections(self,secs):
        out=[]
        for fid,sp,xy,z,kind in secs:
            if not kind:continue
            xy=np.asarray(xy).copy();mouths=self.tunnel_model.mouth(fid)
            # The mask's end inset is only for a real mouth. Extend a covered
            # internal end so a map-segment boundary cannot expose its roof.
            for at,other,side in ((0,1,0),(-1,-2,1)):
                if mouths[side] or len(xy)<2:continue
                d=xy[at]-xy[other];d/=max(np.linalg.norm(d),1e-9)
                p=xy[at]+d*(TUNNEL_KEEP_IN_M+2.)
                xy=np.r_[p[None],xy] if at==0 else np.r_[xy,p[None]]
            out.append((xy,sp.width/2+TUNNEL_KEEP_M))
        return out

    def _open_tunnels(self, feats):
        """(fid, Plan) of the tunnels' open sections (roads.TUNNEL_OPEN_COVER): the ground graded to the road's floor
        (the lower hull of the ground), as the road is drawn (roads._tunnel_chunks): over a footbridge's hump in the
        DEM the road climbed it, the ground over the road (Central Park's transverses, 2026-10-17)."""
        return [(fid, Plan(xy, z, spec.width / 2 + shoulder(spec)))
                for fid, spec, xy, z, kind in self._tunnel_sections(feats) if kind == 0]

    def planned(self, key):
        """True once cell key's plans exist (made, or failed recently)."""
        with self.lock:
            f = self.failed.get(key)
            return key in self.cells or (f is not None and time.monotonic() - f < RETRY_S)

    def warm(self, key):
        """Make cell key's plans now (worker threads: the lookahead ahead of the player)."""
        self._cell_plans(key)

    def plans(self, lat, lon, roads_only=False):
        """The Plans touching the points' area (each road once); roads_only: not the tunnels' (TUNNEL_TAG)."""
        lat = np.asarray(lat, np.float64)
        lon = np.asarray(lon, np.float64)
        pad = (T_MAX + 40.0) / 111320.0
        padlon = pad / max(0.05, math.cos(math.radians(float(np.mean(lat)))))
        seen, out = set(), []
        e,n,_=self.frame.geodetic_to_enu(lat.ravel(),lon.ravel(),0.)
        low=np.array([e.min(),n.min()]);high=np.array([e.max(),n.max()])
        for key in mapcells.cells_for_bbox(float(lat.min()) - pad, float(lon.min()) - padlon,
                                           float(lat.max()) + pad, float(lon.max()) + padlon):
            for fid_part, p in self._cell_plans(key):
                if roads_only and TUNNEL_TAG in fid_part:
                    continue
                k = (fid_part, p.xy[0, 0], p.xy[0, 1])
                if k not in seen:
                    seen.add(k)
                    if (np.asarray(p.bbox[2:])<low).any() or (np.asarray(p.bbox[:2])>high).any():continue
                    out.append(self._resolve_plan(fid_part,p))
        return out

    def apply(self, lat, lon, base, lift=0.0, roads_only=False):
        """base (the ungraded heights at the points) graded under the roads. Same shape as base.
        lift: m added under the roads (tapering with the grading's weight): the physics block and the
        road mesh use ROAD_LIFT, the visible ground tiles 0, so the road mesh lies exactly on the
        ground the tyres touch while the visible ground stays a little below it (no z-fighting;
        2026-10-11 the user saw the tyres sink into a road mesh lifted above the physics ground)."""
        lat = np.asarray(lat, np.float64)
        lon = np.asarray(lon, np.float64)
        base = np.asarray(base, np.float64)
        shape = base.shape
        if base.size == 0:
            return base
        plans = self.plans(lat, lon, roads_only)
        if not plans:
            return base
        e, n, _ = self.frame.geodetic_to_enu(lat.ravel(), lon.ravel(), 0.0)
        e, n = np.asarray(e), np.asarray(n)
        out = grade_points(e, n, base.ravel(), plans, lift)
        keep = self._over_tunnels(e, n)
        if keep is not None:
            # Protect the roof from underground mouth/approach excavation,
            # while still grading real surface streets above the tunnel. Raw
            # DEM restoration erased their surface lift and put asphalt in the
            # visible terrain, producing torn patches over urban tunnels.
            surface=self.plans(lat,lon,roads_only=True)
            above=grade_points(e,n,base.ravel(),surface,lift) if surface else base.ravel()
            out[keep] = above[keep]
        import roadcontext
        if roadcontext.region_at(float(lat.ravel()[0]), float(lon.ravel()[0])):
            # Preserve major roads and their slip roads across their physical
            # pavement footprint, including the resolved junction pins. Nearby
            # paths and embankments cannot obtain ownership of a traffic lane.
            mainline=list(self.uk_vertical.mainline_plans.values())
            if mainline:
                from ukvertical import approach_ownership,core_mask
                weight=approach_ownership(np.c_[e,n],plans,mainline)
                candidate=grade_points(e,n,out,mainline,lift)
                core,target=core_mask(np.c_[e,n],mainline,heights=True)
                candidate[core]=target[core]+lift
                out+=weight*(candidate-out)
            # Upper abutment approaches own their ground. A nearby lower road's
            # fill transition must not drag a connected approach below the deck.
            priority=[p for k,p in self.uk_vertical.upper_plans.items() if k not in self.uk_vertical.mainline_plans]
            if priority:
                from ukvertical import approach_ownership,core_mask
                weight=approach_ownership(np.c_[e,n],plans,priority)
                candidate=grade_points(e,n,out,priority,lift)
                core,target=core_mask(np.c_[e,n],priority,heights=True)
                candidate[core]=target[core]+lift
                out+=weight*(candidate-out)
            out = self.uk_vertical.interfaces(np.c_[e,n],out,lift)
            out = self.uk_vertical.excavate(np.c_[e,n], out, lift, plans)
            # The driven road layer has its own colliding mesh. Terrain is
            # supporting fill, two centimetres below that layer, so blending
            # another road/portal into the DEM cannot put a bump through it.
            support,road_z=self.uk_vertical.surface(np.c_[e,n])
            out[support]=road_z[support]+lift-.02
        return out.reshape(shape)

    def open_tunnels(self, lat, lon):
        """[(lat (k,), lon (k,), Spec)] of the tunnels' open sections planned near the points: roads on the ground
        that the map calls tunnels (surface.paint_roads paints them: grass grew over the open road of Central Park's
        79th Street Transverse, 2026-10-17)."""
        lat = np.asarray(lat, np.float64)
        lon = np.asarray(lon, np.float64)
        if lat.size == 0:
            return []
        for key in mapcells.cells_for_bbox(float(lat.min()), float(lon.min()), float(lat.max()), float(lon.max())):
            self._cell_plans(key)
        with self.lock:
            secs = [o for v in self.opens.values() for o in v]
        out, seen = [], set()
        for xy, spec in secs:
            k = (round(float(xy[0, 0]), 2), round(float(xy[0, 1]), 2), len(xy))
            if k in seen:
                continue
            seen.add(k)
            la, lo, _ = self.frame.enu_to_geodetic(xy[:, 0], xy[:, 1], 0.0)
            la, lo = np.asarray(la), np.asarray(lo)
            if la.max() < lat.min() - 0.001 or la.min() > lat.max() + 0.001 or \
                    lo.max() < lon.min() - 0.0015 or lo.min() > lon.max() + 0.0015:
                continue
            out.append((la, lo, spec))
        return out

    def _over_tunnels(self, e, n):
        """Which points lie over a covered tunnel (its half width + TUNNEL_KEEP_M), or None."""
        with self.lock:
            zones = [z for v in self.covers.values() for z in v]
        if not zones or not len(e):
            return None
        x0, y0, x1, y1 = e.min(), n.min(), e.max(), n.max()
        import fast
        if fast.AVAILABLE and hasattr(fast._ef, "over_tunnel"):     # (Rust: the same sums, without the GIL)
            mask = np.zeros(len(e), bool)
            ee, nn = np.ascontiguousarray(e, np.float64), np.ascontiguousarray(n, np.float64)
            for xy, hw in zones:
                fast._ef.over_tunnel(mask, ee, nn, np.ascontiguousarray(xy[:, :2], np.float64), float(hw),
                                     float(TUNNEL_KEEP_IN_M))
            return mask if mask.any() else None
        mask = None
        for xy, hw in zones:
            if xy[:, 0].max() + hw < x0 or xy[:, 0].min() - hw > x1 or xy[:, 1].max() + hw < y0 or xy[:, 1].min() - hw > y1:
                continue
            a, b = xy[:-1], xy[1:]
            ab = b - a
            L2 = np.maximum((ab * ab).sum(1), 1e-12)
            sj = np.r_[0.0, np.cumsum(np.sqrt(L2))]
            # only the segments near the points (the Gotthard road tunnel's 4,200 segments each took a pass over a
            # block's points: 140 s of grading per block, 2026-10-18)
            near = ((np.minimum(a[:, 0], b[:, 0]) - hw <= x1) & (np.maximum(a[:, 0], b[:, 0]) + hw >= x0)
                    & (np.minimum(a[:, 1], b[:, 1]) - hw <= y1) & (np.maximum(a[:, 1], b[:, 1]) + hw >= y0))
            for j in np.flatnonzero(near):
                t = ((e - a[j, 0]) * ab[j, 0] + (n - a[j, 1]) * ab[j, 1]) / L2[j]
                # over it, from TUNNEL_KEEP_IN_M inside its portals: its mouths graded to the road (a road's last row
                # at a portal took the hill's height, the road mesh a wedge up into the opening, 2026-10-17)
                s_ = sj[j] + t * np.sqrt(L2[j])
                inside = (t > 0.0) & (t < 1.0) & (s_ > TUNNEL_KEEP_IN_M) & (s_ < sj[-1] - TUNNEL_KEEP_IN_M)
                d = np.abs((e - a[j, 0]) * ab[j, 1] - (n - a[j, 1]) * ab[j, 0]) / np.sqrt(L2[j])
                m = inside & (d <= hw)
                mask = m if mask is None else (mask | m)
        return mask


def grade_points(px, py, base, plans, lift=0.0):
    """base at the points (px, py) graded under the plans (see the module doc). Pure.
    All segments at once, in batches of about PAIR_BATCH (segment, point) pairs (a Python loop per
    segment was the server's largest CPU cost while driving, 2026-10-12)."""
    px = np.asarray(px, np.float64)
    py = np.asarray(py, np.float64)
    base = np.asarray(base, np.float64)
    out = base.copy()
    if not len(px):
        return out
    x0, y0, x1, y1 = px.min(), py.min(), px.max(), py.max()
    bx = np.floor((px - x0) / BUCKET).astype(np.int64)
    by = np.floor((py - y0) / BUCKET).astype(np.int64)
    nbx = int(bx.max()) + 1
    key = by * nbx + bx
    order = np.argsort(key, kind="stable")
    sk = key[order]
    # every segment of the plans near the points: ends, end heights, reach (core half width + T_MAX)
    A, B, ZA, ZB, H = [], [], [], [], []
    for p in plans:
        if p.bbox[2] < x0 or p.bbox[0] > x1 or p.bbox[3] < y0 or p.bbox[1] > y1 or len(p.xy) < 2:
            continue
        A.append(p.xy[:-1])
        B.append(p.xy[1:])
        ZA.append(p.z[:-1])
        ZB.append(p.z[1:])
        H.append(np.full(len(p.xy) - 1, p.half))
    if not A:
        return out
    A, B, ZA, ZB, H = (np.concatenate(v) for v in (A, B, ZA, ZB, H))
    import fast
    if fast.AVAILABLE and getattr(fast._ef, "VERSION", 0) >= 27:   # the Rust loop: the same pairs in the same order
        f64 = np.float64
        return fast._ef.grade_points(np.ascontiguousarray(px, f64), np.ascontiguousarray(py, f64),
                                     np.ascontiguousarray(base, f64), np.ascontiguousarray(A[:, :2], f64),
                                     np.ascontiguousarray(B[:, :2], f64), np.ascontiguousarray(ZA, f64),
                                     np.ascontiguousarray(ZB, f64), np.ascontiguousarray(H, f64), float(lift),
                                     float(SLOPE_RUN), float(T_MIN), float(T_MAX), float(BLEND_R), float(BUCKET),
                                     float(WALL_CUT_M), float(WALL_T_M), float(WALL_FLAT_M), float(WALL_AHEAD_M))
    reach = H + T_MAX
    lo_x = np.minimum(A[:, 0], B[:, 0]) - reach
    hi_x = np.maximum(A[:, 0], B[:, 0]) + reach
    lo_y = np.minimum(A[:, 1], B[:, 1]) - reach
    hi_y = np.maximum(A[:, 1], B[:, 1]) + reach
    near = ~((hi_x < x0) | (lo_x > x1) | (hi_y < y0) | (lo_y > y1))
    A, B, ZA, ZB, H = A[near], B[near], ZA[near], ZB[near], H[near]
    lo_x, hi_x, lo_y, hi_y = lo_x[near], hi_x[near], lo_y[near], hi_y[near]
    cx0 = np.maximum(0, np.floor((lo_x - x0) / BUCKET)).astype(np.int64)
    cx1 = np.minimum(nbx - 1, np.floor((hi_x - x0) / BUCKET)).astype(np.int64)
    cy0 = np.maximum(0, np.floor((lo_y - y0) / BUCKET)).astype(np.int64)
    cy1 = np.floor((hi_y - y0) / BUCKET).astype(np.int64)
    # (segment, bucket row) pairs -> the sorted points' range of that row's buckets cx0..cx1
    nrow = np.maximum(cy1 - cy0 + 1, 0)
    seg = np.repeat(np.arange(len(A)), nrow)
    row = np.repeat(cy0, nrow) + (np.arange(nrow.sum()) - np.repeat(np.cumsum(nrow) - nrow, nrow))
    i0 = np.searchsorted(sk, row * nbx + cx0[seg], "left")
    i1 = np.searchsorted(sk, row * nbx + cx1[seg], "right")
    cnt = np.maximum(i1 - i0, 0)
    keep = cnt > 0
    seg, i0, cnt = seg[keep], i0[keep], cnt[keep]
    num = np.zeros(len(px))
    den = np.zeros(len(px))
    wmax = np.zeros(len(px))
    ends = np.cumsum(cnt)
    start = 0
    while start < len(seg):
        stop = int(np.searchsorted(ends, (ends[start - 1] if start else 0) + PAIR_BATCH, "right"))
        stop = max(stop, start + 1)
        c = cnt[start:stop]
        s_ = np.repeat(seg[start:stop], c)
        idx = order[np.repeat(i0[start:stop], c) + (np.arange(c.sum()) - np.repeat(np.cumsum(c) - c, c))]
        a = A[s_]
        ab = B[s_] - a
        qx, qy = px[idx] - a[:, 0], py[idx] - a[:, 1]
        L2 = ab[:, 0] * ab[:, 0] + ab[:, 1] * ab[:, 1]
        long_ = L2 > 1e-12
        t = np.where(long_, np.clip((qx * ab[:, 0] + qy * ab[:, 1]) / np.where(long_, L2, 1.0), 0.0, 1.0), 0.0)
        d = np.hypot(qx - t * ab[:, 0], qy - t * ab[:, 1])
        target = ZA[s_] + (ZB[s_] - ZA[s_]) * t
        Lab = np.sqrt(np.maximum(L2, 1e-24))
        side = np.abs(qx * ab[:, 1] - qy * ab[:, 0]) / Lab
        along = (qx * ab[:, 0] + qy * ab[:, 1]) / Lab
        ahead = np.maximum(np.maximum(-along, along - Lab), 0.0)
        wall = (base[idx] - target > WALL_CUT_M) & (ahead < side) & (ahead < WALL_AHEAD_M)
        T = np.where(wall, WALL_T_M, np.clip(SLOPE_RUN * np.abs(target - base[idx]), T_MIN, T_MAX))
        u = np.clip((d - H[s_] - np.where(wall, WALL_FLAT_M, 0.0)) / T, 0.0, 1.0)
        w = 1.0 - u * u * (3.0 - 2.0 * u)           # 1 on the core, smooth to 0 over T
        m = w > 0
        i = idx[m]
        # the blend between roads by inverse distance from each centreline (times w), so two roads
        # near each other (divided carriageways, junctions) meet in a gradual slope; with w alone
        # the target jumped at a core's edge (2026-10-11, the user's car flipped at speed:
        # centreline 2nd difference p99 0.17 m per metre, worst 0.5 m)
        wb = w[m] / (1.0 + (d[m] / BLEND_R) ** 2)
        num += np.bincount(i, wb * target[m], len(px))
        den += np.bincount(i, wb, len(px))
        np.maximum.at(wmax, i, w[m])
        start = stop
    g = den > 0
    out[g] = base[g] + wmax[g] * (num[g] / den[g] - base[g] + lift)
    return out


def _bounds_latlon(b):
    """(lat0, lon0, lat1, lon1) of a CellKey.bounds() (lon0, lat0, lon1, lat1)."""
    lon0, lat0, lon1, lat1 = (float(v) for v in b)
    return lat0, lon0, lat1, lon1


def paired_abutment_targets(points, targets, bridges, levels):
    """One height for side-by-side, same-level bridge approaches; never across a stacked deck.

    Ends must lie abreast (within 5 m along the span), with parallel span tangents.
    This shares clearance evidence across twin carriageways without routing traffic
    across the median. Pure, with heights in the same coordinate frame.
    """
    points, targets = np.asarray(points), np.asarray(targets, float)
    if len(points) < 2 or not bridges:
        return targets.copy()
    ends, directions, lvls = [], [], []
    for line, level in zip(bridges, levels):
        for p, d in ((line[0], line[1] - line[0]), (line[-1], line[-2] - line[-1])):
            ends.append(p)
            directions.append(d / max(float(np.linalg.norm(d)), 1e-9))
            lvls.append(level)
    ends, directions = np.asarray(ends), np.asarray(directions)
    match = np.linalg.norm(points[:, None] - ends[None], axis=2).argmin(1)
    parent = list(range(len(points)))
    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for i in range(len(points)):
        for j in range(i):
            a, b = match[i], match[j]
            delta = points[i] - points[j]
            if (lvls[a] == lvls[b] and np.linalg.norm(delta) <= roadsmod.DUAL_DECK_M
                    and float(directions[a] @ directions[b]) > .95
                    and abs(float(delta @ directions[a])) <= 5.
                    and abs(float(delta @ directions[b])) <= 5.):
                parent[root(i)] = root(j)
    maxima = {}
    for i, value in enumerate(targets):
        r = root(i)
        maxima[r] = max(maxima.get(r, -np.inf), value)
    return np.array([maxima[root(i)] for i in range(len(points))])


def bridge_lifts(line, all_bridges, ground_lines, z_at):
    """[(end xy (2,), lift m)] of a bridge part (line (k, 2) ENU m): at each of its ends that no other bridge part
    continues from (an abutment), how far the ground there must be raised for the deck to clear every road crossing
    under it (roads.DECK_ROAD_CLEAR + APPROACH_MARGIN_M over the road, full height within APPROACH_FLAT_M of the end,
    then falling at roads.DECK_GRADE), within [APPROACH_MIN_LIFT, APPROACH_MAX_LIFT]. Roads crossing within
    APPROACH_MIN_CROSS_M of either end meet it at grade and do not count. z_at(xy (n, 2)) -> ground m. Pure given z_at."""
    line = np.asarray(line, np.float64)[:, :2]
    if len(line) < 2:
        return []
    s = np.r_[0.0, np.cumsum(np.hypot(*np.diff(line, axis=0).T))]
    if s[-1] < 2 * APPROACH_MIN_CROSS_M:
        return []
    cr = roadsmod._crossings([line], ground_lines)
    if not cr:
        return []
    zu = z_at(np.array([c[2] for c in cr], np.float64))
    arcs = np.array([c[1] for c in cr], np.float64)
    under = (arcs >= APPROACH_MIN_CROSS_M) & (arcs <= s[-1] - APPROACH_MIN_CROSS_M)    # (not a junction at an end)
    if not under.any():
        return []
    zu, arcs = zu[under], arcs[under]
    out = []
    for end, at in ((line[0], 0.0), (line[-1], s[-1])):
        joined = False
        for other in all_bridges:
            if other is line or (len(other) == len(line) and np.array_equal(other, line)):
                continue
            o = np.asarray(other, np.float64)
            if min(np.hypot(*(o[0, :2] - end)), np.hypot(*(o[-1, :2] - end))) < 0.75:
                joined = True
                break
        if joined:
            continue
        d = np.abs(arcs - at)
        need = zu + roadsmod.DECK_ROAD_CLEAR + APPROACH_MARGIN_M \
            - roadsmod.DECK_GRADE * np.maximum(d - APPROACH_FLAT_M, 0.0)
        lift = float(need.max() - z_at(end[None])[0])
        if lift >= APPROACH_MIN_LIFT:
            out.append((np.asarray(end, np.float64), min(lift, APPROACH_MAX_LIFT)))
    return out


def approach_add(xy, at_end, lift, half, others=()):
    """m to add to a road plan's vertices (xy (n, 2)) rising to `lift` at its first (at_end False) or last vertex (a
    bridge's abutment), falling off along the road (arc length) on a cosine ramp whose steepest grade is APPROACH_GRADE;
    at most what keeps the fill slope (SLOPE_RUN) clear of the other roads [(line (k, 2), half width)] beside it, with
    APPROACH_GAP_M to spare. None when nothing is raised. Pure."""
    xy = np.asarray(xy, np.float64)[:, :2]
    if len(xy) < 2 or lift < APPROACH_MIN_LIFT:
        return None
    s = np.r_[0.0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
    d = (s[-1] - s) if at_end else s
    run = float(np.clip(lift * math.pi / (2 * APPROACH_GRADE), APPROACH_MIN_RUN, APPROACH_MAX_RUN))
    u = np.clip(d / run, 0.0, 1.0)
    add = lift * 0.5 * (1.0 + np.cos(math.pi * u))
    on = add > 1e-3
    if not on.any():
        return None
    q0 = xy[on]
    lo_q, hi_q = q0.min(0), q0.max(0)
    for line, oh in others:
        line = np.asarray(line, np.float64)[:, :2]
        if len(line) < 2:
            continue
        reach = half + oh + APPROACH_GAP_M + SLOPE_RUN * lift
        if (line.max(0) < lo_q - reach).any() or (line.min(0) > hi_q + reach).any():
            continue                    # too far to matter
        q = xy[on]
        a, b = line[:-1], line[1:]
        ab = b - a
        L2 = np.maximum((ab * ab).sum(1), 1e-12)
        t = np.clip(((q[:, None, :] - a[None]) * ab[None]).sum(2) / L2[None], 0.0, 1.0)
        dist = np.hypot(*(q[:, None, :] - (a[None] + t[..., None] * ab[None])).transpose(2, 0, 1)).min(1)
        cap = np.maximum(0.0, (dist - half - oh - APPROACH_GAP_M) / SLOPE_RUN)
        add[on] = np.minimum(add[on], cap)
    if add.max() < 1e-3:
        return None
    return add


def _is_link(spec):
    return bool(getattr(spec, "link", False))


class GradedDem:
    """dem.Dem with sample() graded under the roads; everything else passes through."""

    def __init__(self, dem, grader):
        self._dem, self._grader = dem, grader

    def sample(self, lat, lon, zoom, progress=None):
        base = self._dem.sample(lat, lon, zoom, progress) if progress is not None else self._dem.sample(lat, lon, zoom)
        return self._grader.apply(lat, lon, base)

    def __getattr__(self, name):
        return getattr(self._dem, name)
