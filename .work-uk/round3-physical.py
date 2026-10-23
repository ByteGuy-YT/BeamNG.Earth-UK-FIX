import sys,json
from pathlib import Path
sys.path[:0]=['tools','server']
import mcp,geodesy
north='--north' in sys.argv
fr=geodesy.EnuFrame(53.05668,-1.26075) if north else geodesy.EnuFrame(53.007221667994,-1.2352589323031)
rows=json.loads(Path('.work-uk/motorway-scan-before.json').read_text())
out=[]
for r in rows:
 if north and not -5<r['worst_change']<-2:continue
 if not north and r['worst_change']> -5:continue
 x,y,_=fr.geodetic_to_enu(r['lat'],r['lon'],0.)
 z=r['natural']
 result=mcp.call('raycast',{'from':{'x':float(x),'y':float(y),'z':z+1.5},
                            'to':{'x':float(x),'y':float(y),'z':z-3.},'renderGeometry':False})
 out.append({'source_before':r,'world_xy':[x,y],'physics_raycast':result});print(out[-1])
Path('.work-uk/round3-physical'+('-north' if north else '')+'.json').write_text(json.dumps(out,indent=2))
