import sys,pickle,time,json
import numpy as np
sys.path[:0]=['server'];import roads
from pathlib import Path
original=roads._deck_stacks
for path in sorted(Path('.work-uk').glob('tokyo-solver-*.pkl'))[:1]:
 lines,g,cr,kw=pickle.load(path.open('rb'));lines=[roads.RouteLine(a,i) for a,i in lines];pts=np.concatenate(lines);lookup={tuple(np.round(p,6)):v for p,v in zip(pts,g)}
 def ground(q):
  return np.array([lookup[tuple(np.round(p,6))] if tuple(np.round(p,6)) in lookup else g[np.argmin(np.linalg.norm(pts-p,axis=1))] for p in q])
 for mode in ('normal','crossings_only','central_overlap'):
  if mode=='normal':roads._deck_stacks=original
  elif mode=='crossings_only':roads._deck_stacks=lambda *a,**k:[]
  else:
   def central(lines,levels,widths,*a,**k):
    out=[];ss=[np.r_[0.,np.cumsum(np.linalg.norm(np.diff(l,axis=0),axis=1))] for l in lines]
    for hi,sh,lo,sl in original(lines,levels,widths,*a,**k):
     p=np.array([np.interp(sh,ss[hi],lines[hi][:,j]) for j in (0,1)]);q=np.array([np.interp(sl,ss[lo],lines[lo][:,j]) for j in (0,1)])
     if np.linalg.norm(p-q)<min(widths[hi],widths[lo])*.25:out.append((hi,sh,lo,sl))
    return out
   roads._deck_stacks=central
  start=time.perf_counter();z=roads.deck_profile(lines,ground,cr,**kw);bad=[];_,edges,adj=roads._chain_graph(lines);lv=kw['levels'];widths=kw['widths']
  for i,j,si,sj in roads._deck_crossings(lines):
   if lv[i]==lv[j]:continue
   s,t=edges[i][2],edges[j][2];d=roads._dijkstra(adj,{edges[i][0]:si,edges[i][1]:s[-1]-si})
   reach=max(7.5/.08,2*(widths[i]+widths[j]))
   if min(d[edges[j][0]]+sj,d[edges[j][1]]+t[-1]-sj)<=reach:continue
   gap=(np.interp(si,s,z[i])-np.interp(sj,t,z[j]))*np.sign(lv[i]-lv[j])
   if gap<7.47:bad.append(float(gap))
  print(json.dumps({'file':path.name,'mode':mode,'bad':len(bad),'min_gap':min(bad,default=7.5),'max_height':max(float(v.max()) for v in z),'seconds':time.perf_counter()-start}),flush=True)

