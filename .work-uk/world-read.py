import sys,json,numpy as np
sys.path.insert(0,'server');import geodesy,roads,roadprofile,mapdata,netfetch
md=mapdata.MapData('C:/Users/topge/.cache/beamng-earth',netfetch.Fetcher(offline=True));out={}
for name,lat,lon in [('london',51.4927,-.1204),('ikea',53.0017,-1.283),('j26',53.006,-1.246),('stelvio',46.528,-10.455),('boston',42.355,-71.055)]:
 fr=geodesy.EnuFrame(lat,lon);rows=[];seen=set()
 for key in roads.cells_of_tile(fr,0,0,margin=400):
  try:f=md.cell(key,layers=('roads',)).layers.get('roads')
  except Exception:continue
  if f is None:continue
  for i,sp in enumerate(roads.road_specs(f,lambda la,lo:np.ones(np.shape(la),bool))):
   fid=str(f.ids[i]);
   if not sp or fid in seen:continue
   seen.add(fid);ll=f.parts(i)[0][0];x,y,_=fr.geodetic_to_enu(ll[:,1],ll[:,0],0.)
   if np.min(np.hypot(x,y))>700:continue
   p=sp.profile;t=roadprofile.tags_for(f,i)
   rows.append({'id':fid,'width':sp.width,'cls':sp.cls,'walk':sp.walk,'dir':sp.dir,'drive':p.drive if p else None,'tags':t,'ll':ll.tolist()})
 out[name]=rows
 print(name,'ways',len(rows),'narrow',[(r['id'][:8],r['width'],r['drive'],{k:v for k,v in r['tags'].items() if not k.startswith('_')}) for r in rows if r['width']<4.1][:15])
from pathlib import Path
Path('.work-uk/world-roads-before.json').write_text(json.dumps(out,indent=2));md.close()

