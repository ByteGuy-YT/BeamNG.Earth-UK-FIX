"""Independent-worker bridge boundary audit. Test coordinates are not production overrides."""
import sys,json,time,argparse,numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'server')];import mapdata,netfetch,dem,geodesy,grading,roads,roadmesh
cases=[('boston',42.3685,-71.063),('j26',52.9994,-1.231),('sydney',-33.8523,151.2108)]
ap=argparse.ArgumentParser(description='Compare bridge edges built with independent tile height models.');ap.add_argument('--out',default=str(ROOT/'docs/world-seam-validation.json'));ap.add_argument('--case',action='append',default=[]);args=ap.parse_args()
net=netfetch.Fetcher(offline=True);cache=str(Path.home()/'.cache/beamng-earth');md=mapdata.MapData(cache,net);dd=dem.Dem(cache+'/dem',fetcher=net)
import seacarve
sea=seacarve.SeaCarver(md,cache,dem=dd)
rows=[]
for name,lat,lon in cases:
 if args.case and name not in args.case:continue
 start=time.perf_counter();fr=geodesy.EnuFrame(lat,lon);ends={};count=0;errors=[]
 raw=lambda la,lo:dd.sample(la,lo,15)
 shaped=lambda la,lo:sea.carve(la,lo,raw(la,lo))
 for tx,ty in ((-1,0),(0,0),(0,-1),(-1,-1)):
  # Each tile starts with an independent height model, as separate worker processes do.
  g=grading.Grader(fr,md,raw,structure_elev=shaped);elev=lambda la,lo:g.apply(la,lo,shaped(la,lo),.04)
  bp=g.bridge_model;bp.wet=sea.depth
  fs=[md.cell(k,layers=('roads',)).layers.get('roads') for k in roads.cells_of_tile(fr,tx,ty)]
  chunks=roads.build_tile(fr,tx,ty,fs,elev,bridges=bp,tunnels=g.tunnel_model)
  cs=[c for c in chunks if c.get('deck') and not c.get('tunnel')]
  for c,r in zip(cs,roadmesh.ribbons(cs)):
   for at in (0,-1):
    p=np.array(c['n'][at]);k=(c['fid'],*np.round(p[:2],3))
    if not np.any(abs(p[:2]/256-np.round(p[:2]/256))<1e-6):continue
    for other,oi,oldtile in ends.get(k,[]):
     if oldtile==(tx,ty):continue
     count+=1;gap=min(max(np.linalg.norm(r[s][at]-other[s][oi]) for s in (0,1)),max(np.linalg.norm(r[s][at]-other[1-s][oi]) for s in (0,1)))
     errors.append(max(float(gap),abs(float(r[5][at]-other[5][oi]))))
    ends.setdefault(k,[]).append((r,at,(tx,ty)))
 row={'name':name,'seams':count,'max_gap':max(errors,default=0.),'seconds':time.perf_counter()-start}
 row['ok']=count>0 and row['max_gap']<.03;rows.append(row);print(json.dumps(row),flush=True)
 Path(args.out).write_text(json.dumps(rows,indent=2))
md.close();dd.pool.shutdown()
raise SystemExit(not all(r['ok'] for r in rows))

