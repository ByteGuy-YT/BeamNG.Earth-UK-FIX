import sys,json,numpy as np
from pathlib import Path
sys.path[:0]=['server','tools'];import cdae,mcp
p=Path('C:/Users/topge/AppData/Local/BeamNG/BeamNG.drive/current/temp/beamngEarth/20261022-012146-9efe/deck_5_-1_0.cdae');s=cdae.read(p);rows=[]
for j,m in enumerate(s['meshes']):
 v=np.frombuffer(m['verts'][2],'<f4').reshape(-1,3).astype(float);t=np.frombuffer(m['indices'][2],'<u4').reshape(-1,3);n=np.frombuffer(m['norms'][2],'<f4').reshape(-1,3)
 centres=v[t].mean(1);good=(n[t][:,:,2].mean(1)>.8)&(centres[:,2]>0)&(centres[:,0]>10)&(centres[:,0]<245)&(centres[:,1]>10)&(centres[:,1]<245)
 ks=np.flatnonzero(good)
 for k in ks[::max(1,len(ks)//3)][:3]:
  q=centres[k]+[-256,0,0]
  result=json.loads(mcp.call('raycast',{'from':dict(zip(('x','y','z'),q+[0,0,.25])),'to':dict(zip(('x','y','z'),q-[0,0,.25])),'renderGeometry':False}))
  rows.append({'part':j,'expected':q.tolist(),'hit':result.get('hit'),'error':result.get('pt',{}).get('z',-999)-q[2]})
print(json.dumps(rows,indent=2));Path('.work-uk/boston-collision.json').write_text(json.dumps(rows,indent=2))

