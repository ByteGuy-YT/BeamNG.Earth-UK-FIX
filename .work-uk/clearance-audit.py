import sys,runpy,json
import numpy as np
sys.path[:0]=['server'];import roads
orig=roads.deck_profile;rows=[]
def audit(lines,ground,crossings=(),**kw):
 z=orig(lines,ground,crossings,**kw)
 arcs=[np.r_[0.,np.cumsum(np.linalg.norm(np.diff(l[:,:2],axis=0),axis=1))] for l in lines]
 nodes,edges,_=roads._chain_graph(lines)
 for cr in crossings:
  i,s,h=cr[:3]
  if min(s,arcs[i][-1]-s)<40:continue
  required=cr[3] if len(cr)>3 and cr[3] is not None else roads.DECK_ROAD_CLEAR
  got=float(np.interp(s,arcs[i],z[i]))-h
  if got<required-.25:rows.append({'kind':'water' if len(cr)>3 else 'ground','required':required,'gap':got,'at':np.array([np.interp(s,arcs[i],lines[i][:,j]) for j in (0,1)]).tolist()})
 lv=kw.get('levels')
 if lv:
  for i,j,si,sj in roads._deck_crossings(lines):
   if lv[i]==lv[j]:continue
   reach=60.
   joined=any(ni==nj and di+dj<=reach for ni,di in ((edges[i][0],si),(edges[i][1],arcs[i][-1]-si)) for nj,dj in ((edges[j][0],sj),(edges[j][1],arcs[j][-1]-sj)))
   if joined:continue
   a=float(np.interp(si,arcs[i],z[i]));b=float(np.interp(sj,arcs[j],z[j]));gap=(a-b)*np.sign(lv[i]-lv[j])
   if gap<roads.DECK_ROAD_CLEAR-.25:rows.append({'kind':'stack','required':roads.DECK_ROAD_CLEAR,'gap':gap,'at':[float(np.interp(si,arcs[i],lines[i][:,q])) for q in (0,1)]})
 return z
roads.deck_profile=audit
sys.argv=['validate_world_geometry.py','--offline','--water','--case','boston_zakim','--out','.work-uk/clearance-world.json']
try:runpy.run_path('tools/validate_world_geometry.py',run_name='__main__')
except SystemExit:pass
rows.sort(key=lambda r:r['gap']-r['required']);print(json.dumps(rows[:35],indent=2));print('failed requirements',len(rows))
open('.work-uk/clearance-deficits.json','w').write(json.dumps(rows,indent=2))
