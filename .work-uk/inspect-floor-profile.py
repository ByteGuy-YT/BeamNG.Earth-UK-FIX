exec(open('.work-uk/trace-humps.py').read().split("print('cell'")[0])
q=np.array([[-25.,-25.],[25.,25.]])
a,b,_=fr.enu_to_geodetic(q[:,0],q[:,1],0.)
gr.apply(a,b,raw(a,b),.04);m=gr.uk_vertical
for key,p in {**m.mainline_plans,**m.upper_plans}.items():
 if not key[0].startswith(sys.argv[3]):continue
 sp=m.floor_specs[key]
 xy,s=grading.resample(p.xy,2.)
 d,at,_=ukvertical.project(np.zeros((1,2)),xy)
 if d[0]>150:continue
 k=int(abs(s-at[0]).argmin());sl=slice(max(0,k-10),min(len(s),k+11));xy=xy[sl];ss=s[sl]
 tangent=np.gradient(xy,axis=0);tangent/=np.maximum(np.linalg.norm(tangent,axis=1),1e-9)[:,None]
 normal=np.c_[-tangent[:,1],tangent[:,0]]
 side=int(sys.argv[4]) if len(sys.argv)>4 else 1
 probe=xy+normal*(sp.profile.offset+(-1 if side==1 else 1)*sp.profile.drive*.475)
 _,st,arc=ukvertical.project(probe,p.xy);base=np.interp(st,arc,p.z)
 inter=m.road_interfaces(probe,base,p,m.near(probe,40.))
 out=m.road_heights(probe,p)
 print('ROAD',key[0],sp.profile.highway,'ENDS',p.xy[[0,-1]],p.z[[0,-1]],p.end_ids,'MAXGRADE',float((abs(np.diff(p.z))/np.diff(arc)).max()),flush=True)
 print('VALUES',np.c_[ss,base,inter,out].tolist(),flush=True)
 for pos,identity in zip(p.xy[[0,-1]],p.end_ids):
  print('NODE',identity,'base',m.endpoint_height(pos,identity),'aligned',m.aligned_endpoint(pos,identity),'raw',m.sample(pos[None])[0],flush=True)
 for line,z,half,name in m.near(p.xy[[0,-1]],60.):
  for e in (0,-1):
   if np.linalg.norm(p.xy[[0,-1]]-line[e],axis=1).min()<10:
    print('DECK',name,e,'point',line[e],'z',z[e],'other',z[1 if e==0 else -2],'ids',getattr(line,'end_ids',None),'hwy',m.highways.get(name),flush=True)
md.close();dd.pool.shutdown();dd.urgent_pool.shutdown()
