import sys,json,time,pickle
from pathlib import Path
import numpy as np
sys.path[:0]=['server','tools']
import roads,grading,geodesy,mapcells,mapdata,netfetch,dem,roadprofile,ukvertical
cache=str(Path.home()/'.cache/beamng-earth')
net=netfetch.Fetcher(offline=True);md=mapdata.MapData(cache,net);dd=dem.Dem(cache+'/dem',fetcher=net)
lat,lon=map(float,sys.argv[1:3]) if len(sys.argv)>2 else (52.998153,-1.271675)
fr=geodesy.EnuFrame(lat,lon);raw=lambda a,b:dd.sample(a,b,15)
gr=grading.Grader(fr,md,raw);out=[]
key=mapcells.cell_of(lat,lon);f=md.cell(key,layers=('roads',)).layers['roads']
print('cell',key,flush=True)
seen=set()
for ck in [key,*key.neighbours()]:
 ff=md.cell(ck,layers=('roads',)).layers['roads']
 for i,sp in enumerate(roads.bridge_specs(ff)):
  if sp is None:continue
  fid=str(ff.ids[i]);tags=roadprofile.tags_for(ff,i)
  if fid in seen:continue
  seen.add(fid)
  for ll in roads.bridge_parts(ff,i):
   x,y,_=fr.geodetic_to_enu(ll[:,1],ll[:,0],0.);xy=roads.densify(np.c_[x,y],2.)
   if np.linalg.norm(xy,axis=1).min()>800:continue
   zz=gr.uk_vertical.deck(fid,xy)
   if zz is None:continue
   la,lo,_=fr.enu_to_geodetic(xy[:,0],xy[:,1],0.)
   data={'id':fid,'name':tags.get('name'),'highway':tags.get('highway'),'profile':str(sp.profile),'ll_ends':ll[[0,-1]].tolist(),'raw_ends':raw(la[[0,-1]],lo[[0,-1]]).tolist(),'deck_ends':zz[[0,-1]].tolist(),'length':float(np.linalg.norm(np.diff(xy,axis=0),axis=1).sum())}
   data['uk_raw_range']=[float(zz.min()),float(zz.max())]
   targets=[]
   for be in (0,-1):
    direction=xy[1]-xy[0] if be==0 else xy[-2]-xy[-1];direction/=np.linalg.norm(direction)
    # outside, endpoint, interior: use final graded surface, independent of deck.
    q=xy[be]+np.array([-20.,-8.,-2.,-.1,0.,.1,2.,8.,20.])[:,None]*direction
    a,b,_=fr.enu_to_geodetic(q[:,0],q[:,1],0.);base=raw(a,b)
    target=gr.apply(a,b,base,.04)
    targets.append({'raw':base.tolist(),'graded':target.tolist()})
   data['ends']=targets;out.append(data);print(json.dumps(data),flush=True)
Path('.work-uk/hump-trace-'+str(lat)+'.json').write_text(json.dumps(out,indent=2))
# Ground A roads/motorways: exact profile modifications, max grade and nearby target.
seen=set();stats=[]
for ck in [key,*key.neighbours()]:
 ff=md.cell(ck,layers=('roads',)).layers['roads']
 specs=roads.road_specs(ff)
 for i,sp in enumerate(specs):
  if sp is None or sp.profile is None or sp.cls not in ('motorway','trunk','primary'):continue
  fid=str(ff.ids[i]);tags=roadprofile.tags_for(ff,i)
  if fid in seen:continue
  seen.add(fid)
  for ll in roads.ground_parts(ff,i):
   p=grading.plan_road(fr,ll,sp,raw)
   if np.linalg.norm(p.xy,axis=1).min()>800:continue
   plans=[(fid,p)];gr.uk_vertical.adjust(plans,[sp]);zp=plans[0][1].z
   k=int(abs(zp-p.z).argmax());la,lo,_=fr.enu_to_geodetic(*p.xy[k],0.)
   row={'id':fid,'name':tags.get('name'),'ref':tags.get('ref'),'highway':tags.get('highway'),'offset':sp.profile.surface_offset,'width':sp.width,'max_change':float(zp[k]-p.z[k]),'at':[float(la),float(lo)],'z':float(zp[k]),'raw_plan':float(p.z[k]),'near_z':float(zp[np.linalg.norm(p.xy,axis=1).argmin()]),'length':float(np.linalg.norm(np.diff(p.xy,axis=0),axis=1).sum())}
   stats.append(row);print('GROUND',json.dumps(row),flush=True)
Path('.work-uk/hump-ground-'+str(lat)+'.json').write_text(json.dumps(stats,indent=2))
md.close();dd.pool.shutdown()
