import sys,json,time,math,os,statistics
from pathlib import Path
import numpy as np
root=Path.cwd();baseline=len(sys.argv)>1 and sys.argv[1]=='baseline'
sys.path.insert(0,str(root/('.work-uk/street-baseline/server' if baseline else 'server')))
os.environ['BEAMNG_EARTH_OSM_DB']=str(root/'.road-data/osm.sqlite')
import mapdata,mapcells,netfetch,geodesy,roads
md=mapdata.MapData('C:/Users/topge/.cache/beamng-earth',netfetch.Fetcher(offline=True))
flat=lambda la,lo:np.full(np.shape(la),20.)
rows=[]
for lat,lon,name in [(53.052,-1.299,'Underwood'),(53.0535,-1.3955,'Ripley'),(53.0493,-1.396,'school area'),(53.0471,-1.2565,'M1')]:
 fr=geodesy.EnuFrame(lat-128/111320,lon-128/(111320*math.cos(math.radians(lat))))
 fs=[md.cell(k,layers=('roads','landcover')).layers for k in roads.cells_of_tile(fr,0,0)]
 urban=lambda la,lo:np.logical_or.reduce([c['landcover'].sample(lo,la)==50 for c in fs])
 ms=[]
 for i in range(8):
  props=[];walks=[]
  t=time.perf_counter();roads.build_tile(fr,0,0,[c['roads'] for c in fs],flat,urban,walks=walks,props=props,left_hand=True);ms.append((time.perf_counter()-t)*1000)
 row={'site':name,'warm_median_ms':round(statistics.median(ms[2:]),3),'samples_ms':[round(x,3) for x in ms[2:]],'prop_count':len(props)}
 rows.append(row);print(json.dumps(row),flush=True)
md.close()
Path('.work-uk/street-benchmark-'+('before' if baseline else 'after')+'.json').write_text(json.dumps(rows,indent=2))
