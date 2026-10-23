import json,sys,time,zipfile,os
from pathlib import Path
import numpy as np
sys.path[:0]=['server','tools']
import mapdata,mapcells,netfetch,roads,grading,geodesy,dem,roadprofile
cache='C:/Users/topge/.cache/beamng-earth'
net=netfetch.Fetcher(offline=True);md=mapdata.MapData(cache,net);dd=dem.Dem(cache+'/dem',fetcher=net)
fr=geodesy.EnuFrame(53.035,-1.25)
raw=lambda la,lo:dd.sample(la,lo,15)
gr=grading.Grader(fr,md,raw)
seen=set();rows=[]
for key in mapcells.cells_for_bbox(52.998,-1.278,53.067,-1.224):
 f=md.cell(key,layers=('roads',)).layers['roads']
 for i,sp in enumerate(roads.road_specs(f)):
  tags=roadprofile.tags_for(f,i)
  if sp is None or tags.get('highway')!='motorway' or str(f.ids[i]) in seen:continue
  seen.add(str(f.ids[i]))
  for ll in roads.ground_parts(f,i):
   x,y,_=fr.geodetic_to_enu(ll[:,1],ll[:,0],0.);xy,s=grading.resample(np.c_[x,y],8.)
   la,lo,_=fr.enu_to_geodetic(xy[:,0],xy[:,1],0.)
   keep=(la>=52.998)&(la<=53.067)
   if not keep.any():continue
   xy=xy[keep];la=la[keep];lo=lo[keep];base=raw(la,lo)
   z=gr.apply(la,lo,base,.04);natural=grading.plan_road(fr,ll,sp,raw)
   dist,at,ss=__import__('ukvertical').project(xy,natural.xy)
   nz=np.interp(at,ss,natural.z)+.04
   k=int(np.argmax(np.abs(z-nz)))
   row={'id':str(f.ids[i]),'length':round(s[-1],1),'worst_change':round(float(z[k]-nz[k]),3),
        'lat':float(la[k]),'lon':float(lo[k]),'generated':float(z[k]),'natural':float(nz[k]),'points':len(xy)}
   print(json.dumps(row),flush=True);rows.append(row)
Path('.work-uk/motorway-scan-'+('after' if '--after' in sys.argv else 'before')+'.json').write_text(json.dumps(rows,indent=2))
md.close();dd.pool.shutdown()
