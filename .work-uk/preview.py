import sys,json,math,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,'server')
import mapdata,mapcells,netfetch,geodesy,roads,roadmesh,sidewalks
md=mapdata.MapData('C:/Users/topge/.cache/beamng-earth',netfetch.Fetcher(offline=True))
canvas=Image.new('RGB',(2048,2180),(34,38,42));draw=ImageDraw.Draw(canvas)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',26)
small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',21)
results=[]
sites=[(53.052,-1.299,'Underwood'),(53.0539,-1.394,'Ripley roundabout'),(53.0243,-1.3235,'A610 Langley Mill'),(53.0471,-1.2565,'M1 between J26 and J27')]
for ix,(lat,lon,name) in enumerate(sites):
 start=time.perf_counter()
 fr=geodesy.EnuFrame(lat-128/111320,lon-128/(111320*math.cos(math.radians(lat))))
 keys=roads.cells_of_tile(fr,0,0)
 cells=[md.cell(k,layers=('roads','landcover')).layers for k in keys]
 def urban(la,lo):
  out=np.zeros(np.shape(la),bool)
  for c in cells:out|=c['landcover'].sample(lo,la)==50
  return out
 flat=lambda la,lo:np.full(np.shape(la),25.)
 walks=[]
 chunks=roads.build_tile(fr,0,0,[c['roads'] for c in cells],flat,urban,walks=walks,left_hand=True)
 mesh=roadmesh.build(fr,chunks,flat,(0,0,0))
 b=sidewalks.Builder((0,0,0))
 for w in walks:
  if 'corner' in w:
   c=w['corner'];b.add_corner(c['arc'],c['inward'],c['outer'],h=w.get('h',sidewalks.CURB_H),ramps=c.get('ramps',()))
  else:
   c,o=(w['curb'],w['out']) if 'curb' in w else sidewalks.run_geometry(w['pts'],w['side'],w['w'])
   b.add_run(c,o,w['w'],h=w.get('h',sidewalks.CURB_H),caps=w['caps'],ramps=w.get('ramps',()))
 image=Image.new('RGB',(1000,1000),(99,118,88));d=ImageDraw.Draw(image)
 def render(P,T,M,mats,pavement=False):
  p=np.c_[P[:,0]*1000/256,(256-P[:,1])*1000/256]
  for mi,mat in enumerate(mats):
   color=(178,175,158) if pavement else (242,241,225) if roadmesh.layer_of({'m':mat})=='mark' else (73,79,83)
   for tri in T[M==mi]:
    q=p[tri]
    if (q.max(0)<0).any() or (q.min(0)>1000).any():continue
    d.polygon([tuple(v) for v in q],fill=color)
 render(mesh[0],mesh[1],mesh[4],mesh[3])
 if not b.empty():
  a=b.arrays();render(a[0],a[1],a[3],sidewalks.MATERIALS,True)
 x,y=24+(ix%2)*1024,60+(ix//2)*1060
 canvas.paste(image,(x,y))
 draw.text((x,y-37),name,font=font,fill=(240,240,238))
 draw.rectangle((x+35,y+955,x+35+25*1000/256,y+960),fill='white')
 draw.text((x+35,y+922),'25 m',font=small,fill='white')
 row={'site':name,'road_vertices':len(mesh[0]),'road_triangles':len(mesh[1]),'pavement_runs':len(walks),'pavement_vertices':b.n,'seconds':round(time.perf_counter()-start,3)}
 results.append(row);print(json.dumps(row),flush=True)
draw.text((24,2135),'Generated plan views — geometry checks, not in-game screenshots. Widths without mapped evidence are estimates.',font=small,fill=(225,225,220))
canvas.save('.work-uk/geometry-preview.png')
Path('.work-uk/geometry-preview-results.json').write_text(json.dumps(results,indent=2))
md.close()
