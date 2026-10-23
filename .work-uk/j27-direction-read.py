import sys,json,numpy as np
sys.path.insert(0,'server')
import mapdata,netfetch,roads,geodesy,navgraph,roadprofile
md=mapdata.MapData('C:/Users/topge/.cache/beamng-earth',netfetch.Fetcher(offline=True));fr=geodesy.EnuFrame(53.0634,-1.2691)
fs=[md.cell(k,layers=('roads',)).layers['roads'] for k in roads.cells_of_tile(fr,0,0)]
g=navgraph.build(fr,fs,lambda la,lo:np.zeros(np.shape(la)),(0,0),left_hand=True)
ids=set();pts=[];lines=[];fids=[]
for f in fs:
 for i,sp in enumerate(roads.road_specs(f)):
  if sp and sp.profile and sp.profile.junction in ('roundabout','circular'):
   fid=str(f.ids[i])
   if fid in ids:continue
   ids.add(fid);ll=f.parts(i)[0][0];x,y,_=fr.geodetic_to_enu(ll[:,1],ll[:,0],0.);pts.extend(np.c_[x,y]);lines.append(np.c_[x,y]);fids.append(fid)
nodes,edges,adj=roads._chain_graph(lines)
todo=set(range(len(nodes)))
while todo:
 seed=todo.pop();component={seed};stack=[seed]
 while stack:
  n=stack.pop()
  for nb,_ in adj[n]:
   if nb in todo:todo.remove(nb);component.add(nb);stack.append(nb)
 own={fid for fid,(a,b,_) in zip(fids,edges) if a in component}
 pp=np.concatenate([ln for fid,ln in zip(fids,lines) if fid in own]);centre=(pp.min(0)+pp.max(0))/2
 clockwise=anticlockwise=0
 for e in g['edges']:
  if any(fid in n for fid in own for n in e[:2]):
   a,b=[np.array(g['nodes'][n][:2]) for n in e[:2]];q=(a+b)/2-centre;v=b-a;cross=float(q[0]*v[1]-q[1]*v[0])
   clockwise+=cross<0;anticlockwise+=cross>0
 print('COMPONENT',centre,'ways',len(own),'clockwise',clockwise,'anticlockwise',anticlockwise)
centre=(np.min(pts,axis=0)+np.max(pts,axis=0))/2
ring=[]
for e in g['edges']:
 if any(fid in n for fid in ids for n in e[:2]):
  a,b=[np.array(g['nodes'][n][:2]) for n in e[:2]]
  q=(a+b)/2-centre;v=b-a;ring.append(float(q[0]*v[1]-q[1]*v[0]))
print('centre',centre,'clockwise',sum(v<0 for v in ring),'anticlockwise',sum(v>0 for v in ring))
print('signals',len(g['signals']))
for j in g['signals']:
 for a in j['app']:
  p=np.array(a[7:9]);inc=np.array(a[4:6]);q=p-centre;print('signal',j['j'],a[0],p,inc,a[10],'signed',q[0]*inc[1]-q[1]*inc[0])
md.close()
