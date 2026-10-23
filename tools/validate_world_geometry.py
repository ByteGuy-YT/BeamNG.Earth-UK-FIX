#!/usr/bin/env python3
"""Real-data geometry audit; coordinates select tests, never production overrides."""
import sys,json,time,traceback,argparse,tempfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
import mapdata,netfetch,geodesy,roads,grading,dem,roadmesh,ukvertical,cdae
CASES=[('london',51.4927,-.1204),('giltbrook',53.0017,-1.283),('j26',52.9994,-1.231),('boston_zakim',42.3685,-71.063),('boston_i93',42.2105,-71.0),('stelvio',46.528,10.455),('sydney',-33.8523,151.2108),('tokyo',35.663,139.77),('cape_town',-33.917,18.429)]
ap=argparse.ArgumentParser(description='Build and inspect real road/bridge geometry across world regression sites.')
ap.add_argument('--case',action='append',default=[])
ap.add_argument('--cache',default=str(Path.home()/'.cache/beamng-earth'))
ap.add_argument('--offline',action='store_true')
ap.add_argument('--water',action='store_true',help='Use production water-bed carving and water clearance requirements')
ap.add_argument('--out',default=str(ROOT/'docs/world-geometry-validation.json'))
args=ap.parse_args();selected=args.case;rows=[]
clearance_samples=[]
_deck_profile=roads.deck_profile
def checked_deck_profile(lines,ground,crossings=(),**kw):
 z=_deck_profile(lines,ground,crossings,**kw)
 _,edges,adj=roads._chain_graph(lines)
 arcs=[edge[2] for edge in edges]
 clear=kw.get('clear') or roads.DECK_ROAD_CLEAR
 for cr in crossings:
  i,s,h=cr[:3]
  if len(cr)==3 and min(s,arcs[i][-1]-s)>roads.AT_GRADE_REACH_M and np.isfinite(z[i]).all():
   clearance_samples.append(float(np.interp(s,arcs[i],z[i]))-h-clear)
 levels=kw.get('levels');widths=kw.get('widths')
 if levels is not None:
  for i,j,si,sj in roads._deck_crossings(lines):
   if levels[i]==levels[j] or not (np.isfinite(z[i]).all() and np.isfinite(z[j]).all()):continue
   reach=max(clear/min(roads.DECK_MAX_GRADE,.08),2*(widths[i]+widths[j]) if widths is not None else 60.)
   distance=roads._dijkstra(adj,{edges[i][0]:si,edges[i][1]:arcs[i][-1]-si})
   if min(distance[edges[j][0]]+sj,distance[edges[j][1]]+arcs[j][-1]-sj)<=reach:continue
   gap=(float(np.interp(si,arcs[i],z[i]))-float(np.interp(sj,arcs[j],z[j])))*np.sign(levels[i]-levels[j])
   clearance_samples.append(gap-clear)
 return z
