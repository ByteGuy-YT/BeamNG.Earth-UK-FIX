"""Original low-poly UK signs, signals and street props; reproducible without Blender."""
import copy
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'server'))
import dae

OUT = ROOT/'mod/beamng_earth/levels/beamng_earth/art/shapes/beamngEarth/uk_street'
VFS = '/levels/beamng_earth/art/shapes/beamngEarth/uk_street/'


class Mesh:
    def __init__(self):
        self.p, self.uv, self.t, self.m = [], [], [], []
    def quad(self, p, mat, uv=((0, 0), (1, 0), (1, 1), (0, 1))):
        n = len(self.p)
        self.p.extend(p); self.uv.extend(uv)
        self.t.extend(((n,n+1,n+2),(n,n+2,n+3))); self.m.extend((mat,mat))
    def box(self, a, b, mat):
        x,y,z=a; X,Y,Z=b
        for q in (((x,y,z),(X,y,z),(X,y,Z),(x,y,Z)),((X,Y,z),(x,Y,z),(x,Y,Z),(X,Y,Z)),
                  ((x,Y,z),(x,y,z),(x,y,Z),(x,Y,Z)),((X,y,z),(X,Y,z),(X,Y,Z),(X,y,Z)),
                  ((x,y,Z),(X,y,Z),(X,Y,Z),(x,Y,Z)),((x,Y,z),(X,Y,z),(X,y,z),(x,y,z))):
            self.quad(q,mat)
    def face(self, z, radius, mat, uvrect=(0,0,1,1), sides=24, y=.06, phase=0.):
        for i in range(sides):
            a,b=phase+2*math.pi*i/sides,phase+2*math.pi*(i+1)/sides
            n=len(self.p); points=[(0,y,z),(radius*math.cos(a),y,z+radius*math.sin(a)),
                                   (radius*math.cos(b),y,z+radius*math.sin(b))]
            self.p.extend(points)
            u,v,U,V=uvrect
            self.uv.extend([(u+(x/radius+1)/2*(U-u), v+(zz-z+radius)/(2*radius)*(V-v)) for x,_,zz in points])
            self.t.append((n,n+2,n+1));self.m.append(mat)
    def save(self,name):
        path=OUT/(name+'.dae'); mats=list(dict.fromkeys(self.m))
        dae.write_grid_dae(str(path),np.array(self.p).ravel(),np.array(self.uv).ravel(),np.array(self.t).ravel(),mats[0])
        ns='http://www.collada.org/2005/11/COLLADASchema'; tag=lambda s:'{'+ns+'}'+s
        ET.register_namespace('',ns); tree=ET.parse(path); root=tree.getroot()
        mesh=root.find('.//'+tag('mesh')); old=mesh.find(tag('triangles'));mesh.remove(old)
        lib=root.find(tag('library_materials'));fx=root.find(tag('library_effects'))
        bind=root.find('.//'+tag('bind_material')+'/'+tag('technique_common'));bind.clear()
        for i,mat in enumerate(mats):
            if i:
                effect=copy.deepcopy(fx[0]);effect.set('id',mat+'-fx');fx.append(effect)
                material=ET.SubElement(lib,tag('material'),id=mat,name=mat)
                ET.SubElement(material,tag('instance_effect'),url='#'+mat+'-fx')
            tri=copy.deepcopy(old);subset=np.array(self.t)[np.array(self.m)==mat]
            tri.set('material','mat'+str(i));tri.set('count',str(len(subset)))
            tri.find(tag('p')).text=dae._indices(subset,2);mesh.append(tri)
            ET.SubElement(bind,tag('instance_material'),symbol='mat'+str(i),target='#'+mat)
        tree.write(path,encoding='utf-8',xml_declaration=True)
        return len(self.t)


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    materials={}
    def mat(name,color=None,texture=None):
        materials[name]={'name':name,'mapTo':name,'class':'Material','version':1.5,'doubleSided':True,
                         'Stages':[{'baseColorFactor':list(color or (1,1,1,1)),'roughnessFactor':.8,
                                    **({'baseColorMap':VFS+texture} if texture else {})},{},{},{}]}
    for n,c in [('uk_metal',(.52,.55,.56,1)),('uk_black',(.025,.028,.03,1)),('uk_white',(.9,.9,.86,1)),
                ('uk_yellow',(.95,.72,.04,1)),('uk_post_red',(.58,.025,.035,1))]:mat(n,c)
    # Instance palette channels select red, amber and green independently through the
    # same instanceColor fields updated by core_trafficSignals.SignalInstance:setLights.
    im=Image.new('RGB',(32,96));pal=Image.new('RGB',(32,96))
    for i,c in enumerate(((235,22,15),(255,155,8),(15,225,65))):
        ImageDraw.Draw(im).rectangle((0,i*32,31,i*32+31),fill=c)
        ImageDraw.Draw(pal).rectangle((0,i*32,31,i*32+31),fill=((255,0,0),(0,255,0),(0,0,255))[i])
    im.save(OUT/'lenses.png');pal.save(OUT/'palette.png')
    mat('uk_signal_lenses',texture='lenses.png')
    materials['uk_signal_lenses']['Stages'][0].update(colorPaletteMap=VFS+'palette.png',instanceDiffuse=True,
        instanceEmissive=True,emissive=True,emissiveFactor=[1,1,1],emissiveIntensityNits=1800)
    m=Mesh();m.box((-.045,-.045,0),(.045,.045,3.65),'uk_metal')
    m.box((-.36,-.09,2.38),(.36,.03,3.72),'uk_white')
    m.box((-.23,.03,2.46),(.23,.13,3.64),'uk_black')
    for i,z in enumerate((3.46,3.05,2.64)):
        m.face(z,.15,'uk_signal_lenses',(0,1-(i+1)/3,1,1-i/3),sides=16,y=.145)
        m.box((-.17,.13,z+.14),(.17,.32,z+.18),'uk_black')
    counts={'signal':m.save('signal')}
    m=Mesh();m.box((-.06,-.06,0),(.06,.06,3.7),'uk_metal');m.box((-.3,-.2,3.2),(.3,.35,3.75),'uk_yellow')
    m.box((-.23,.35,3.29),(.23,.37,3.64),'uk_black');m.face(3.47,.10,'uk_white',sides=12,y=.38)
    counts['camera']=m.save('camera')
    m=Mesh();m.box((-.17,-.17,0),(.17,.17,1.25),'uk_post_red');m.box((-.11,.17,.83),(.11,.185,.9),'uk_black')
    counts['postbox']=m.save('postbox')
    fontpath=next((p for p in (Path('C:/Windows/Fonts/arialbd.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')) if p.exists()),None)
    font=ImageFont.truetype(str(fontpath),54) if fontpath else ImageFont.load_default(size=54)
    for name in ('giveway','stop','nsl','keep_left','roundabout','school','bus_stop'):
        im=Image.new('RGB',(256,256),(130,136,138));d=ImageDraw.Draw(im)
        if name=='giveway':
            d.polygon([(8,16),(248,16),(128,240)],fill=(185,20,28));d.polygon([(44,38),(212,38),(128,198)],fill='white')
        elif name=='stop':
            pts=[(128+120*math.cos(math.pi/8+i*math.pi/4),128+120*math.sin(math.pi/8+i*math.pi/4)) for i in range(8)]
            d.polygon(pts,fill='white');d.polygon([(128+(x-128)*.93,128+(y-128)*.93) for x,y in pts],fill=(180,20,28))
            d.text((128,128),'STOP',font=font,anchor='mm',fill='white')
        elif name=='nsl':
            d.ellipse((5,5,251,251),fill='white');d.line((45,211,211,45),fill=(20,20,20),width=57)
        elif name=='keep_left':
            d.ellipse((5,5,251,251),fill=(20,70,170));d.line((183,62,74,184),fill='white',width=28)
            d.polygon([(57,198),(68,122),(127,181)],fill='white')
        elif name=='roundabout':
            d.polygon([(128,6),(250,244),(6,244)],fill=(185,20,28));d.polygon([(128,43),(217,224),(39,224)],fill='white')
            for j in range(3):
                a,b=j*120+10,j*120+95
                d.arc((86,117,171,202),a,b,fill='black',width=9)
                t=math.radians(b);p=np.array([128.5+42.5*math.cos(t),159.5+42.5*math.sin(t)])
                u=np.array([-math.sin(t),math.cos(t)]);v=np.array([math.cos(t),math.sin(t)])
                d.polygon([tuple(p+u*5),tuple(p-u*12+v*9),tuple(p-u*12-v*9)],fill='black')
        elif name=='school':
            d.polygon([(128,6),(250,244),(6,244)],fill=(185,20,28));d.polygon([(128,43),(217,224),(39,224)],fill='white')
            for x,y,s in ((112,128,1.),(161,151,.75)):
                d.ellipse((x-11*s,y-25*s,x+11*s,y-3*s),fill='black')
                d.line((x,y,x-7*s,y+35*s),fill='black',width=12)
                d.line((x-7*s,y+35*s,x-28*s,y+60*s),fill='black',width=10)
                d.line((x-7*s,y+35*s,x+15*s,y+61*s),fill='black',width=10)
                d.line((x-22*s,y+7*s,x+20*s,y+10*s),fill='black',width=9)
        else:
            d.rectangle((15,5,241,251),fill='white');d.rectangle((27,20,229,165),fill=(40,75,120))
            d.text((128,100),'BUS',font=font,anchor='mm',fill='white')
            d.text((128,209),'STOP',font=font,anchor='mm',fill='black')
        im.save(OUT/(name+'.png'));mat('uk_'+name,texture=name+'.png')
        m=Mesh();m.box((-.03,-.03,0),(.03,.03,2.7),'uk_metal')
        # A thin plate (shape follows its outline rather than a grey square).
        shape=[(-.34,2.78),(.34,2.78),(0,2.14)] if name=='giveway' else \
              [(0,2.85),(-.35,2.16),(.35,2.16)] if name in ('school','roundabout') else None
        if shape:
            m.p.extend([(x,.04,z) for x,z in shape]);m.uv.extend([(x/.7+.5,(z-2.14)/.71) for x,z in shape]);m.t.append((len(m.p)-3,len(m.p)-2,len(m.p)-1));m.m.append('uk_'+name)
        elif name in ('nsl','keep_left'):
            m.face(2.48,.34,'uk_'+name)
        elif name=='stop':
            m.face(2.48,.34,'uk_'+name,sides=8,phase=math.pi/8)
        else:
            m.quad([(-.32,.04,2.13),(.32,.04,2.13),(.32,.04,2.82),(-.32,.04,2.82)],'uk_'+name)
        counts[name]=m.save(name)
    im=Image.new('RGB',(512,256),(128,69,48));d=ImageDraw.Draw(im)
    for y in range(0,256,16):
        d.line((0,y,512,y),fill=(165,135,107),width=2)
        for x in range(-32 if y//16%2 else 0,512,64):d.line((x,y,x,y+16),fill=(165,135,107),width=2)
    for x in (28,190,352):
        d.rectangle((x,30,x+132,194),fill=(220,226,216));d.rectangle((x+7,37,x+125,187),fill=(66,103,120))
        d.line((x+66,34,x+66,190),fill=(220,226,216),width=7);d.line((x+4,89,x+129,89),fill=(220,226,216),width=7)
    im.save(OUT/'school_facade.png');mat('uk_school_facade',texture='school_facade.png')
    im=Image.new('RGB',(512,256),(225,223,213));d=ImageDraw.Draw(im)
    d.rectangle((0,0,511,48),fill=(29,85,62));d.rectangle((0,48,511,57),fill=(230,190,53))
    d.rectangle((18,74,493,233),fill=(56,86,100))
    for x in range(32,500,80):d.line((x,74,x,233),fill=(203,207,199),width=5)
    label=ImageFont.truetype(str(fontpath),36) if fontpath else ImageFont.load_default(size=36)
    d.text((256,25),'PETROL',font=label,anchor='mm',fill='white')
    im.save(OUT/'fuel_facade.png');mat('uk_fuel_facade',texture='fuel_facade.png')
    for key,label in (('supermarket','SUPERMARKET'),('morrisons','Morrisons')):
        im=Image.new('RGB',(1024,256),(191,173,143));d=ImageDraw.Draw(im)
        d.rectangle((0,0,1023,63),fill=(30,78,52));d.rectangle((0,58,1023,65),fill=(224,184,36))
        title=ImageFont.truetype(str(fontpath),45) if fontpath else ImageFont.load_default(size=45)
        d.text((512,28),label,font=title,anchor='mm',fill='white')
        d.rectangle((235,120,789,255),fill=(61,86,93))
        for x in range(235,790,69):d.line((x,120,x,255),fill=(195,200,194),width=4)
        for x in range(0,1024,48):d.line((x,68,x,118),fill=(167,157,140),width=1)
        im.save(OUT/(key+'_facade.png'));mat('uk_'+key+'_facade',texture=key+'_facade.png')
    rng=np.random.default_rng(1904)
    noise=np.clip(87+rng.normal(0,6,(256,256)),62,112).astype(np.uint8)
    Image.fromarray(np.stack([noise,noise,noise],axis=2)).save(OUT/'pavement.png')
    mat('uk_pavement',texture='pavement.png')
    (OUT/'main.materials.json').write_text(json.dumps(materials,indent=2)+'\n')
    (OUT/'asset-budget.json').write_text(json.dumps(counts,indent=2)+'\n')
    print('Asset triangle budgets:',counts)


if __name__=='__main__':build()
