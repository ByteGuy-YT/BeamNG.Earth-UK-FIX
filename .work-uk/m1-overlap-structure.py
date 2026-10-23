exec(open('.work-uk/trace-humps.py').read().split("print('cell'")[0])
m=gr.uk_vertical
for xy,z,half,fid in m.near(np.array([[0.,0.]]),100.):
 if fid.startswith(('f0e6','db8a','e2b3','90eb')):
  print(fid,m.highways.get(fid),'half',half,'ends',xy[[0,-1]].tolist(),'z',z[[0,-1]].tolist(),'len',np.linalg.norm(np.diff(xy,axis=0),axis=1).sum(),'ids',xy.end_ids,flush=True)
md.close();dd.pool.shutdown()
