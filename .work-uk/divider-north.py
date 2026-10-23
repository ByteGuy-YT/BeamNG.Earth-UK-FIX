import sys,math
import numpy as np
sys.path.insert(0,'server')
import roads,ukroadside,roadprofile,geodesy,mapdata,netfetch
md=mapdata.MapData('C:/Users/topge/.cache/beamng-earth',netfetch.Fetcher(offline=True))
fr=geodesy.EnuFrame(53.05668,-1.26075)
cells=[md.cell(k,layers=('roads',)).layers['roads'] for k in roads.cells_of_tile(fr,0,0)]
seen=set();rr=[]
for f in cells:
 for i,sp in enumerate(roads.road_specs(f)):
  if sp is None or sp.cls!='motorway' or str(f.ids[i]) in seen:continue
  seen.add(str(f.ids[i]))
  for ll in roads.ground_parts(f,i):
   x,y,z=fr.geodetic_to_enu(ll[:,1],ll[:,0],0.);line=roads.offset_polyline(np.c_[x,y,np.full(len(x),150.)],sp.profile.surface_offset)
   rr.append((str(f.ids[i]),sp,line,0))
   tags=roadprofile.tags_for(f,i)
   if np.min(np.linalg.norm(line[:,:2],axis=1))<600:print(str(f.ids[i]),tags.get('highway'),sp.dir,sp.profile.forward,sp.profile.backward,sp.width,sp.profile.drive,sp.profile.offset,'min',np.min(np.linalg.norm(line[:,:2],axis=1)))
for fid,sp,line,_ in rr:
 dd,p,t=ukroadside._nearest_many(np.array([[0.,0.,0.]]),line)
 if dd[0]>25:continue
 for ofid,osp,other,_ in rr:
  if ofid==fid:continue
  d,q,ot=ukroadside._nearest_many(p,other)
  dot=float((t*(sp.dir or 1)*ot*(osp.dir or 1)).sum())
  if d[0]<45:print('pair',fid[:8],ofid[:8],'distance',d[0],'dot',dot,'gap',d[0]-(sp.profile.drive+osp.profile.drive)/2)
cc=ukroadside.chunks(fr,rr,(-256,-256,256,256),lambda la,lo:np.zeros(np.shape(la)))
print('barriers',sum(c['m']=='bne_bridge_concrete' for c in cc))
md.close()
