exec(open('.work-uk/trace-humps.py').read().split("print('cell'")[0])
q=np.array([[-60.,-60.],[60.,60.]])
a,b,_=fr.enu_to_geodetic(q[:,0],q[:,1],0.);gr.apply(a,b,raw(a,b),.04)
m=gr.uk_vertical;rows={**m.mainline_plans,**m.upper_plans};rows={k:p for k,p in rows.items() if ukvertical.project(np.zeros((1,2)),p.xy)[0][0]<100.}
ends={}
for key,p in rows.items():
 sp=m.floor_specs[key]
 topology=roads.offset_polyline(np.c_[p.xy,np.zeros(len(p.xy))],-sp.profile.surface_offset)[:,:2] if sp.profile.surface_offset else p.xy
 for e in (0,-1):
  if np.linalg.norm(topology[e])>100.:continue
  identity=p.end_ids[e]
  if identity is not None:ends.setdefault(identity,[]).append((key,p,topology[e]))
for identity,values in ends.items():
 if len(values)<2:continue
 centre=np.mean([v[2] for v in values],axis=0);r=max(m.floor_specs[k].width/2 for k,_,_ in values)+2
 axis=np.arange(-r,r+1);x,y=np.meshgrid(axis,axis);points=np.c_[x.ravel(),y.ravel()]+centre
 heights=[]
 for key,p,_ in values:
  d,at,s=ukvertical.project(points,p.xy);h=m.road_heights(points,p);h[d>m.floor_specs[key].width/2]=np.nan;heights.append(h)
 hh=np.array(heights);valid=np.isfinite(hh).sum(0)>=2
 if valid.any():
  gap=np.nanmax(hh[:,valid],axis=0)-np.nanmin(hh[:,valid],axis=0);j=np.nanargmax(gap);pos=points[valid][j]
  print('JUNCTION',identity,'arms',len(values),'gap',float(gap[j]),'position',pos,'plane',m.junction_plane(centre,identity),flush=True)
for key,p in rows.items():
 sp=m.floor_specs[key];s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(p.xy,axis=0),axis=1))];at=np.arange(0.,s[-1],2.)
 xy=np.c_[np.interp(at,s,p.xy[:,0]),np.interp(at,s,p.xy[:,1])];xy=xy[np.linalg.norm(xy,axis=1)<80.]
 if len(xy)<2:continue
 normal=__import__('roadmesh')._normals(xy);points=np.r_[xy+normal*sp.width/2,xy-normal*sp.width/2]
 a,b,_=fr.enu_to_geodetic(points[:,0],points[:,1],0.);ground=gr.apply(a,b,raw(a,b),.04)
 ground=fr.geodetic_to_enu(a,b,ground)[2];floor=m.road_heights(points,p);gap=floor-ground
 print('EDGE',key[0],'range',float(gap.min()),float(gap.max()),'position',points[np.argmax(gap)],flush=True)
 if gap.max()>.15:
  pos=points[[np.argmax(gap)]]
  for kk,pp in {**m.mainline_plans,**m.upper_plans}.items():
   d,_,_=ukvertical.project(pos,pp.xy)
   if d[0]<pp.half+2:print(' CONFLICT',kk[0],'distance',d,'half',pp.half,'height',m.road_heights(pos,pp),'ENDS',pp.xy[[0,-1]],'ids',pp.end_ids,flush=True)
md.close();dd.pool.shutdown();dd.urgent_pool.shutdown()
