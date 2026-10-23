exec(open('.work-uk/trace-humps.py').read().split("print('cell'")[0])
q=np.array([[0.,-1.],[0.,0.],[0.,1.],[0.,2.]])
la,lo,_=fr.enu_to_geodetic(q[:,0],q[:,1],0.)
gr.apply(la,lo,raw(la,lo),.04)
m=gr.uk_vertical
for key,p in m.mainline_plans.items():
 if not key[0].startswith(sys.argv[3]):continue
 d,at,s=ukvertical.project(q,p.xy);base=np.interp(at,s,p.z)
 print('PROFILE',key[0],p.end_ids,'end',p.z[[0,-1]].tolist(),'grade',float((abs(np.diff(p.z))/np.diff(s)).max()),'dist',d,'s',at,'len',s[-1],flush=True)
 print('BASE',base,'INTERFACE',m.road_interfaces(q,base,p,m.near(q,40.)),'LATTICE',m.road_heights(q,p),flush=True)
 for line,z,half,name in m.near(q,40.):
  for e in (0,-1):
   dist=np.linalg.norm(p.xy[[0,-1]]-line[e],axis=1)
   if dist.min()<4.:
    width,off=m.pavements.get(name,(half,0.));shift=roads.offset_polyline(np.c_[line,np.zeros(len(line))],off)[:,:2] if off else line
    other=1 if e==0 else -2;u=shift[e]-shift[other];length=np.linalg.norm(u);u/=length
    delta=q-shift[e];station=delta@u;cross=abs(delta[:,0]*u[1]-delta[:,1]*u[0])
    print('BRIDGE',name,'end',e,'dist',dist,'z',z[e],'ids',line.end_ids,'position',line[e],flush=True)
    print('MASK','station',station,'cross',cross,'limits',(-p.half-2.,24.,max(width,p.half)+2.),'off',off,'shift',shift[e],'target',z[e]+(z[e]-z[other])/length*station,flush=True)
    print('ENDS',line[:4],line[-4:],'shift',shift[:4],shift[-4:],'plan',p.xy[-3:],flush=True)
md.close();dd.pool.shutdown()
