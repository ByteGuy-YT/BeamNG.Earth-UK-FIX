exec(open('.work-uk/trace-humps.py').read().split("print('cell'")[0])
from unittest.mock import patch
import terrain_surface
q=np.array([[0.,-2.],[0.,0.],[0.,2.]])
a,b,_=fr.enu_to_geodetic(q[:,0],q[:,1],0.)
z=gr.apply(a,b,raw(a,b),.04);print('OUT',z,flush=True)
plans=gr.plans(a,b)
print('PLANS',flush=True)
for ck,rows in gr.cells.items():
 for fid,p in rows:
  distance,at,s=ukvertical.project(q,p.xy)
  if distance.min()>p.half:continue
  print(fid,'distance',distance.tolist(),'half',p.half,'height',np.interp(at,s,p.z).tolist(),'stations',at.tolist(),'len',s[-1],'end_ids',p.end_ids,'endZ',p.z[[0,-1]].tolist(),flush=True)
for name,pp in [('mainline',list(gr.uk_vertical.mainline_plans.values())),('upper',list(gr.uk_vertical.upper_plans.values()))]:
 mask,tgt=ukvertical.core_mask(q,pp,heights=True);print('CORE',name,mask,tgt,flush=True)
 for p in pp:
  distance,at,s=ukvertical.project(q,p.xy)
  if distance.min()>p.half:continue
  print(' ',name,'distance',distance.tolist(),'half',p.half,'height',np.interp(at,s,p.z).tolist(),'stations',at.tolist(),'len',s[-1],'endZ',p.z[[0,-1]].tolist(),flush=True)
md.close();dd.pool.shutdown()
