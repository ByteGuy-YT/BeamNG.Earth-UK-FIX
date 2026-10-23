import sys,json
from pathlib import Path
import numpy as np
sys.path[:0]=['server','tools'];import cdae,mcp
state=json.loads(mcp.call('run_lua',{'code':"local o={};require('beamngEarth/farfield').eachTile(function(t) if t.shown and not t.hidden and t.x0<0 and t.x1>-256 and t.y0<0 and t.y1>-256 then table.insert(o,t) end end);return jsonEncode(o)"}))
root=Path('C:/Users/topge/AppData/Local/BeamNG/BeamNG.drive/current')
def read(path,off):
 s=cdae.read(str(path));out=[]
 for m in s['meshes']:
  v=np.frombuffer(m['verts'][2],'<f4').reshape(-1,3).astype(float)+off
  t=np.frombuffer(m['indices'][2],'<u4').reshape(-1,3)
  out.append((v,t))
 return out
ground={}
for row in sorted(state,key=lambda r:-r['level']):
 for v,t in read(root/row['shape'].lstrip('/'),[row['x'],row['y'],row['z']]):
  for p in v:
   key=tuple(np.round(p[:2],5));ground[key]=max(ground.get(key,-np.inf),p[2])
def z_at(q):
 ij=np.floor(q/2).astype(int);a,b=(q/2-ij).T
 corners=[ij,ij+[1,0],ij+[0,1],ij+[1,1]]
 z00,z10,z01,z11=[np.array([ground.get(tuple(p*2),np.nan) for p in xx]) for xx in corners]
 z45=np.where(a>=b,z00+a*(z10-z00)+b*(z11-z10),z00+a*(z11-z01)+b*(z01-z00))
 z135=np.where(a+b<=1,z00+a*(z10-z00)+b*(z01-z00),z11+(1-a)*(z01-z11)+(1-b)*(z10-z11))
 return np.where(ij.sum(1)%2==0,z45,z135)
session=state[0]['session'];path=root/'temp/beamngEarth'/session/'road_1_-1_-1.cdae'
rows=[]
for v,t in read(path,[-256,-256,0]):
 tri=v[t];q=tri.mean(1);d=q[:,2]-z_at(q[:,:2]);good=np.isfinite(d)
 bad=np.flatnonzero(good&(d<-.005))
 rows.extend([{'q':q[j].tolist(),'dz':float(d[j])} for j in bad[::max(1,len(bad)//20)][:20]])
 print('vertices',len(v),'tris',len(t),'sampled',int(good.sum()),'under',len(bad),'min',float(d[good].min()),'percentiles',np.percentile(d[good],[0,1,10,50,90,99,100]).tolist())
 s=cdae.read(str(path));m=s['meshes'][0];pr=np.frombuffer(m['primitives'][2],'<u4').reshape(-1,3)
 for start,count,typ in pr:
  ds=d[start//3:(start+count)//3];nm=s['materials'][int(typ)&0xfffffff]['name']
  ok=np.isfinite(ds);print(nm,len(ds),np.percentile(ds[ok],[0,1,10,50,99,100]).tolist())
  if nm=='bne_sidewalk_brick':
   ix=np.arange(start//3,(start+count)//3);bb=ix[(d[ix]<-.01)&np.isfinite(d[ix])];print('brickbad',q[bb[::max(1,len(bb)//10)]].tolist())
print(json.dumps({'terrain':[{k:r[k] for k in ('key','shape','x','y','z','level')} for r in state],'bad':rows},indent=2))
Path('.work-uk/live-parking-audit.json').write_text(json.dumps({'bad':rows},indent=2))
