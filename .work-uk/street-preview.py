from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import xml.etree.ElementTree as ET
import numpy as np,json
root=Path('mod/beamng_earth/levels/beamng_earth/art/shapes/beamngEarth/uk_street')
out=Image.new('RGB',(1200,820),(37,43,47));d=ImageDraw.Draw(out)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',25)
d.text((25,16),'UK street assets — geometry / texture preview',font=font,fill='white')
ns={'c':'http://www.collada.org/2005/11/COLLADASchema'}
colors={'uk_metal':(139,148,152),'uk_white':(226,226,217),'uk_black':(22,24,26),'uk_yellow':(239,187,24),'uk_post_red':(166,19,31),'uk_signal_lenses':(175,80,35)}
for name,cx in [('signal',170),('camera',420),('postbox',650)]:
 tree=ET.parse(root/(name+'.dae'));a=tree.find('.//c:float_array',ns);p=np.fromstring(a.text,sep=' ').reshape(-1,3)
 # An orthographic view from the front-right; model dimensions remain in metres.
 px=p[:,0]*.88-p[:,1]*.48;depth=p[:,0]*.48+p[:,1]*.88
 xy=np.c_[cx+px*90,415-p[:,2]*90+depth*20]
 bindings={v.get('symbol'):v.get('target')[1:] for v in tree.findall('.//c:instance_material',ns)}
 faces=[]
 for tri in tree.findall('.//c:triangles',ns):
  t=np.fromstring(tri.find('c:p',ns).text,sep=' ',dtype=int).reshape(-1,6)[:,::2]
  mat=bindings[tri.get('material')]
  for q in t:faces.append((depth[q].mean(),q,mat))
 for _,q,mat in sorted(faces,key=lambda x:x[0]):
  c=colors.get(mat,(180,180,180))
  if mat=='uk_signal_lenses':
   z=p[q,2].mean();c=(239,34,24) if z>3.25 else (230,151,20) if z>2.85 else (27,170,70)
  d.polygon([tuple(v) for v in xy[q]],fill=c)
 d.text((cx-65,435),name,font=font,fill='white')
for i,name in enumerate(('giveway','stop','nsl','keep_left','roundabout','school','bus_stop')):
 im=Image.open(root/(name+'.png')).resize((130,130))
 x=24+i*167;out.paste(im,(x,490));d.text((x,630),name,font=font,fill='white')
for x,name,label in [(775,'school_facade','School facade'),(775,'fuel_facade','Petrol facade')]:
 y=70 if name=='school_facade' else 250
 im=Image.open(root/(name+'.png')).resize((400,150));out.paste(im,(x,y));d.text((x,y+152),label,font=font,fill='white')
d.text((24,740),'Original assets; stock petrol pumps are loaded from the installed game.',font=font,fill=(205,213,215))
d.text((24,778),'Model/texture review only. In-game lighting and rendering still need checking.',font=font,fill=(205,213,215))
out.save('docs/uk-street-assets-preview.png')
