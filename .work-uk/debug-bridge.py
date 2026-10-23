exec(open('.work-uk/vertical.py').read().replace('md.close();d.pool.shutdown()', ''))
for fid,sp,xy,z,_ in parts:
 if sp.cls!='motorway': continue
 print('\nBRIDGE',fid)
 for p in xy[[0,-1]]:
  la,lo,_=fr.enu_to_geodetic(p[0],p[1],0.)
  print('END',p,'raw',raw(la,lo),'graded',elev(la,lo),'lift',(gr._end_lift(p) or [None])[0])
  near=[]
  for k,plans in gr.cells.items():
   for name,pl in plans:
    dist=min(np.linalg.norm(pl.xy[0]-p),np.linalg.norm(pl.xy[-1]-p))
    if dist<4: near.append((name,round(float(dist),3),pl.z[0],pl.z[-1],pl.half))
  print('plans',near)
md.close();d.pool.shutdown()

