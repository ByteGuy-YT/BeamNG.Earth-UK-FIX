import sys,json,time
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path[:0]=['server','tools']
import roads,roadprofile,ukroadside,furniture,geodesy,mapdata,mapcells,netfetch,navgraph,mcp
md=mapdata.MapData('C:/Users/topge/.cache/beamng-earth',netfetch.Fetcher(offline=True));fr=geodesy.EnuFrame(53.035,-1.25)
rr=[];seen=set();fs=[]
for key in mapcells.cells_for_bbox(52.998,-1.278,53.067,-1.224):
 f=md.cell(key,layers=('roads',)).layers['roads'];fs.append(f)
 for i,(rs,bs) in enumerate(zip(roads.road_specs(f),roads.bridge_specs(f))):
  sp=rs or bs;fid=str(f.ids[i])
  if sp is None or not sp.profile or sp.profile.highway!='motorway' or fid in seen:continue
  seen.add(fid)
  for ll in f.parts(i)[0]:
   x,y,_=fr.geodetic_to_enu(ll[:,1],ll[:,0],0.);ln=roads.offset_polyline(np.c_[x,y,np.full(len(x),100.)],sp.profile.surface_offset)
   rr.append((fid,sp,ln,0.))
tiles=set();probes=[]
for fid,sp,ln,_ in rr:
 L=furniture._arclen(ln)[-1];p,t=furniture._at(ln,np.arange(8,L-8,4.));la,_,_=fr.enu_to_geodetic(p[:,0],p[:,1],0.)
 p=p[(la>=53.001)&(la<=53.063)];t=t[(la>=53.001)&(la<=53.063)]
 for q in p:tiles.add(tuple(np.floor(q[:2]/256).astype(int)))
 bd=np.full(len(p),np.inf);bq=np.zeros_like(p)
 for ofid,osp,ol,_ in rr:
  if ofid==fid:continue
  d,q,ot=ukroadside._nearest_many(p,ol);dot=np.sum(t*sp.dir*ot*osp.dir,axis=1)
  good=(d<bd)&(d<40)&(dot<-.95)&(d>(sp.width+osp.width)/2+.2)
  bd[good]=d[good];bq[good]=q[good]
 good=np.isfinite(bd);probes.extend((p[good,:2]+bq[good,:2])/2)
chunks=[];start=time.perf_counter()
with patch.object(ukroadside.ukcontext,'near',return_value=()):
 for tx,ty in sorted(tiles):chunks.extend(c for c in ukroadside.chunks(fr,rr,(tx*256,ty*256,(tx+1)*256,(ty+1)*256),None) if c['m']=='bne_bridge_concrete')
segments=[]
for c in chunks:
 p,u,L,*_=c['box3d'];p=np.array(p[:2]);u=np.array(u);segments.append([p-u*L/2,p+u*L/2])
pp=np.array(probes);dist=np.full(len(pp),np.inf)
for ln in segments:
 d,_,_=ukroadside._nearest_many(pp,np.array(ln));dist=np.minimum(dist,d)
bad=pp[dist>2.]
summary={'tiles':len(tiles),'divider_segments':len(chunks),'generation_seconds':time.perf_counter()-start,'probe_count':len(pp),'within_2m':int((dist<=2).sum()),'worst_distance':float(dist.max()),'missing_gps':[list(fr.enu_to_geodetic(p[0],p[1],0.)[:2]) for p in bad[::max(1,len(bad)//20)]]}
print(json.dumps(summary,indent=2));Path('.work-uk/divider-route.json').write_text(json.dumps(summary,indent=2));md.close()
