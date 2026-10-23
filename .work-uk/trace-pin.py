exec(open('.work-uk/trace-humps.py').read().split("print('cell'")[0])
point=np.zeros(2);model=gr.uk_vertical
for structure in model.near(point[None],450.):
 line,z,half,fid=structure;nodes,edges,adj,lines=model.network(structure)
 if not len(nodes):continue
 node=int(np.argmin(np.linalg.norm(nodes-point,axis=1)))
 if np.linalg.norm(nodes[node]-point)>.75:continue
 for end,other in ((0,1),(-1,-2)):
  sn=int(np.argmin(np.linalg.norm(nodes-line[end],axis=1)))
  if np.linalg.norm(nodes[sn]-line[end])>.75:continue
  d=roads._dijkstra(adj,{sn:0.})[node]
  if d<2:print('ANCHOR',fid,'end',end,'distance',d,'physical',np.linalg.norm(line[end]-point),'height',z[end],'ids',line.end_ids,flush=True)
md.close();dd.pool.shutdown()
