"""One physical cross-section for UK roads, AI, markings, physics and vegetation.

Fallbacks are deliberately modest; they are estimates, never advertised as surveys.
OSM tags arrive through osm_enrich. Directions/sides in that column are already aligned
with the feature geometry. A Profile is immutable and safe in memoised Specs.
"""
import json
import math
import os
import re
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import numpy as np

import roadcontext


@lru_cache(maxsize=1)
def config():
    path = Path(os.environ.get("BEAMNG_EARTH_UK_ROADS_CONFIG", Path(__file__).with_name("uk_roads.json")))
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, value in data.items():
        values = value.values() if isinstance(value, dict) else [value]
        for v in values:
            if isinstance(v, (int, float)) and (not math.isfinite(v) or v < 0):
                raise ValueError(f"Invalid UK road configuration: {key}")
    if any(float(v) <= 0 for v in data["lane_width"].values()):
        raise ValueError("UK lane widths must be positive")
    return data


def metres(value):
    """Physical length. Reject lists, ranges, unknowns and restrictions, accept m/ft/in."""
    if value is None:
        return None
    s = str(value).strip().lower()
    imperial = re.fullmatch(r"(\d+(?:\.\d+)?)\s*'\s*(\d+(?:\.\d+)?)?\s*\"?", s)
    if imperial:
        v = float(imperial[1]) * .3048 + float(imperial[2] or 0) * .0254
    else:
        m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(m|metres?|meters?|ft|feet)?", s)
        if not m:
            return None
        v = float(m[1]) * (.3048 if m[2] in ("ft", "feet") else 1.)
    return v if math.isfinite(v) and 0 <= v <= 100 else None


def count(value):
    s = str(value or "").strip()
    return int(s) if s.isdigit() and 1 <= int(s) <= 12 else None


def tags_for(feats, i):
    col = feats.attrs.get("osm_tags")
    if col is None:
        return {}
    try:
        return json.loads(str(col[i])) or {}
    except (ValueError, TypeError):
        return {}


def rule(feats, name, i):
    table = feats.rules.get(name)
    k = table.major(i) if table is not None else -1
    return table.value[k] if k >= 0 else None


@dataclass(frozen=True)
class Profile:
    region: str
    width: float
    drive: float
    forward: int
    backward: int
    left_space: float = 0.
    right_space: float = 0.
    walk_left: float = 0.
    walk_right: float = 0.
    parking_left: float = 0.
    parking_right: float = 0.
    lane_widths: tuple = ()        # left to right looking along geometry
    lane_markings: bool = True
    shared: bool = False
    junction: str = ""
    source: str = "class-estimate"
    lane_source: str = "class-estimate"
    walk_source: str = "urban-estimate"
    diagnostics: tuple = ()
    speed_mph: float | None = None
    control: str = ""             # mapped signal/stop/give_way, empty unknown
    centre_width: float = 0.      # shared centre turning lanes, excluded from directional lane counts
    controls: tuple = ("", "")   # mapped control at start/end of this segment
    crossings: tuple = ()        # mapped crossings at fractions of this segment
    mini_ends: tuple = (False, False)
    control_setbacks: tuple = (0., 0.)
    national_speed: bool = False
    highway: str = ""              # mapped source class, retaining _link distinction
    explicit_two_way: bool = False

    @property
    def offset(self):
        return (self.right_space - self.left_space) / 2

    @property
    def mainline(self):
        return self.highway in ('motorway','trunk')

    @property
    def surface_offset(self):
        # Divided mainline mapping traces the driving corridor. Its asymmetric
        # outer shoulder extends the surface outward, not the lanes inward.
        return -self.offset if self.mainline else 0.

    @property
    def left_hand(self):
        return True


def _pavements(t, urban, cls, direction):
    typical = config().get("pavement_width_by_class", {}).get(cls, config()["pavement_width"])
    default = typical if urban and cls not in {"motorway", "trunk", "track", "service"} else 0.
    common = t.get("sidewalk:both", t.get("sidewalk"))
    widths = []
    for side in ("left", "right"):
        presence = t.get(f"sidewalk:{side}", common)
        if presence in ("no", "none", "separate") or common in ("left", "right") and common != side:
            widths.append(0.)
            continue
        v = metres(t.get(f"sidewalk:{side}:width", t.get("sidewalk:both:width", t.get("sidewalk:width"))))
        widths.append(v if v is not None and v <= 10 else
                      (typical if presence in ("yes", "both", side) else default))
    return widths


