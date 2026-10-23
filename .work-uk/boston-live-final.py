import sys,json,time
from pathlib import Path
import numpy as np
sys.path[:0]=['server','tools'];import roads,mapdata,netfetch,dem,grading,geodesy,seacarve,mcp
cache=str(Path.home()/'.cache/beamng-earth');net=netfetch.Fetcher(offline=True);md=mapdata.MapData(cache,net);dd=dem.Dem(cache+'/dem',fetcher=net);fr=geodesy.EnuFrame(42.3685,-71.063)
sea=seacarve.SeaCarver(md,cache,dem=dd);raw=lambda la,lo:dd.sample(la,lo,15);sr=lambda la,lo:sea.carve(la,lo,raw(la,lo))
gr=grading.Grader(fr,md,raw,structure_elev=sr);elev=lambda la,lo:gr.apply(la,lo,sr(la,lo),.04)
bp=gr.bridge_model;bp.wet=sea.depth
tp=gr.tunnel_model
for tx,ty in ((0,0),(-1,0),(0,-1),(-1,-1)):
 fs=[md.cell(k,layers=('roads',)).layers.get('roads') for k in roads.cells_of_tile(fr,tx,ty)]
 roads.build_tile(fr,tx,ty,fs,elev,bridges=bp,tunnels=tp)
rows=[]
for kind,model in (('bridge',bp),('tunnel',tp)):
 parts=list(model.done.values());_,edges,_=roads._chain_graph([v[1] for v in parts]);degree={}
 for a,b,_ in edges:
  for node in (a,b):degree[node]=degree.get(node,0)+1
 for part,(a,b,s) in zip(parts,edges):
  sp,xy,z,_=part
  if not np.isfinite(z).all():continue
  for at,node in ((0,a),(-1,b)):
   if degree[node]<2 or (abs(xy[at])>400).any():continue
   for d in (2.,8.,16.):
    station=min(d,s[-1]/2) if at==0 else max(s[-1]-d,s[-1]/2)
    q=np.array([np.interp(station,s,xy[:,j]) for j in (0,1)]+[np.interp(station,s,z)])
    if np.linalg.norm(q[:2]-np.array([-200.,-150.]))>200.:continue
    hit=json.loads(mcp.call('raycast',{'from':dict(zip(('x','y','z'),q+[0,0,.12])),'to':dict(zip(('x','y','z'),q-[0,0,.12])),'renderGeometry':False}))
    err=abs(hit.get('pt',{}).get('z',-9999)-q[2]);rows.append({'kind':kind,'q':q.tolist(),'hit':hit.get('hit',False),'error_m':err})
Path('.work-uk/boston-live-final.json').write_text(json.dumps(rows,indent=2))
bad=[r for r in rows if not r['hit'] or r['error_m']>.08]
print(json.dumps({'samples':len(rows),'passed':len(rows)-len(bad),'bad':bad[:15],'max_error_m':max((r['error_m'] for r in rows if r['hit']),default=0)},indent=2))
md.close();dd.pool.shutdown()

