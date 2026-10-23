import sys,runpy,pickle,numpy as np
from pathlib import Path
sys.path[:0]=['server'];import roads
orig=roads.deck_profile;number=0
def record(lines,ground,crossings=(),**kw):
 global number
 if len(lines)>60:
  xy=np.concatenate([np.asarray(l)[:,:2] for l in lines]);g=ground(xy)
  path=Path('.work-uk')/f'tokyo-solver-{number}.pkl';number+=1
  with path.open('wb') as f:pickle.dump(([(np.asarray(l),getattr(l,'end_ids',(None,None))) for l in lines],g,crossings,kw),f)
 return orig(lines,ground,crossings,**kw)
roads.deck_profile=record
sys.argv=['validate_world_geometry.py','--water','--case','tokyo','--out','.work-uk/tokyo-captured.json']
runpy.run_path('tools/validate_world_geometry.py',run_name='__main__')
