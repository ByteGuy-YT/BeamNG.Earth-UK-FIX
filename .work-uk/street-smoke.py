import sys,json,time,math
from pathlib import Path
import numpy as np
sys.path.insert(0,'server')
import mapdata,mapcells,netfetch,geodesy,roads,roadmesh,navgraph,ukcontext,buildings
md=mapdata.MapData('C:/Users/topge/.cache/beamng-earth',netfetch.Fetcher(offline=True))
flat=lambda la,lo:np.full(np.shape(la),20.)
results=[]
for lat,lon,name in [(53.052,-1.299,'Underwood'),(53.0535,-1.3955,'Ripley fuel'),(53.0493,-1.396,'Ripley school'),(53.0471,-1.2565,'M1'),(52.99747,-1.28042,'Shell canopy'),(53.0201,-1.3251,'Nethergreen forecourt')]:
 fr=geodesy.EnuFrame(lat-128/111320,lon-128/(111320*math.cos(math.radians(lat))))
 fs=[md.cell(k,layers=('roads','landcover')).layers for k in roads.cells_of_tile(fr,0,0)]
 urban=lambda la,lo:np.logical_or.reduce([c['landcover'].sample(lo,la)==50 for c in fs])
 timings=[]
 for i in range(4):
  walks=[];props=[];lines=[]
  t=time.perf_counter();chunks=roads.build_tile(fr,0,0,[c['roads'] for c in fs],flat,urban,walks=walks,props=props,lines=lines,left_hand=True);timings.append((time.perf_counter()-t)*1000)
 graph=navgraph.build(fr,[c['roads'] for c in fs],flat,(128,128),urban_fn=urban,left_hand=True)
 counts={g:sum(r[0]==g for r in props) for g in sorted({r[0] for r in props})}
 row={'site':name,'tile_ms':timings,'props':counts,'signal_junctions':len(graph['signals']),'cameras_in_graph':len(graph['cameras']),'records':len(ukcontext.near(fr,(0,0,256,256)))}
 try:
  items=buildings.road_tile_items(fr,0,0,md,flat)
  ukcontext.decorate_buildings(fr,(0,0,256,256),items)
  snapshot=[(x.ring.copy(),x.height,x.floors,x.roof) for x,_,_ in items]
  output=buildings.road_tile(fr,0,0,md,flat,lines=lines,props=props,items=items)
  for (spec,_,_),old in zip(items,snapshot):
   assert np.array_equal(spec.ring,old[0]) and (spec.height,spec.floors,spec.roof)==old[1:]
  if output:
   for mesh in output[0]:assert np.isfinite(mesh[0]).all()
  row['fuel_pump_assets']=sum(r[0]=='ukfuelpump' for r in props)
  row['buildings']=len(items);row['special']=[(s.cls,s.uk_use,s.height,len(s.ring)) for s,_,_ in items if s.uk_use]
 except Exception as e:row['building_data_error']=str(e)[:200]
 results.append(row);print(json.dumps(row),flush=True)
Path('.work-uk/street-smoke.json').write_text(json.dumps(results,indent=2))
md.close()

