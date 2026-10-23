"""Audit complete surface/bridge transitions and approaches, not only deck meshes.

Coordinates select test data only; production code has no geographic overrides.
"""
import sys,json,time,argparse,traceback
from pathlib import Path
import numpy as np
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'server')]
import mapdata,mapcells,dem,netfetch,geodesy,roads,grading,roadprofile,terrain_surface,ukvertical,roadmesh
CASES=[('a610',52.99815,-1.27167,'A610',1400),('m1_j26',53.002,-1.232,'M1',2000),
 ('m1_j27_28',53.089,-1.305,'M1',2400),('m25',51.713,-.242,'M25',2000),
 ('m6_birmingham',52.518,-1.866,'M6',2000),('m6_cumbria',54.629,-2.757,'M6',2000),
 ('m62',53.612,-2.059,'M62',2000),('m4',51.427,-.987,'M4',2000),
 ('m5',51.521,-2.631,'M5',2000),('m8',55.865,-4.276,'M8',2000),
 ('a1',54.971,-1.678,'A1',2000),('a9',56.44,-3.463,'A9',2000),
 ('a55',53.279,-3.772,'A55',2000),('a38',50.7,-3.521,'A38',2000),
 ('a303',51.175,-1.828,'A303',2000),('a14',52.27,.06,'A14',2000)]
ONLY_IDS=[]

