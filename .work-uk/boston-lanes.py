import sys,json,numpy as np
from pathlib import Path
sys.path[:0]=['server'];import mapdata,netfetch,geodesy,roads,roadprofile
fr=geodesy.EnuFrame(42.3685,-71.063);md=mapdata.MapData(str(Path.home()/'.cache/beamng-earth'),netfetch.Fetcher(offline=True))
rows=[];seen=set()
for k in roads.cells_of_tile(fr,-1,-1):
 f=md.cell(k,layers=('roads',)).layers['roads'];specs=roads.bridge_specs(f);ground=roads.road_specs(f);tunnels=roads.tunnel_specs(f)
 for i in range(len(f)):
  fid=str(f.ids[i]);sp=specs[i] or ground[i] or tunnels[i]
  if fid in seen or sp is None or sp.cls not in ('motorway','trunk'):continue
  seen.add(fid);ring=f.parts(i)[0][0];x,y,_=fr.geodetic_to_enu(ring[:,1],ring[:,0],0.);xy=np.c_[x,y]
  if (xy.max(0)<[-500,-400]).any() or (xy.min(0)>[100,300]).any():continue
  tags=roadprofile.tags_for(f,i)
  rows.append({'fid':fid,'source':str(f.attrs['src_record'][i]),'class':sp.cls,'tags':{k:v for k,v in tags.items() if k in ('name','lanes','lanes:forward','lanes:backward','highway','shoulder','oneway')},'lanes':sp.lanes,'width':sp.width,'ranges':roads.level_ranges(f,i),'start':xy[0].tolist(),'end':xy[-1].tolist()})
Path('.work-uk/boston-lanes.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2));md.close()
