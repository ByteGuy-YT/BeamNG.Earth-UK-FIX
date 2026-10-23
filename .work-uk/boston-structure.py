import sys,json,numpy as np
from pathlib import Path
sys.path[:0]=['server'];import mapdata,netfetch,geodesy,roads,mapcells,dem
fr=geodesy.EnuFrame(42.3685,-71.063);md=mapdata.MapData(str(Path.home()/'.cache/beamng-earth'),netfetch.Fetcher(offline=True))
out=[];seen=set()
for k in roads.cells_of_tile(fr,-1,-1):
 f=md.cell(k,layers=('roads',)).layers.get('roads')
 for i in range(len(f)):
  fid=str(f.ids[i]);lv=roads.level_ranges(f,i)
  if fid in seen or not lv:continue
  seen.add(fid);rows={}
  for name in ('flags','level'):
   r=f.rules.get(name)
   rows[name]=[(float(r.start[j]),float(r.end[j]),str(r.value[j])) for j in r.rows(i)] if r is not None else []
  rings=[]
  for p in f.parts(i):
   for r in p:
    x,y,_=fr.geodetic_to_enu(r[:,1],r[:,0],0);rings.append(np.c_[x,y].tolist())
  out.append({'fid':fid,'name':str(f.attrs.get('name',['']*len(f))[i]),'ranges':lv,'rules':rows,'xy':rings})
Path('.work-uk/boston-structures.json').write_text(json.dumps(out,indent=2))
for x in out:
 if any(v[2]=='tunnel' for v in x['ranges']):print(x['fid'],x['name'],x['ranges'],x['rules'])
md.close()