roads.deck_profile=checked_deck_profile
for name,lat,lon in CASES:
 if selected and name not in selected:continue
 start=time.perf_counter();md=None;dd=None;clearance_samples.clear()
 try:
  net=netfetch.Fetcher(offline=args.offline);cache=args.cache;md=mapdata.MapData(cache,net);dd=dem.Dem(cache+'/dem',fetcher=net);fr=geodesy.EnuFrame(lat,lon)
  raw=lambda la,lo:dd.sample(la,lo,15)
  if args.water:
   import seacarve
   sea=seacarve.SeaCarver(md,cache,dem=dd)
   structure_raw=lambda la,lo:sea.carve(la,lo,raw(la,lo))
  else:sea=None;structure_raw=raw
  gr=grading.Grader(fr,md,raw,structure_elev=structure_raw)
  elev=lambda la,lo:gr.apply(la,lo,structure_raw(la,lo),.04)
  bp=gr.bridge_model;bp.vertical=gr.uk_vertical
  if sea is not None:bp.wet=sea.depth
  stats=[];all_decks=[];tp=gr.tunnel_model
  for tx,ty in ((0,0),(-1,0),(0,-1),(1,0)):
   fs=[md.cell(k,layers=('roads',)).layers.get('roads') for k in roads.cells_of_tile(fr,tx,ty)]
   walks=[];walls=[];ctx=[];chunks=roads.build_tile(fr,tx,ty,fs,elev,walks=walks,bridges=bp,tunnels=tp,walls=walls,deck_context=ctx)
   origin=(tx*256,ty*256,0.);rm=roadmesh.build(fr,chunks,elev,origin,vertical=bp.vertical,deck_context=ctx);dm=roadmesh.deck(chunks,origin,context=ctx);tm=roadmesh.tunnel(chunks,origin,walls)
   meshes=[m for m in (rm,dm,tm) if m is not None]
   all_decks.extend(c for c in chunks if c.get('deck') and not c.get('tunnel'))
   objects=0;max_vertices=0
   with tempfile.TemporaryDirectory() as tmp:
    for j,m in enumerate(meshes):
     path=str(Path(tmp)/f'mesh{j}.cdae');roadmesh.write(path,m);decoded=cdae.read(path)
     objects+=len(decoded['meshes']);max_vertices=max(max_vertices,max(mm['verts'][0] for mm in decoded['meshes']))
     assert all(mm['verts'][0]<=60000 for mm in decoded['meshes'])
     assert sum(mm['indices'][0] for mm in decoded['meshes'])==3*len(m[1])
   assert all(np.isfinite(m[0]).all() and m[1].max()<len(m[0]) for m in meshes)
   errors=[]
   canonical={}
   for fid,sp,xy,z,_ in bp.parts(fs,roads.tile_bbox(tx,ty)):
    ln=np.c_[xy,z]
    if sp.profile is not None and sp.profile.surface_offset:ln=roads.offset_polyline(ln,sp.profile.surface_offset)
    canonical.setdefault(fid,[]).append(ln)
   for c in chunks:
    if not c.get('deck') or c.get('tunnel') or c.get('fid') not in canonical:continue
    pp=np.asarray(c['n']);xy,s,z=roadmesh._resample(pp,2.)
    matches=[]
    for ln in canonical[c['fid']]:
     dist,at,ss=ukvertical.project(xy,ln[:,:2]);matches.append((float(dist.max()),abs(z-np.interp(at,ss,ln[:,2]))))
    errors.extend(min(matches,key=lambda row:row[0])[1])
   stats.append({'tile':[tx,ty],'chunks':len(chunks),'walls':len(walls),'road_vertices':len(rm[0]) if rm else 0,'deck_vertices':len(dm[0]) if dm else 0,'deck_max_profile_error':float(max(errors,default=0.)),'engine_meshes':objects,'max_engine_vertices':max_vertices})
  assert sum(t['chunks'] for t in stats)>0,'No road geometry at this test location'
  assert max(t['deck_max_profile_error'] for t in stats)<.03,'Deck differs from shared source profile'
  # A valid mesh can still meet another valid mesh at a seven-metre wall.
  # Audit physical connectivity independently of per-part profile fidelity.
  parts=[v for v in bp.done.values() if np.isfinite(v[2]).all()]
  nodes,edges,_=roads._chain_graph([v[1] for v in parts]);node_z={}
  for v,(a,b,_) in zip(parts,edges):
   for node,at in ((a,0),(b,-1)):node_z.setdefault(node,[]).append(float(v[2][at]))
  joins=[max(z)-min(z) for z in node_z.values() if len(z)>1]
  assert max(joins,default=0.)<.03,f'Connected deck endpoints disagree by {max(joins):.3f} m'
  seam_ends={};seams=[]
  for c,r in zip(all_decks,roadmesh.ribbons(all_decks)):
   for at in (0,-1):
    p=np.asarray(c['n'][at]);on_edge=np.any(np.abs(p[:2]/256-np.round(p[:2]/256))<1e-6)
    if on_edge:seam_ends.setdefault((c['fid'],*np.round(p[:2],3)),[]).append((r,at))
  for ends in seam_ends.values():
   for j,(a,ia) in enumerate(ends):
    for b,ib in ends[j+1:]:
     gap=min(max(np.linalg.norm(a[s][ia]-b[s][ib]) for s in (0,1)),max(np.linalg.norm(a[s][ia]-b[1-s][ib]) for s in (0,1)))
     seams.append(max(float(gap),abs(float(a[5][ia]-b[5][ib]))))
  assert max(seams,default=0.)<.03,f'Adjacent deck tile edges disagree by {max(seams):.3f} m'
  grades=[float(np.max(abs(np.diff(v[2]))/np.maximum(np.linalg.norm(np.diff(v[1][:,:2],axis=0),axis=1),1e-9))) for v in parts]
  if max(grades,default=0.)>=.081:
   faults=[]
   for key,v in bp.done.items():
    sp,xy,z,_=v
    ds=np.linalg.norm(np.diff(xy[:,:2],axis=0),axis=1);gg=abs(np.diff(z))/np.maximum(ds,1e-9)
    if not len(gg) or not np.isfinite(gg).any():continue
    at=int(np.nanargmax(gg))
    if gg[at]>=.081:faults.append({'id':str(key),'class':sp.cls,'highway':sp.profile.highway if sp.profile else None,'grade':float(gg[at]),'span_m':float(ds[at]),'z_pair':z[at:at+2].tolist(),'xy_pair':np.asarray(xy[at:at+2]).tolist()})
   print(json.dumps({'diagnostic':name,'deck_grade_faults':faults}),file=sys.stderr,flush=True)
  assert max(grades,default=0.)<.081,f'Near-vertical deck slope: {max(grades):.3f}'
  assert min(clearance_samples,default=0.)>-.03,f'Bridge clearance deficit: {-min(clearance_samples):.3f} m'
  tunnel_parts=[v for v in tp.done.values() if np.isfinite(v[2]).all()]
  tn,te,_=roads._chain_graph([v[1] for v in tunnel_parts]);tz={}
  for v,(a,b,_) in zip(tunnel_parts,te):
   for node,at in ((a,0),(b,-1)):tz.setdefault(node,[]).append(float(v[2][at]))
  tunnel_joins=[max(z)-min(z) for z in tz.values() if len(z)>1]
  assert max(tunnel_joins,default=0.)<.03,f'Connected tunnel floors disagree by {max(tunnel_joins):.3f} m'
  covered=sum(np.linalg.norm(np.diff(xy,axis=0),axis=1).sum() for _,_,xy,_,_ in tp.parts(fs,(-768,-768,768,768)))
  row={'name':name,'lat':lat,'lon':lon,'ok':True,'tiles':stats,'connected_junctions':len(joins),'max_junction_step':max(joins,default=0.),'checked_seams':len(seams),'max_seam_gap':max(seams,default=0.),'max_deck_grade':max(grades,default=0.),'checked_road_clearances':len(clearance_samples),'min_clearance_margin':min(clearance_samples,default=0.),'tunnel_parts':len(tunnel_parts),'max_tunnel_join_step':max(tunnel_joins,default=0.),'covered_tunnel_m':float(covered),'seconds':time.perf_counter()-start}
 except Exception as ex:
  row={'name':name,'ok':False,'error':str(ex),'trace':traceback.format_exc(),'seconds':time.perf_counter()-start}
 finally:
  if md:md.close()
  if dd:dd.pool.shutdown()
 rows.append(row);print(json.dumps(row),flush=True)
 Path(args.out).write_text(json.dumps(rows,indent=2)+'\n')
raise SystemExit(0 if rows and all(r['ok'] for r in rows) else 1)

