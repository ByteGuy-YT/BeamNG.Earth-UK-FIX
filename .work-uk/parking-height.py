import sys,numpy as np
from pathlib import Path
sys.path[:0]=['server'];import cdae
root=Path('C:/Users/topge/AppData/Local/BeamNG/BeamNG.drive/current/temp/beamngEarth/20261022-014943-13e6')
def sample(p,q):
 s=cdae.read(str(p));found=[]
 for m in s['meshes']:
  v=np.frombuffer(m['verts'][2],'<f4').reshape(-1,3).astype(float)
  t=np.frombuffer(m['indices'][2],'<u4').reshape(-1,3);tri=v[t]
  # query relative to tile origin
  a=tri[:,0,:2];ab=tri[:,1,:2]-a;ac=tri[:,2,:2]-a;d=q-a
  den=ab[:,0]*ac[:,1]-ab[:,1]*ac[:,0];safe=np.where(abs(den)>1e-10,den,1)
  u=(d[:,0]*ac[:,1]-d[:,1]*ac[:,0])/safe;w=(ab[:,0]*d[:,1]-ab[:,1]*d[:,0])/safe
  good=(abs(den)>1e-10)&(u>=-1e-5)&(w>=-1e-5)&(u+w<=1.00001)
  found.extend((tri[:,0,2]+u*(tri[:,1,2]-tri[:,0,2])+w*(tri[:,2,2]-tri[:,0,2]))[good])
 return sorted(set(round(float(z),5) for z in found))
p=root/'road_2_-1_-1.cdae'
for q in ([-150,-150],[-160,-140],[-180,-140],[-190,-130],[-200,-100],[-220,-100]):print(q,sample(p,np.array(q)+256))
