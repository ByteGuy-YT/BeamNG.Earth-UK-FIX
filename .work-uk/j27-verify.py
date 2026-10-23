import sys,json
from pathlib import Path
import numpy as np
sys.path[:0]=['server','tools']
import mapdata,netfetch,roads,geodesy,navgraph,ukroadside
md=mapdata.MapData('C:/Users/topge/.cache/beamng-earth',netfetch.Fetcher(offline=True));fr=geodesy.EnuFrame(53.0634,-1.2691)
fs=[md.cell(k,layers=('roads',)).layers['roads'] for k in roads.cells_of_tile(fr,0,0)]
g=navgraph.build(fr,fs,lambda la,lo:np.zeros(np.shape(la)),(0,0),left_hand=True)
seen=set();lines=[]
for f in fs:
 for i,(rs,bs) in enumerate(zip(roads.road_specs(f),roads.bridge_specs(f))):
  sp=rs or bs;fid=str(f.ids[i])
  if sp and sp.profile and sp.profile.junction=='circular' and fid not in seen:
   seen.add(fid);ll=f.parts(i)[0][0];x,y,_=fr.geodetic_to_enu(ll[:,1],ll[:,0],0.);ln=np.c_[x,y]
   if np.min(np.linalg.norm(ln,axis=1))<200:lines.append(ln)
pts=np.concatenate(lines);centre=(pts.min(0)+pts.max(0))/2
live=json.loads(Path('.work-uk/j27-live.json').read_text());rings=[]
for e in live['edges']:
 p=np.array([e['p']['x'],e['p']['y']]);q=np.array([e['q']['x'],e['q']['y']]);mid=(p+q)/2
 if min(ukroadside._nearest_many(mid[None],ln)[0][0] for ln in lines)>2:continue
 if not e.get('oneWay'):rings.append({'oneway':False,'a':e['a'],'b':e['b']});continue
 if e['inNode']==e['b']:p,q=q,p
 d=q-p;r=(p+q)/2-centre;cross=float(r[0]*d[1]-r[1]*d[0]);rings.append({'oneway':True,'clockwise':cross<0,'cross':cross})
heads=[]
for s in live['signals']:
 for h in s['heads']:
  front=np.array([h['front']['x'],h['front']['y']]);inc=np.array([s['dir']['x'],s['dir']['y']]);heads.append(float(front@(-inc)))
r={'source_circular_ways':len(lines),'centre':centre.tolist(),'live_ring_links':len(rings),'oneway_clockwise':sum(e.get('clockwise',False) for e in rings),'wrong_links':[e for e in rings if not e.get('clockwise')],'head_front_dot_incoming':heads}
print(json.dumps(r,indent=2));Path('.work-uk/j27-verified.json').write_text(json.dumps(r,indent=2));md.close()
