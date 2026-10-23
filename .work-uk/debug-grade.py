exec(open('tools/validate_uk_round2.py').read().split("if __name__")[0])
name,lat,lon=[('J27',53.0634,-1.2691),('A610',52.99837845,-1.2722428)][int(sys.argv[1])]
net=netfetch.Fetcher(offline=True);cache=str(Path.home()/'.cache/beamng-earth');md=mapdata.MapData(cache,net);d=dem.Dem(cache+'/dem',fetcher=net)
fr=geodesy.EnuFrame(lat-128/111320,lon-128/(111320*math.cos(math.radians(lat))))
raw=lambda la,lo:d.sample(la,lo,15)
gr=grading.Grader(fr,md,raw)
cells=[md.cell(k,layers=('roads',)).layers['roads'] for k in roads.cells_of_tile(fr,0,0)]
rows=[];seen=set()
for f in cells:
 for i,sp in enumerate(roads.road_specs(f)):
  if sp is None or sp.cls not in ('motorway','trunk') or str(f.ids[i]) in seen:continue
  seen.add(str(f.ids[i]))
  for ll in roads.ground_parts(f,i):
   x,y,_=fr.geodetic_to_enu(ll[:,1],ll[:,0],0.);xy=roads.densify(np.c_[x,y],4.)
   near=((xy[:,0]-128)**2+(xy[:,1]-128)**2)<750**2
   if near.sum()<2:continue
   xy=xy[max(0,np.flatnonzero(near)[0]-1):np.flatnonzero(near)[-1]+2]
   la,lo,_=fr.enu_to_geodetic(xy[:,0],xy[:,1],0.);base=raw(la,lo);zz=gr.apply(la,lo,base,.04)
   grades=np.abs(np.diff(zz))/np.maximum(np.linalg.norm(np.diff(xy,axis=0),axis=1),.01)
   k=int(grades.argmax());rows.append((float(grades[k]),str(f.ids[i]),xy,zz,base,k))
for grade,fid,xy,z,base,k in sorted(rows,key=lambda a:-a[0])[:5]:
 print(name,grade,fid,'index',k,'len',len(xy),flush=True)
 sl=slice(max(0,k-3),min(len(xy),k+5));print('xy/z/raw',np.c_[xy,z,base][sl],flush=True)
 if grade>.2:
  for structure in gr.uk_vertical.near(xy):
   ln,top,half,sfid=structure;nodes,edges,adj,ls=gr.uk_vertical.network(structure)
   for be in (0,-1):
    j=int(np.argmin(np.linalg.norm(nodes-ln[be],axis=1)))
    if np.linalg.norm(nodes[j]-ln[be])>.75:continue
    ds=roads._dijkstra(adj,{j:0.})
    for ck,pls in gr.cells.items():
     for pf,p in pls:
      if pf!=fid:continue
      ids=[int(np.argmin(np.linalg.norm(nodes-q,axis=1))) for q in p.xy[[0,-1]]]
      if any(np.linalg.norm(nodes[jj]-q)>.75 for jj,q in zip(ids,p.xy[[0,-1]])):continue
      ss=np.r_[0,np.cumsum(np.linalg.norm(np.diff(p.xy,axis=0),axis=1))];dd=np.minimum(ds[ids[0]]+ss,ds[ids[1]]+ss[-1]-ss)
      if dd.min()<100:print('SEED',sfid,be,'top',top[be],'location',ln[be],'dmin',dd.min(),'slope',(top[-1]-top[-2])/max(np.linalg.norm(ln[-1]-ln[-2]),1e-9),'lastsegment',np.linalg.norm(ln[-1]-ln[-2]),flush=True)
 la,lo,_=fr.enu_to_geodetic(xy[:,0],xy[:,1],0.);plans=gr.plans(la,lo)
 zz=grading.grade_points(xy[:,0],xy[:,1],base,plans,.04)
 print('before priority',zz[sl],flush=True)
 priority=list(gr.uk_vertical.upper_plans.values())
 zz2=grading.grade_points(xy[:,0],xy[:,1],zz,priority,.04)
 print('after priority',zz2[sl],flush=True)
 for f in cells:
  for i in range(len(f)):
   if str(f.ids[i])==fid:print('tags',__import__('roadprofile').tags_for(f,i),flush=True)
 for ck,plans in gr.cells.items():
  for pfid,p in plans:
   dist,at,s=__import__('ukvertical').project(xy[k:k+2],p.xy)
   if dist.min()<5:print('plan',str(ck),pfid,dist,np.interp(at,s,p.z),p.xy[[0,-1]],flush=True)
md.close();d.pool.shutdown()
