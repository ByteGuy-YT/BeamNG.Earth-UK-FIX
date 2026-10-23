import sys,json,numpy as np
from pathlib import Path
sys.path[:0]=['server'];import mapdata,mapcells,netfetch,roads,roadprofile
md=mapdata.MapData(str(Path.home()/'.cache/beamng-earth'),netfetch.Fetcher(offline=True));seen=set();out=[]
for bounds,wanted in [((51.489,-.124,51.499,-.117),'vauxhall walk'),((52.998,-1.237,53.016,-1.222),'nottingham road')]:
 for k in mapcells.cells_for_bbox(*bounds):
  f=md.cell(k,layers=('roads',)).layers['roads']
  for i,sp in enumerate(roads.road_specs(f)):
   if sp is None or str(f.ids[i]) in seen:continue
   tags=roadprofile.tags_for(f,i)
   if tags.get('name','').lower()!=wanted:continue
   seen.add(str(f.ids[i]));ll=f.parts(i)[0][0]
   out.append({'name':wanted,'coords':ll.tolist(),'spec':str(sp)})
print(json.dumps(out,indent=2));Path('.work-uk/live-street-locations.json').write_text(json.dumps(out,indent=2));md.close()
