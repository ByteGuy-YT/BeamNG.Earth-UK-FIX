exec(open('.work-uk/trace-humps.py').read().split("print('cell'")[0])
fs=roads.road_specs(f);pick=[]
for i,sp in enumerate(fs):
 if sp and str(f.ids[i]).startswith('ea8017f4'):
  for ll in roads.ground_parts(f,i):
   p=grading.plan_road(fr,ll,sp,raw)
   if len(p.xy)<10:pick.append((str(f.ids[i]),p,sp))
for fid,p,sp in pick:
 print('PLAN',fid,p.xy.tolist(),p.z.tolist(),flush=True)
 s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(p.xy,axis=0),axis=1))]
 for structure in gr.uk_vertical.near(p.xy,100.):
  line,z,half,name=structure;nodes,edges,adj,lines=gr.uk_vertical.network(structure)
  nodez=gr.uk_vertical.ground_nodes(structure)
  ends=p.xy[[0,-1]];idx=[int(np.argmin(np.linalg.norm(nodes-q,axis=1))) for q in ends]
  if any(np.linalg.norm(nodes[j]-q)>.75 for j,q in zip(idx,ends)):continue
  for be in (0,-1):
   at=int(np.argmin(np.linalg.norm(nodes-line[be],axis=1)))
   if np.linalg.norm(nodes[at]-line[be])>.75:continue
   distances=roads._dijkstra(adj,{at:0.});d=np.minimum(distances[idx[0]]+s,distances[idx[1]]+s[-1]-s)
   corr=z[be]-nodez[at];radius=max(100.,abs(corr)*np.pi/(2*.045))
   if d.min()>radius:continue
   print('SEED',name,be,'top',z[be],'nodebase',nodez[at],'delta',corr,'d',d.tolist(),'node_ends',nodez[idx].tolist(),'ids',line.end_ids,flush=True)
   for k,(a,b,_) in enumerate(edges):
    if at in (a,b):
     print(' incident',k,'ends',lines[k][0][[0,-1]].tolist(),'class',lines[k][1].cls,flush=True)
md.close();dd.pool.shutdown()
