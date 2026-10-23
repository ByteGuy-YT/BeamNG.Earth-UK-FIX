exec(open('.work-uk/trace-humps.py').read().split("print('cell'")[0])
q0=np.array([[-30.,-30.],[30.,30.]])
a,b,_=fr.enu_to_geodetic(q0[:,0],q0[:,1],0.);gr.apply(a,b,raw(a,b),.04)
m=gr.uk_vertical
for key,p in {**m.mainline_plans,**m.upper_plans}.items():
 if not key[0].startswith(sys.argv[3]):continue
 dist,station,s=ukvertical.project(np.zeros((1,2)),p.xy)
 if dist[0]>3.:continue
 j=min(len(p.xy)-2,max(0,np.searchsorted(s,station[0])-1));u=p.xy[j+1]-p.xy[j];u/=np.linalg.norm(u);v=np.array([-u[1],u[0]])
 sp=m.floor_specs[key];side=sp.profile.offset-.475*sp.profile.drive
 q=v*side+np.arange(-2.,4.)[:,None]*u
 _,at,s=ukvertical.project(q,p.xy);base=np.interp(at,s,p.z)
 jun=m.junction_interfaces(q,base,p);inter=m.road_interfaces(q,jun,p,m.near(q,40.));mask,common=m.surface(q,reference=inter)
 print('ROAD',key[0],p.end_ids,'probe',q,flush=True)
 print('BASE',base,'JUNCTION',jun,'INTERFACE',inter,'COMMON',common,'ACTUAL',m.road_heights(q,p),flush=True)
 for kk,pp in {**m.mainline_plans,**m.upper_plans}.items():
  d,at,s=ukvertical.project(q,pp.xy)
  if (d>pp.half+2).all():continue
  z=np.interp(at,s,pp.z);jj=m.junction_interfaces(q,z,pp);ii=m.road_interfaces(q,jj,pp,m.near(q,40.))
  print(' CANDIDATE',kk[0],'distance',d,'half',pp.half,'base',z,'JUN',jj,'INT',ii,'ends',pp.xy[[0,-1]],flush=True)
md.close();dd.pool.shutdown();dd.urgent_pool.shutdown()
