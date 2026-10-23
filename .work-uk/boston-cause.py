import sys,numpy as np
sys.path[:0]=['server']
import roads
oldcross=roads._deck_crossings;oldstacks=roads._deck_stacks
def joined(lines,i,j,si,sj,reach=120):
 for ei in (0,-1):
  for ej in (0,-1):
   if np.linalg.norm(lines[i][ei,:2]-lines[j][ej,:2])>.5:continue
   li=np.linalg.norm(np.diff(lines[i][:,:2],axis=0),axis=1).sum()
   lj=np.linalg.norm(np.diff(lines[j][:,:2],axis=0),axis=1).sum()
   if (si if ei==0 else li-si)+(sj if ej==0 else lj-sj)<reach:return True
 return False
def cross(lines):return [c for c in oldcross(lines) if not joined(lines,*c)]
def stacks(lines,levels,widths,step=16):
 return [c for c in oldstacks(lines,levels,widths,step) if not joined(lines,c[0],c[2],c[1],c[3])]
roads._deck_crossings=cross;roads._deck_stacks=stacks
exec(open('.work-uk/boston-joins.py').read())
