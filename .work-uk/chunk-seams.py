import sys,json,numpy as np
sys.path[:0]=['server'];import roadmesh
d=json.load(open('.work-uk/boston-joins.json'));cs=[c for c in d['chunks'] if c.get('deck')]
ends={}
for c,r in zip(cs,roadmesh.ribbons(cs)):
 for i in (0,-1):
  k=tuple(np.round(c['n'][i],2));ends.setdefault(k,[]).append((c,r,i))
bad=[]
for k,es in ends.items():
 for a in range(len(es)):
  ca,ra,ia=es[a]
  for cb,rb,ib in es[a+1:]:
   if ca['fid']!=cb['fid']:continue
   gap=min(max(np.linalg.norm(ra[side][ia]-rb[side][ib]) for side in (0,1)),max(np.linalg.norm(ra[side][ia]-rb[1-side][ib]) for side in (0,1)))
   if gap>.03:bad.append({'p':k,'gap':float(gap),'fid':ca['fid']})
print(json.dumps(sorted(bad,key=lambda x:-x['gap'])[:20],default=str,indent=2))
