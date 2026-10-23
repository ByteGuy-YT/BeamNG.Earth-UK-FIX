import sys,json,time
from pathlib import Path
import numpy as np
sys.path.insert(0,'server')
import mapdata,mapcells,netfetch,roads,grading,geodesy,dem
cache='C:/Users/topge/.cache/beamng-earth'
net=netfetch.Fetcher(offline=True)
md=mapdata.MapData(cache,net)
d=dem.Dem(cache+'/dem',fetcher=net)
lat,lon=map(float,sys.argv[1:3]) if len(sys.argv)>2 else (53.028,-1.251)
fr=geodesy.EnuFrame(lat,lon)
raw=lambda la,lo:d.sample(la,lo,15)
gr=grading.Grader(fr,md,raw)
elev=lambda la,lo:gr.apply(la,lo,raw(la,lo),grading.ROAD_LIFT)
f=md.cell(mapcells.cell_of(lat,lon),layers=('roads',)).layers['roads']
bp=roads.BridgeProfiles(fr,lambda k:md.cell(k,layers=('roads',)).layers['roads'],elev)
start=time.perf_counter()
parts=bp.parts([f],(-1000,-1000,1000,1000))
print('decks',len(parts),'seconds',round(time.perf_counter()-start,2),flush=True)
out=[]
for fid,sp,xy,z,lo in parts:
 if sp.cls not in ('motorway','trunk','primary'):continue
 s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
 maxgrade=float(np.max(np.abs(np.diff(z))/np.maximum(np.diff(s),1e-9)))
 p=xy[[0,-1]];la,lo,_=fr.enu_to_geodetic(p[:,0],p[:,1],0.)
 _,_,gz=fr.geodetic_to_enu(la,lo,elev(la,lo))
 row={'id':fid,'class':sp.cls,'length':round(s[-1],2),'width':sp.width,'grade':round(maxgrade,3),'step':np.round(z[[0,-1]]-gz,3).tolist(),'xy':xy.tolist(),'z':z.tolist()}
 out.append(row)
 print({k:v for k,v in row.items() if k not in ('xy','z')},flush=True)
Path(f'.work-uk/vertical-{lat}-{lon}.json').write_text(json.dumps(out,indent=2))
md.close();d.pool.shutdown()