def _parking(t, side):
    val = t.get(f"parking:{side}", t.get("parking:both", t.get(f"parking:lane:{side}", t.get("parking:lane:both"))))
    if val not in {"lane", "parallel", "diagonal", "perpendicular", "yes"}:
        return 0.
    v = metres(t.get(f"parking:{side}:width", t.get("parking:both:width", t.get(f"parking:lane:{side}:width"))))
    return v if v is not None and v <= 8 else config()["parking_width"]


def _speed(t, region, cls, direction, dual):
    v = t.get("maxspeed:" + ("backward" if direction < 0 else "forward"), t.get("maxspeed", ""))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(mph|km/h)?", v)
    if m:
        return float(m[1]) / (1.609344 if m[2] != "mph" else 1.)
    if v in {"GB:nsl_single", "GB:nsl_dual", "GB:motorway", "UK:nsl_single", "UK:nsl_dual"}:
        return 60. if v.endswith("single") else 70.
    # Only mapped restricted-road context establishes a legal default, not WorldCover built-up pixels.
    if t.get("lit") == "yes" and cls != "motorway" and not v:
        return 20. if region == "Wales" else 30.
    return None


def _nodes(t, ll):
    controls, minis, crossings, setbacks = ["", ""], [False, False], [], [0., 0.]
    if len(ll) < 2:
        return tuple(controls), (), tuple(minis), tuple(setbacks)
    scale = np.array([111320. * np.cos(np.radians(ll[:, 1].mean())), 111320.])
    xy = (ll - ll[0]) * scale
    seg = np.diff(xy, axis=0)
    lengths = np.hypot(*seg.T)
    length2 = np.maximum(lengths * lengths, 1e-12)
    stations = np.r_[0., np.cumsum(lengths)]
    if stations[-1] < .01:
        return tuple(controls), (), tuple(minis), tuple(setbacks)
    for node in t.get("_nodes", ()):
        q = (np.array([node["lon"], node["lat"]]) - ll[0]) * scale
        f = np.clip(((q - xy[:-1]) * seg).sum(1) / length2, 0, 1)
        d = np.linalg.norm(q - xy[:-1] - f[:, None] * seg, axis=1)
        k = int(d.argmin())
        if d[k] > 5.:
            continue
        at = (stations[k] + f[k] * lengths[k]) / stations[-1]
        what = node.get("highway")
        if what == "crossing" and node.get("crossing") not in {"no", "unmarked", "informal"}:
            crossings.append(float(at))
        end_dist = np.linalg.norm(xy[[0, -1]] - q, axis=1)
        end = int(end_dist.argmin())
        along_end = (at if end == 0 else 1-at) * stations[-1]
        if end_dist[end] <= 60. and along_end <= stations[-1] * .45 + 1.:
            if what in {"stop", "give_way", "traffic_signals"}:
                direction = node.get('traffic_signals:direction', node.get('direction'))
                if direction in ('forward', 'backward') and (direction == 'forward') != (end == 1):
                    continue
                controls[end] = what
                setbacks[end] = float(along_end)
            elif what == "mini_roundabout" and end_dist[end] <= 12.:
                minis[end] = True
    return tuple(controls), tuple(sorted(set(crossings))), tuple(minis), tuple(setbacks)