def audit(case,cache,offline):
 name,lat,lon,ref,radius=case;start=time.monotonic()
 net=netfetch.Fetcher(offline=offline);md=mapdata.MapData(cache,net);dd=dem.Dem(cache+'/dem',fetcher=net)
 fr=geodesy.EnuFrame(lat,lon);raw=lambda a,b:dd.sample(a,b,15)
 gr=grading.Grader(fr,md,raw);elev=lambda a,b:gr.apply(a,b,raw(a,b),.04)
 margin=radius/111320.;pl=margin/np.cos(np.radians(lat));fs=[];seen=set();parts=[];bridges=[]
 try:
  for key in mapcells.cells_for_bbox(lat-margin,lon-pl,lat+margin,lon+pl):
   f=md.cell(key,layers=('roads',)).layers['roads'];fs.append(f)
   rs,bs=roads.road_specs(f),roads.bridge_specs(f)
   for i,(sp,bsp) in enumerate(zip(rs,bs)):
    tags=roadprofile.tags_for(f,i);fid=str(f.ids[i])
    if fid in seen or ref not in str(tags.get('ref','')).split(';'):continue
    seen.add(fid)
    if sp is not None:
     for ll in roads.ground_parts(f,i):
      p=grading.plan_road(fr,ll,sp,raw)
      if np.linalg.norm(p.xy,axis=1).min()<radius:parts.append((fid,sp,p))
    if bsp is not None:
     for ll in roads.bridge_parts(f,i):
      x,y,_=fr.geodetic_to_enu(ll[:,1],ll[:,0],0.)
      if np.linalg.norm(np.c_[x,y],axis=1).min()<radius:bridges.append(fid);break
  if not parts and not bridges:raise AssertionError('No mapped target route loaded')
  # Build all solutions before measuring the ground, just as the loaded mesh does.
  solved=gr.bridge_model.parts(fs,(-radius,-radius,radius,radius))
  level_lines=[v[2] for v in solved];levels=[gr.uk_vertical.levels.get(v[0].split('#')[0],0) for v in solved]
  widths=[v[1].width for v in solved]
  clearances=[]
  arcs=[np.r_[0.,np.cumsum(np.linalg.norm(np.diff(ln,axis=0),axis=1))] for ln in level_lines]
  for hi,sh,lo,sl in roads.deck_clearance_constraints(level_lines,levels,widths,roads.DECK_ROAD_CLEAR):
   clearances.append(float(np.interp(sh,arcs[hi],solved[hi][3])-np.interp(sl,arcs[lo],solved[lo][3])-roads.DECK_ROAD_CLEAR))
  model_errors=[]
  for fid,sp,xy,z,_ in solved:
   if not sp.profile:continue
   target=gr.uk_vertical.deck(fid,xy)
   if target is None:model_errors.append(float('inf'));continue
   aa,bb,_=fr.enu_to_geodetic(xy[:,0],xy[:,1],0.)
   expected=fr.geodetic_to_enu(aa,bb,target+.04)[2]
   model_errors.append(float(abs(z-expected).max()))
  decks=[(fid,sp,roads.offset_polyline(np.c_[xy,z],sp.profile.surface_offset) if sp.profile and sp.profile.surface_offset else np.c_[xy,z])
         for fid,sp,xy,z,_ in solved if fid.split('#')[0] in bridges]
  # Generate the same colliding interfaces as the road tile builder. Measure
  # the final driveable surface, retaining failures elsewhere in the approach.
  patches=[]
  for fid,sp,line in decks:
   for end in (0,-1):
    touches=min((np.linalg.norm(p.xy[[0,-1]]-line[end,:2],axis=1).min() for _,_,p in parts),default=np.inf)<4.
    if touches:
     patch=roadmesh.bridge_join(fr,line,sp.width,end,elev,(-np.inf,-np.inf,np.inf,np.inf),vertical=gr.uk_vertical if sp.profile else None)
     if patch:patch['fid']=fid;patches.append(patch)
  # A surface road can join the middle/edge of another bridge. Its terrain
  # beneath that slab is intentionally excavated; the slab is the collision
  # road there. Omitting it reports a fictitious drop in a continuous route.
  slab_chunks=roads._deck_chunks([(fid,sp,np.c_[xy,z],lon) for fid,sp,xy,z,lon in solved],(-radius-100,-radius-100,radius+100,radius+100),vertical=gr.uk_vertical)
  refs=[c for c in slab_chunks if c.get('deck') and c.get('deck_priority')==2]
  for ch,ribbon in zip([c for c in slab_chunks if c.get('deck') and not c.get('ctx')],roadmesh.ribbons([c for c in slab_chunks if c.get('deck') and not c.get('ctx')])):
   left,right,_,_,_,z=ribbon;n=len(z);pp=np.c_[np.r_[left,right],np.r_[z,z]];ix=np.arange(n-1)
   tt=np.r_[np.c_[ix,ix+n,ix+n+1],np.c_[ix,ix+n+1,ix+1]]
   if ch.get('deck_priority')==1:
    pp,tt,_=roadmesh.subtract_footprints(pp,tt,np.zeros((len(pp),2)),roadmesh.deck_exclusions(ch,refs))
   if ch.get('ground_exclusions'):
    pp,tt,_=roadmesh.subtract_footprints(pp,tt,np.zeros((len(pp),2)),ch['ground_exclusions'])
   if not len(tt):continue
   patches.append({'join_mesh':[pp,tt,None],'fid':ch['fid'],'slab':True})
  def driveable(xy,trace=None,owner=None,approach=None):
   z=terrain_surface.heights(fr,elev,xy)
   # Surface-road collision meshes use this same common triangulated field.
   # Restrict it to the physical pavement; its two-metre sampling guard band
   # is not itself a road. Bridge joins/slabs are intersected below.
   surface=gr.uk_vertical
   if owner is not None:z=np.maximum(z,surface.road_heights(xy,owner))
   elif approach is not None:z=np.maximum(z,surface.approach_heights(xy,*approach))
   if trace is not None:trace.append({'layer':'terrain_and_surface','z':z.tolist()})
   aa,bb,_=fr.enu_to_geodetic(xy[:,0],xy[:,1],0.)
   expected=z.copy()
   for patch in patches:
    pp,tt,_=patch['join_mesh'];pp=np.asarray(pp);tt=np.asarray(tt)
    ids=np.flatnonzero(((xy>=pp[:,:2].min(0)-1e-7)&(xy<=pp[:,:2].max(0)+1e-7)).all(1))
    if not len(ids):continue
    a=pp[tt[:,0]];b=pp[tt[:,1]]-a;c=pp[tt[:,2]]-a
    den=b[:,0]*c[:,1]-b[:,1]*c[:,0]
    good=abs(den)>1e-10;a=a[good];b=b[good];c=c[good];den=den[good]
    for k in ids:
     d=xy[k]-a[:,:2]
     u=(d[:,0]*c[:,1]-d[:,1]*c[:,0])/den;v=(b[:,0]*d[:,1]-b[:,1]*d[:,0])/den
     hit=(u>=-1e-7)&(v>=-1e-7)&(u+v<=1.0000001)
     heights=(a[:,2]+u*b[:,2]+v*c[:,2])[hit]
     if patch.get('slab'):heights=heights[heights<=expected[k]+.25]
     if len(heights):
      top=float(heights.max())
      if trace is not None and top>z[k]+.001:trace.append({'layer':patch['fid'],'slab':patch.get('slab',False),'at':int(k),'z':top})
      z[k]=max(z[k],top)
   return z
  # Ground at the exact two-metre physics lattice, including its interpolation.
  joints=[]
  for fid,sp,line in decks:
   for end in (0,-1):
    direction=line[end,:2]-line[1 if end==0 else -2,:2];direction/=np.linalg.norm(direction)
    normal=np.array([-direction[1],direction[0]])
    lane_half=(sp.profile.drive if sp.profile else sp.width)/2
    offsets=np.array([-.95*lane_half,0.,.95*lane_half])
    drive_normal=-normal if end==0 else normal
    centre=line[end,:2]+drive_normal*(sp.profile.offset if sp.profile else 0.)
    q=centre+.05*direction+offsets[:,None]*drive_normal
    trace=[];z=driveable(q,trace,approach=(line,end))
    # End must touch a ground part; a deck-to-deck source split is measured elsewhere.
    touches=min((np.linalg.norm(p.xy[[0,-1]]-line[end,:2],axis=1).min() for _,_,p in parts),default=np.inf)<4.
    if not touches:continue
    gap=z-line[end,2];a,b,_=fr.enu_to_geodetic(*line[end,:2],0.)
    joints.append({'id':fid,'end':end,'lat':float(a),'lon':float(b),'deck':float(line[end,2]),'ground_minus_deck':gap.tolist(),'layers':trace})
  sections=[]
  for fid,sp,p in parts:
   if ONLY_IDS and not any(fid.startswith(prefix) for prefix in ONLY_IDS):continue
   xy,s=grading.resample(p.xy,2.);keep=np.linalg.norm(xy,axis=1)<radius
   # Exclude the very edge covered by a bridge, but retain every approach.
   la,lo,_=fr.enu_to_geodetic(xy[:,0],xy[:,1],0.)
   tangent=np.gradient(xy,axis=0);tangent/=np.maximum(np.linalg.norm(tangent,axis=1),1e-9)[:,None]
   normal=np.c_[-tangent[:,1],tangent[:,0]]
   drive=sp.profile.drive if sp.profile else sp.width
   centre=xy+normal*(sp.profile.offset if sp.profile else 0.)
   edge=.475*drive
   probes=np.r_[centre,centre-normal*edge,centre+normal*edge]
   # Warm source plans before selecting this physical road's independent floor.
   elev(la,lo);owner=gr.uk_vertical.floor_plan(fid,p.xy)
   zz=driveable(probes,owner=owner).reshape(3,len(xy));grade=abs(np.diff(zz,axis=1))/np.maximum(np.diff(s),1e-8)[None,:];active=keep[:-1]&keep[1:]
   if not active.any():continue
   lane,k=np.unravel_index(np.argmax(np.where(active[None,:],grade,-1)),grade.shape);z=zz[lane]
   direct=fr.geodetic_to_enu(la[k:k+2],lo[k:k+2],elev(la[k:k+2],lo[k:k+2]))[2]
   ground=terrain_surface.heights(fr,elev,xy[k:k+2])
   layers=[];driveable(probes.reshape(3,len(xy),2)[lane,k:k+2],trace=layers,owner=owner)
   cross=abs(zz[2]-zz[1])/max(2*edge,.1)
   sections.append({'id':fid,'highway':sp.profile.highway if sp.profile else sp.cls,'length':float(s[-1]),'sampled_m':int(keep.sum())*2,'max_grade':float(grade[lane,k]),'probe':int(lane),'max_crossfall':float(cross[keep].max()),'lat':float(la[k]),'lon':float(lo[k]),'z_pair':z[k:k+2].tolist(),'direct_pair':direct.tolist(),'terrain_pair':ground.tolist(),'layers':layers})
  max_gap=max((max(abs(np.array(j['ground_minus_deck']))) for j in joints),default=0.)
  max_grade=max((s['max_grade'] for s in sections),default=0.)
  max_crossfall=max((s['max_crossfall'] for s in sections),default=0.)
  return {'name':name,'ref':ref,'ok':bool(max_gap<.03 and max_grade<(.085 if ref.startswith('M') else .15) and max_crossfall<.1 and max(model_errors,default=0)<.001 and min(clearances,default=0)>-.03),
          'metres':sum(s['sampled_m'] for s in sections),'bridges':len(decks),'max_joint_gap':float(max_gap),'max_grade':float(max_grade),
          'stacked_clearances':len(clearances),'min_clearance_margin':min(clearances,default=0.),
          'max_crossfall':max_crossfall,
          'max_solver_disagreement':max(model_errors,default=0.),
          'joints':joints,'sections':sections,'seconds':time.monotonic()-start}
 finally:md.close();dd.pool.shutdown()

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--case',action='append',default=[])
 ap.add_argument('--offline',action='store_true');ap.add_argument('--out',default='docs/road-corridor-validation.json')
 ap.add_argument('--section-id',action='append',default=[],help='Diagnostic subset only; not a complete corridor check')
 ap.add_argument('--cache',default=str(Path.home()/'.cache/beamng-earth'));args=ap.parse_args();rows=[];ONLY_IDS=args.section_id
 for case in CASES:
  if args.case and case[0] not in args.case:continue
  try:row=audit(case,args.cache,args.offline)
  except Exception as ex:row={'name':case[0],'ok':False,'error':str(ex),'trace':traceback.format_exc()}
  rows.append(row);Path(args.out).write_text(json.dumps(rows,indent=2)+'\n')
  print(json.dumps({k:v for k,v in row.items() if k not in ('joints','sections','trace')}),flush=True)
 raise SystemExit(not(rows and all(r['ok'] for r in rows)))
