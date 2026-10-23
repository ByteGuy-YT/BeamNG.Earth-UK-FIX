import sys,json
from pathlib import Path
sys.path.insert(0,'server')
import mapdata,mapcells,netfetch,roads
md=mapdata.MapData('C:/Users/topge/.cache/beamng-earth',netfetch.Fetcher())
rows=[]
for lat,lon,name in [(53.052,-1.299,'underwood'),(53.0634,-1.2691,'j27'),(53.025,-1.25,'m1'),(52.9899,-1.2346,'j26'),(53.013,-1.315,'a610'),(53.054,-1.393,'ripley')]:
 f=md.cell(mapcells.cell_of(lat,lon),layers=('roads',)).layers['roads']
 print(name,len(f),flush=True)
 specs=roads.road_specs(f)
 for i,sp in enumerate(specs):
  sp=sp or roads.bridge_specs(f)[i]
  if sp is None:continue
  tags=json.loads(f.attrs['osm_tags'][i]);ll=f.lonlat[f.coord_off[f.ring_off[f.part_off[i]]]:f.coord_off[f.ring_off[f.part_off[i+1]]]]
  dist=((ll[:,0]-lon)**2*.36+(ll[:,1]-lat)**2).min()**.5*111320
  if dist<1300 and (sp.cls in ('motorway','trunk','primary') or tags.get('name') in ('Main Road','Fairview Avenue','Nottingham Road','Mansfield Road')):
   row={'site':name,'id':str(f.ids[i]),'class':sp.cls,'width':sp.width,'lanes':[sp.profile.forward,sp.profile.backward],'dir':sp.dir,'source':sp.profile.source,'dual':sp.median,'match':str(f.attrs['osm_match'][i]),'tags':{k:v for k,v in tags.items() if not k.startswith('_')},'width_rule':str(roads._rule_value(f.rules.get('width'),i)),'ranges':roads.level_ranges(f,i),'ll':ll.tolist()}
   rows.append(row)
Path('.work-uk/diagnosis.json').write_text(json.dumps(rows,indent=2))
md.close()
for r in rows:
 print(r['site'],r['class'],r['tags'].get('name',r['tags'].get('ref')),r['width'],r['lanes'],r['dir'],r['source'],r['tags'].get('lanes'),r['tags'].get('oneway'),r['dual'],r['ranges'])
