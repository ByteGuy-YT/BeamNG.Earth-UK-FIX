import sys,runpy,numpy as np
sys.path[:0]=['server'];import roads
orig=roads.deck_profile
def check(lines,ground,crossings=(),**kw):
 z=orig(lines,ground,crossings,**kw);lv=kw.get('levels');ww=kw.get('widths');_,edges,adj=roads._chain_graph(lines)
 for cr in crossings:
  i,at,h=cr[:3];ss=edges[i][2]
  if len(cr)==3 and min(at,ss[-1]-at)>12 and np.interp(at,ss,z[i])-h<7.47:print('BADGROUND',i,'gap',np.interp(at,ss,z[i])-h,'range',float(min(v.min() for v in z)),float(max(v.max() for v in z)),flush=True)
 if lv is not None:
  for i,j,si,sj in roads._deck_crossings(lines):
   if lv[i]==lv[j]:continue
   a,b,s=edges[i];c,d,t=edges[j];reach=max(40.,2*(ww[i]+ww[j])) if ww is not None else 60.
   path=min((di+dj for ni,di in ((a,si),(b,s[-1]-si)) for nj,dj in ((c,sj),(d,t[-1]-sj)) if ni==nj),default=1e9)
   gap=(np.interp(si,s,z[i])-np.interp(sj,t,z[j]))*np.sign(lv[i]-lv[j])
   if path>reach and gap<7.47:
    dd=roads._dijkstra(adj,{a:si,b:s[-1]-si}); print('NETWORK',min(dd[c]+sj,dd[d]+t[-1]-sj),'END_IDS',getattr(lines[i],'end_ids',None),getattr(lines[j],'end_ids',None),flush=True); print('BAD',i,j,'gap',gap,'direct graph path',path,'reach',reach,'widths',ww[i],ww[j], 'levels',lv[i],lv[j],flush=True)
 return z
roads.deck_profile=check
sys.argv=['validate_world_geometry.py','--offline','--water','--case','tokyo','--out','.work-uk/tokyo-debug-result.json']
runpy.run_path('tools/validate_world_geometry.py',run_name='__main__')


