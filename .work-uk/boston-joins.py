import sys,json,time
from pathlib import Path
import numpy as np
sys.path[:0]=['server']
import mapdata,netfetch,geodesy,roads,grading,dem,roadmesh
lat,lon=(42.2105,-71.) if 'south' in sys.argv else (42.3685,-71.063)
cache=str(Path.home()/'.cache/beamng-earth');net=netfetch.Fetcher(offline=True)
md=mapdata.MapData(cache,net);dd=dem.Dem(cache+'/dem',fetcher=net);fr=geodesy.EnuFrame(lat,lon)
raw=lambda la,lo:dd.sample(la,lo,15)
gr=grading.Grader(fr,md,raw);elev=lambda la,lo:gr.apply(la,lo,raw(la,lo),.04)
bp=roads.BridgeProfiles(fr,lambda k:md.cell(k,layers=('roads',)).layers.get('roads'),elev)
snapshots=[];chunks=[]
for tx,ty in [(x,y) for x in range(-3,3) for y in range(-2,4)]:
 fs=[md.cell(k,layers=('roads',)).layers.get('roads') for k in roads.cells_of_tile(fr,tx,ty)]
 chunks+=roads.build_tile(fr,tx,ty,fs,elev,bridges=bp)
 snapshots.append((tx,ty,{str(k):v[2].copy() for k,v in bp.done.items()}))
print('parts',len(bp.done),flush=True)
keys=sorted(bp.done);lines=[bp.done[k][1] for k in keys];nodes,edges,_=roads._chain_graph(lines)
by={}
for k,(a,b,s) in zip(keys,edges):
 for node,end in ((a,0),(b,-1)):by.setdefault(node,[]).append((k,end))
bad=[]
for node,entries in by.items():
 if len(entries)<2:continue
 zz=[float(bp.done[k][2][e]) for k,e in entries]
 if not all(np.isfinite(zz)):continue
 if max(zz)-min(zz)>.03:bad.append({'xy':nodes[node].tolist(),'dz':max(zz)-min(zz),'ends':[(k,e,z) for (k,e),z in zip(entries,zz)]})
bad.sort(key=lambda b:-b['dz']);print(json.dumps(bad[:30],indent=2),flush=True)
out={'lat':lat,'lon':lon,'parts':[{'key':k,'width':bp.done[k][0].width,'xy':bp.done[k][1].tolist(),'z':bp.done[k][2].tolist()} for k in keys], 'bad':bad,'chunks':chunks}
Path('.work-uk/boston-joins'+('-south' if 'south' in sys.argv else '')+'.json').write_text(json.dumps(out,default=lambda a:a.tolist() if hasattr(a,'tolist') else str(a)))
md.close();dd.pool.shutdown()