def resolve(feats, i, spec, urban_fn=None, widths=None, urban_override=None):
    region = roadcontext.feature_region(feats, i)
    if not region or spec is None:
        return spec
    cfg = config()
    t = tags_for(feats, i)
    a = feats.coord_off[feats.ring_off[feats.part_off[i]]]
    b = feats.coord_off[feats.ring_off[feats.part_off[i + 1]]]
    ll = feats.lonlat[a:b]
    urban = spec.urban
    if urban_override is not None:
        urban = urban_override
    elif urban_fn is not None and len(ll):
        urban = bool(np.mean(urban_fn(ll[:, 1], ll[:, 0])) >= .5)
    cls = spec.cls
    junction = t.get("junction", "")
    # Overture retains a roundabout road flag in releases which provide it.
    flags = feats.rules.get("flags")
    if not junction and flags is not None and any(str(flags.value[k]) == "is_roundabout" for k in flags.rows(i)):
        junction = "roundabout"
    direction = spec.dir
    if t.get("highway") and "oneway" not in t and cls != "motorway" and junction != "roundabout":
        # OSM's normal road default is two-way. A nearby bend of this same street must
        # not turn it into a narrow, opposing carriageway through geometric inference.
        direction = 0
    if t.get("oneway") in {"yes", "1", "true"}:
        direction = 1
    elif t.get("oneway") in {"-1", "reverse"}:
        direction = -1
    elif t.get("oneway") in {"no", "0", "false"}:
        direction = 0
    elif cls == "motorway" and not direction:
        direction = 1
    elif junction == "roundabout" and not direction:
        direction = 1                 # OSM roundabout ways imply oneway=yes in digitised direction
    # Enriched tags are already oriented to this feature's digitised geometry.
    oneway = bool(direction) or junction == "roundabout"
    slip = str(rule(feats, "subclass", i)) == "link" or t.get("highway", "").endswith("_link")
    fwd, back, total = count(t.get("lanes:forward")), count(t.get("lanes:backward")), count(t.get("lanes"))
    array_counts = False
    def from_arrays(suffix=""):
        values = [len(t[k].split("|")) for prefix in ("turn:lanes", "width:lanes", "change:lanes", "destination:lanes", "destination:ref:lanes", "access:lanes")
                  if (k := prefix + suffix) in t and t[k]]
        return count(values[0]) if values and len(set(values)) == 1 else None
    if not total:
        total = from_arrays()
        array_counts |= total is not None
    if not fwd:
        fwd = from_arrays(":forward")
        array_counts |= fwd is not None
    if not back:
        back = from_arrays(":backward")
        array_counts |= back is not None
    centre_count = count(t.get("lanes:both_ways")) or 0
    directional_total = max(1, total - centre_count) if total else None
    diag = []
    if array_counts:
        diag.append("lane-count-from-mapped-lane-arrays")
    if t.get("_section_conflicts"):
        diag.append("varying-osm-attributes:" + t["_section_conflicts"])
    if total and fwd and back and fwd + back + centre_count != total:
        diag.append("conflicting-total-and-directional-lanes")
    lane_source = "osm-lanes" if any((fwd, back, total)) else "class-estimate"
    if oneway:
        default_lanes = cfg["motorway_lanes"] if cls == "motorway" and not slip else \
            cfg.get("divided_arterial_lanes", 2) if cls in {"primary", "trunk"} and not slip else 1
        n = total or fwd or back or default_lanes
        fwd, back = (0, n) if direction < 0 else (n, 0)
    else:
        if directional_total and fwd and not back and directional_total > fwd:
            back = directional_total - fwd
        elif directional_total and back and not fwd and directional_total > back:
            fwd = directional_total - back
        elif directional_total and not fwd and not back:
            fwd, back = (1, 1) if directional_total == 1 else (directional_total // 2, directional_total - directional_total // 2)
            if directional_total > 2 and directional_total % 2:
                diag.append("odd-lane-split-estimated")
        fwd, back = fwd or 1, back or 1
    shared = not oneway and (total == 1 or t.get("narrow") == "yes" and lane_source == "class-estimate")
    lw = cfg["slip_lane_width"] if slip else cfg["lane_width"].get(cls, 2.75)
    drive = cfg["single_track_width"] if shared or cls in {"service", "track"} and total is None else (fwd + back) * lw
    centre_width = centre_count * lw if not oneway else 0.
    drive += centre_width
    if junction == "roundabout" and fwd + back == 1:
        drive = max(drive, cfg.get("roundabout_single_lane_width", 4.5))
    if oneway and lane_source=='class-estimate' and not slip and cls in {'residential','living_street','unclassified','tertiary','secondary'}:
        # A lane estimate is not the width of the entire paved street. Leave
        # usable edge space on unmeasured one-way streets; explicit widths below
        # still win, and building separation can constrain this fallback.
        drive=max(drive,cfg.get('oneway_street_width',4.0))
    park_l, park_r = _parking(t, "left"), _parking(t, "right")
    left, right = park_l, park_r
    if cls == "motorway" and not slip:
        # Traffic management also covers controlled motorways with permanent shoulders.
        # Only mapped shoulder absence suppresses the normal motorway estimate.
        shoulder = t.get("shoulder", "yes")
        outer = 0. if shoulder in {"no", "none"} else cfg["motorway_hard_shoulder"]
        if direction < 0:
            left, right = cfg["motorway_inner_strip"], outer
        else:
            left, right = outer, cfg["motorway_inner_strip"]
    elif slip:
        left += cfg["slip_edge_strip"]
        right += cfg["slip_edge_strip"]
    for side in ("left", "right"):
        shoulder = t.get(f"shoulder:{side}", t.get("shoulder:both", t.get("shoulder")))
        v = metres(t.get(f"shoulder:{side}:width", t.get("shoulder:both:width", t.get("shoulder:width"))))
        if shoulder in {"no", "none"}:
            v = 0.
        elif shoulder == "yes" and v is None and cls == "motorway" and not slip and f"shoulder:{side}" in t:
            outer_side = "right" if direction < 0 else "left"
            v = cfg["motorway_hard_shoulder"] if side == outer_side else cfg["motorway_inner_strip"]
        if v is not None and v <= 6:
            if side == "left": left = park_l + v
            else: right = park_r + v
    lane_widths = []
    lane_width_evidence = False
    # Directional arrays are ordered left-to-right in the direction of travel.
    for key, n in (("width:lanes:forward", fwd), ("width:lanes:backward", back)):
        vals = [metres(x) for x in t.get(key, "").split("|")] if key in t else []
        if len(vals) == n and all(v is not None and 1.5 <= v <= 5.5 for v in vals):
            lane_widths.extend(reversed(vals) if key.endswith("backward") else vals)
            lane_width_evidence = lane_width_evidence or bool(n)
        elif n:
            lane_widths.extend([lw] * n)
    if "width:lanes" in t and not any(k in t for k in ("width:lanes:forward", "width:lanes:backward")):
        vals = [metres(x) for x in t["width:lanes"].split("|")]
        if len(vals) == fwd + back and all(v is not None and 1.5 <= v <= 5.5 for v in vals):
            lane_widths = list(reversed(vals)) if direction < 0 else vals
            lane_width_evidence = True
            if not oneway:
                diag.append("unqualified-width-lane-order-assumed")
    if lane_width_evidence and not shared:
        drive = sum(lane_widths) + centre_width
    width = metres(t.get("width"))
    source = "osm-estimated-width" if "estimat" in t.get("source:width", "").lower() else "osm-width"
    if width is None or not 1 <= width <= 40:
        value = rule(feats, "width", i)
        width = float(value) if value is not None and math.isfinite(float(value)) and 1 <= float(value) <= 40 else None
        source = "overture-width"
    if width is None:
        width = metres(t.get("est_width"))
        source = "osm-estimated-width"
    if width is None or not 1 <= width <= 40:
        width, source = drive + left + right, "lane-widths" if lane_width_evidence else "lane-estimate" if lane_source == "osm-lanes" else "class-estimate"
    else:
        # An explicit total width already includes edge space. Never widen it to fit a default shoulder.
        if width - left - right < min(2.4, width):
            diag.append("edge-space-does-not-fit-width")
            left = right = park_l = park_r = 0.
        drive = max(.5, width - left - right)
        if lane_source == "class-estimate" and not shared:
            n = max(1, min(8, round(drive / lw)))
            fwd, back = ((0, n) if direction < 0 else (n, 0)) if oneway else (max(1, n // 2), max(1, n // 2))
            lane_source = "width-estimate"
    walk_l, walk_r = _pavements(t, urban, cls, direction)
    if spec.median and oneway and not any(k.startswith("sidewalk") for k in t):
        if direction < 0: walk_l = 0.
        else: walk_r = 0.
    walk_source = "osm" if any(k.startswith("sidewalk") for k in t) else "urban-estimate"
    if widths is not None and urban and not spec.median and source.endswith("estimate") and len(ll):
        measured = widths(str(feats.ids[i]), ll)
        if measured is not None:
            row = measured[0] + 2 * measured[1]
            # Building separation can constrain a road, but front gardens must not inflate it.
            if row < width + walk_l + walk_r:
                width = max(2.5, min(width, row - min(walk_l, .9) - min(walk_r, .9)))
                remain = max(0., row - width)
                denom = walk_l + walk_r
                if denom:
                    walk_l, walk_r = walk_l * min(1., remain / denom), walk_r * min(1., remain / denom)
                drive = max(.5, width - left - right)
                source = "building-constrained-estimate"
    shared = shared or not oneway and drive < 4.5 and lane_source != "osm-lanes"
    markings = t.get("lane_markings") != "no" and not shared
    if cls in {"residential", "living_street", "service"} and t.get("lane_markings") != "yes" and fwd + back <= 2 and not oneway:
        markings = False             # ordinary unmarked UK residential streets
    if shared:
        fwd, back = 1, 1       # engine limitation: shared space, not two painted physical lanes
        lane_widths = []
    else:
        n = fwd + back
        if len(lane_widths) != n or sum(lane_widths) <= 0:
            lane_widths = [drive / n] * n
        else:
            scale = max(.5, drive - centre_width) / sum(lane_widths)
            lane_widths = [v * scale for v in lane_widths]
        if min(lane_widths) < 2.2:
            diag.append("mapped-lanes-narrower-than-2.2m")
    speed = _speed(t, region, cls, direction, spec.median)
    control = t.get("highway", "") if t.get("highway") in {"traffic_signals", "stop", "give_way"} else t.get("_control", "")
    if centre_width:
        diag.append("shared-centre-lane-not-routable-by-stock-ai")
    controls, crossings, minis, setbacks = _nodes(t, ll)
    p = Profile(region, width, drive, fwd, back, left, right, walk_l, walk_r,
                park_l, park_r, tuple(lane_widths), markings, shared, junction, source, lane_source,
                walk_source, tuple(diag), speed, control, centre_width, controls, crossings, minis, setbacks,
                t.get('maxspeed','').startswith(('GB:nsl','UK:nsl')),t.get('highway',''),
                t.get('oneway') in ('no','0','false') or bool(count(t.get('lanes:forward')) and count(t.get('lanes:backward'))))
    return spec._replace(width=width, urban=urban, oneway=oneway, dir=direction,
                         walk=max(walk_l, walk_r), profile=p,
                         median=None if t.get("highway") and not direction else spec.median)


def apply(feats, specs, urban_fn=None, widths=None):
    # Land-cover sampling is expensive per call. Batch a cell, including explicitly mapped-width roads.
    ask, spans = [], []
    for i, sp in enumerate(specs):
        if sp is not None and roadcontext.feature_region(feats, i):
            a = feats.coord_off[feats.ring_off[feats.part_off[i]]]
            b = feats.coord_off[feats.ring_off[feats.part_off[i + 1]]]
            if b > a:
                ask.append(i)
                spans.append(feats.lonlat[a:b])
    urban = {}
    if urban_fn is not None and spans:
        ll = np.concatenate(spans)
        values = np.asarray(urban_fn(ll[:, 1], ll[:, 0]), bool)
        at = 0
        for i, span in zip(ask, spans):
            urban[i] = bool(np.mean(values[at:at + len(span)]) >= .5)
            at += len(span)
    out=[resolve(feats, i, sp, None, widths, urban.get(i)) if sp is not None else None for i, sp in enumerate(specs)]
    circular=[i for i in range(len(feats)) if tags_for(feats,i).get('junction')=='circular' and roadcontext.feature_region(feats,i)]
    if circular:
        directions=getattr(feats,'_uk_circular_dirs',None)
        if directions is None:
            import roads,islands
            candidates=[]
            origin=feats.lonlat[0];scale=np.array([111320.*math.cos(math.radians(origin[1])),111320.])
            for i in circular:
                sp=out[i]
                if sp is None:
                    cls=str(feats.attrs.get('class',['primary']*len(feats))[i])
                    sp=resolve(feats,i,roads.Spec(6.5,'paved',False,cls),None,None,False)
                if sp is None or sp.profile is None:continue
                for part in feats.parts(i):
                    if part and len(part[0])>1:
                        xy=(np.asarray(part[0])-origin)*scale
                        candidates.append((str(feats.ids[i]),sp,np.c_[xy,np.zeros(len(xy))],None))
            directions=feats._uk_circular_dirs=islands.ring_directions(candidates,True)
        for i in circular:
            sp=out[i];direction=directions.get(str(feats.ids[i]))
            if sp is None or not direction or sp.profile.explicit_two_way:continue
            p=sp.profile;n=max(1,p.forward+p.backward)
            p=replace(p,forward=n if direction>0 else 0,backward=n if direction<0 else 0,shared=False,
                      diagnostics=p.diagnostics+('closed-circular-circulation',))
            out[i]=sp._replace(oneway=True,dir=direction,profile=p)
    return out
