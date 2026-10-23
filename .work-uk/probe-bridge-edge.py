exec(open('.work-uk/trace-humps.py').read().split("print('cell'")[0])
qlat,qlon=map(float,sys.argv[3:5]);x,y,_=fr.geodetic_to_enu(qlat,qlon,0.);q0=np.array([[x-20,y-20],[x+20,y+20]])
a,b,_=fr.enu_to_geodetic(q0[:,0],q0[:,1],0.);gr.apply(a,b,raw(a,b),.04);m=gr.uk_vertical
for line,z,half,name in m.near(q0,10.):
 if not name.startswith(sys.argv[5]):continue
 end=int(sys.argv[6]);other=1 if end==0 else -2
 off=m.pavements[name][1];shift=roads.offset_polyline(np.c_[line,z],off)
 u=shift[end,:2]-shift[other,:2];u/=np.linalg.norm(u);v=np.array([-u[1],u[0]])
 # Source direction for drive offset, rather than outward direction.
 nv=-v if end==0 else v
 drive=m.bridge_drives[name];driveoffset=-off
 q=shift[end,:2]+.05*u+nv*(driveoffset-.475*drive)
 qs=q+np.arange(-2.,3.)[:,None]*u
 print('DECK',name,'end',end,'z',z[end],'probe',qs,flush=True)
 for key,p in {**m.mainline_plans,**m.upper_plans}.items():
  if np.linalg.norm(p.xy[[0,-1]]-shift[end,:2],axis=1).min()>2.5:continue
  d,at,s=ukvertical.project(qs,p.xy);base=np.interp(at,s,p.z)
  for pe,po,edge in ((0,1,at<1e-5),(-1,-2,at>s[-1]-1e-5)):
   dr=p.xy[pe]-p.xy[po];le=np.linalg.norm(dr);dr/=le
   base+=np.where(edge,np.maximum((qs-p.xy[pe])@dr,0.)*(p.z[pe]-p.z[po])/le,0.)
  inter=m.road_interfaces(qs,base,p,m.near(qs,40.))
  print('PLAN',key,'ids',p.end_ids,'base',base,'inter',inter,'actual',m.road_heights(qs,p),'ends',p.z[[0,-1]],'xyend',p.xy[[0,-1]],flush=True)
 print('APPROACH',m.approach_heights(qs,shift,end),flush=True)
md.close();dd.pool.shutdown();dd.urgent_pool.shutdown()
