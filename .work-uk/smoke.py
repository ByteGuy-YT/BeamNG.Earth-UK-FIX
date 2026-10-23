import json
import sys
import time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
import mapdata, mapcells, netfetch, geodesy, roads, navgraph, roadmesh

sites = [(53.34, -1.8, "winnats"), (53.213, -1.676, "bakewell"), (53.19, -1.32, "m1"),
         (53.247, -1.623, "baslow"), (51.48, -3.18, "cardiff"), (55.953, -3.188, "edinburgh"),
         (54.597, -5.93, "belfast")]
md = mapdata.MapData(".work-uk/cache", netfetch.Fetcher())
summary = []
flat = lambda la, lo: np.full(np.shape(la), 10.)
try:
    for lat, lon, name in sites:
        started = time.perf_counter()
        f = md.cell(mapcells.cell_of(lat, lon), layers=("roads", "landcover"))
        feats, lc = f.layers["roads"], f.layers["landcover"]
        urban = lambda la, lo: lc.sample(lo, la) == 50
        frame = geodesy.EnuFrame(lat, lon)
        spec = roads.road_specs(feats, urban)
        candidates = []
        for i, sp in enumerate(spec):
            if sp is None or (name == "m1" and sp.cls != "motorway"):
                continue
            ll = np.asarray(feats.parts(i)[0][0])
            e, n, _ = frame.geodetic_to_enu(ll[:, 1], ll[:, 0], 0.)
            xy = np.column_stack([e, n])
            if len(xy) > 1:
                mid = (xy[:-1] + xy[1:]) / 2
                at = np.argmin(np.linalg.norm(mid, axis=1))
                candidates.append((float(np.linalg.norm(mid[at])), mid[at]))
        point = min(candidates, key=lambda c: c[0])[1] if candidates else np.zeros(2)
        tx, ty = (int(np.floor(v / roads.TILE)) for v in point)
        walks, props, parking = [], [], []
        chunks = roads.build_tile(frame, tx, ty, [feats], flat, urban, walks=walks, props=props,
                                  park=parking, left_hand=True)
        assert chunks, name + " has no road geometry"
        mesh = roadmesh.build(frame, chunks, flat, (0., 0., 0.))
        if mesh is not None:
            assert np.isfinite(mesh[0]).all()
            assert mesh[1].max(initial=0) < len(mesh[0])
        graph = navgraph.build(frame, [feats], flat, (0, 0), urban_fn=urban, left_hand=True)
        assert all(e[0] in graph["nodes"] and e[1] in graph["nodes"] and e[7] > 0 for e in graph["edges"])
        assert not any(r[0] in ("hydrant", "deciduous") for r in props)
        spec = roads.road_specs(feats, urban)
        row = {"site": name, "features": len(feats), "mapped_tag_matches": int(np.count_nonzero(feats.attrs["osm_match"] == "matched")),
               "chunks": len(chunks), "pavement_runs": len(walks), "ai_nodes": len(graph["nodes"]),
               "ai_edges": len(graph["edges"]), "roundabout_segments": sum(s is not None and s.profile is not None and s.profile.junction == "roundabout" for s in spec),
               "seconds": round(time.perf_counter() - started, 3)}
        summary.append(row)
        print(json.dumps(row), flush=True)
    Path(".work-uk/smoke-results.json").write_text(json.dumps(summary, indent=2))
finally:
    md.close()
