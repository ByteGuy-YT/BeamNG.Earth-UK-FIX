exec(open('.work-uk/trace-humps.py').read().split("print('cell'")[0])
from unittest.mock import patch
import terrain_surface
la=np.array([53.0894400294184]);lo=np.array([-1.3044464426287825])
x,y,_=fr.geodetic_to_enu(la,lo,0.);point=np.array([x[0],y[0]])
# Direction of the mapped M1 (southeast); sections spanning every lane at its north abutment.
u=np.array([.52,-.854]);n=np.array([.854,.52]);q=np.array([point+u*along+n*off for along in (-8.,-2.,-.05,2.,8.) for off in (-8.,-4.,0.,4.,8.)])
a,b,_=fr.enu_to_geodetic(q[:,0],q[:,1],0.)
g=gr.apply(a,b,raw(a,b),.04)
with patch.object(gr.uk_vertical,'excavate',side_effect=lambda xy,base,lift,*_:base):before=gr.apply(a,b,raw(a,b),.04)
for along,rows in zip((-8.,-2.,-.05,2.,8.),np.arange(25).reshape(5,5)):
 print('AT',along,'raw',np.round(raw(a[rows],b[rows]),2).tolist(),'pre_cut',np.round(before[rows],2).tolist(),'final',np.round(g[rows],2).tolist(),flush=True)
for j in (2,4,12,14):
 print('POINT',j,q[j].tolist(),flush=True)
 for fid,p in gr._cell_plans(key):
  dist,at,s=ukvertical.project(q[[j]],p.xy)
  if dist[0]<p.half+1:print(fid,'distance',dist[0],'half',p.half,'height',np.interp(at[0],s,p.z),'at',at[0],s[-1],flush=True)
plans=gr.plans(a,b)
base=raw(a,b);current=grading.grade_points(q[:,0],q[:,1],base,plans,.04)
for title,pp in [('main',list(gr.uk_vertical.mainline_plans.values())),('upper',list(gr.uk_vertical.upper_plans.values()))]:
 candidate=grading.grade_points(q[:,0],q[:,1],current,pp,.04)
 weight=ukvertical.approach_ownership(q,plans,pp)
 print('LAYER',title,'before',current[10:15].tolist(),'candidate',candidate[10:15].tolist(),'weight',weight[10:15].tolist(),flush=True)
 for j in (10,14):
  for p in pp:
   dist,at,s=ukvertical.project(q[[j]],p.xy)
   if dist[0]<p.half+1:print(title,j,'dist',dist[0],'height',np.interp(at[0],s,p.z),'station',at[0],s[-1],flush=True)
 current+=weight*(candidate-current)
md.close();dd.pool.shutdown()
