import sys
sys.path[:0]=['server','server/tests']
from test_road_interfaces import *
f=uk(lines=[[(-150,0),(-5,0)],[(-5,0),(5,0)],[(5,0),(21,0)],[(21,0),(180,0)]],
 classes=['trunk']*4,tags=[{'highway':'trunk','oneway':'yes'},{'highway':'trunk','oneway':'yes','bridge':'yes'}, {'highway':'trunk','oneway':'yes'},{'highway':'trunk','oneway':'yes'}])
def raw(la,lo):
 x,_,_=FRAME.geodetic_to_enu(la,lo,0.);return 20.-5*np.exp(-((x-5)/3)**2)
g=grading.Grader(FRAME,FakeMD(f),raw)
x=np.arange(8.,160.,2.);la,lo,_=FRAME.enu_to_geodetic(x,np.zeros(len(x)),0.);z=g.apply(la,lo,raw(la,lo))
print(np.c_[x,z].tolist())
for key,p in g.uk_vertical.mainline_plans.items():
 print('PLAN',key,p.xy[[0,-1]],p.z[[0,-1]],'maxgrade',(abs(np.diff(p.z))/np.linalg.norm(np.diff(p.xy,axis=0),axis=1)).max())
