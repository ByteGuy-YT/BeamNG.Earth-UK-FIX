exec(open('.work-uk/trace-humps.py').read().split("print('cell'")[0])
q=np.array([[-80.,-80.],[80.,80.]])
a,b,_=fr.enu_to_geodetic(q[:,0],q[:,1],0.);gr.apply(a,b,raw(a,b),.04)
m=gr.uk_vertical;seen=set()
for kk,p in {**m.mainline_plans,**m.upper_plans}.items():
 if ukvertical.project(np.zeros((1,2)),p.xy)[0][0]>100:continue
 for e in (0,-1):
  if np.linalg.norm(p.xy[e])>120 or p.end_ids[e] in seen:continue
  seen.add(p.end_ids[e]);sp=m.floor_specs[kk];point=p.xy[e]
  print('NODE',p.end_ids[e],'point',point,'plan_end',p.z[e],'raw',m.sample(point[None])[0],'natural_pin',m.endpoint_height(point,p.end_ids[e]),'aligned_pin',m.aligned_endpoint(point,p.end_ids[e]),flush=True)
md.close();dd.pool.shutdown();dd.urgent_pool.shutdown()
