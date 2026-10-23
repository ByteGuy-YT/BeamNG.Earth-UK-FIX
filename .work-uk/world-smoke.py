import sys,json,time,traceback
from pathlib import Path
import numpy as np
sys.path[:0]=['server']
import mapdata,netfetch,geodesy,roads,grading,dem,roadmesh,ukvertical
CASES=[('london',51.4927,-.1204),('giltbrook',53.0017,-1.283),('j26',53.0025,-1.245),('boston_zakim',42.3685,-71.063),('boston_i93',42.2105,-71.0),('stelvio',46.528,10.455),('sydney',-33.8523,151.2108),('tokyo',35.663,139.77),('cape_town',-33.917,18.429)]
selected=sys.argv[1:];rows=[]
for name,lat,lon in CASES:
 if selected and name not in selected:continue
 start=time.perf_counter();md=None;dd=None
 try:
  net=netfetch.Fetcher();cache='C:/Users/topge/.cache/beamng-earth';md=mapdata.MapData(cache,net);dd=dem.Dem(cache+'/dem',fetcher=net);fr=geodesy.EnuFrame(lat,lon)
  raw=lambda la,lo:dd.sample(la,lo,15)
  gr=grading.Grader(fr,md,raw)
  elev=lambda la,lo:gr.apply(la,lo,raw(la,lo),.04)
  bp=roads.BridgeProfiles(fr,lambda k:md.cell(k,layers=('roads',)).layers.get('roads'),elev);bp.vertical=gr.uk_vertical
  stats=[]
  for tx,ty in ((0,0),(-1,0),(0,-1),(1,0)):
   fs=[md.cell(k,layers=('roads',)).layers.get('roads') for k in roads.cells_of_tile(fr,tx,ty)]
   walks=[];walls=[];ctx=[];chunks=roads.build_tile(fr,tx,ty,fs,elev,walks=walks,bridges=bp,walls=walls,deck_context=ctx)
   origin=(tx*256,ty*256,0.);rm=roadmesh.build(fr,chunks,elev,origin);dm=roadmesh.deck(chunks,origin,context=ctx);tm=roadmesh.tunnel(chunks,origin,walls)
   meshes=[m for m in (rm,dm,tm) if m is not None]
   assert all(np.isfinite(m[0]).all() and m[1].max()<len(m[0]) for m in meshes)
   errors=[]
   canonical={fid:(sp,np.c_[xy,z]) for fid,sp,xy,z,_ in bp.parts(fs,roads.tile_bbox(tx,ty))}
   for c in chunks:
    if not c.get('deck') or c.get('tunnel') or c.get('fid') not in canonical:continue
    sp,ln=canonical[c['fid']]
    if sp.profile is not None and sp.profile.surface_offset:ln=roads.offset_polyline(ln,sp.profile.surface_offset)
    pp=np.asarray(c['n']);xy,s,z=roadmesh._resample(pp,2.)
    dist,at,ss=ukvertical.project(xy,ln[:,:2]);errors.extend(abs(z-np.interp(at,ss,ln[:,2])))
   stats.append({'tile':[tx,ty],'chunks':len(chunks),'walls':len(walls),'road_vertices':len(rm[0]) if rm else 0,'deck_vertices':len(dm[0]) if dm else 0,'deck_max_profile_error':float(max(errors,default=0.))})
  row={'name':name,'lat':lat,'lon':lon,'ok':True,'tiles':stats,'seconds':time.perf_counter()-start}
 except Exception as ex:
  row={'name':name,'ok':False,'error':str(ex),'trace':traceback.format_exc(),'seconds':time.perf_counter()-start}
 finally:
  if md:md.close()
  if dd:dd.pool.shutdown()
 rows.append(row);print(json.dumps(row),flush=True)
 Path('.work-uk/world-smoke-'+('-'.join(selected) if selected else 'all')+'.json').write_text(json.dumps(rows,indent=2))

