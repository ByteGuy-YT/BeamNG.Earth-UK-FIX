"""Offline integration audit using cached real roads and DEM, never flat bridge terrain.

Run from the project root. Reports generated-model measurements, not survey truth or FPS.
"""
import json,math,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
import buildings,dem,geodesy,grading,mapcells,mapdata,navgraph,netfetch,parking,roadmesh,roads,ukcontext


def run(online=False):
    cache=str(Path.home()/'.cache/beamng-earth')
    net=netfetch.Fetcher(offline=not online);md=mapdata.MapData(cache,net);d=dem.Dem(cache+'/dem',fetcher=net)
    out=[]
    sites=[('J26 Nottingham Road',52.9994,-1.2311),('M1 Kennel Lane',53.0471,-1.2565),
           ('J27',53.0634,-1.2691),('A610 path subway',52.99837845,-1.2722428),
           ('M1 camera gantry',53.02053995,-1.24495915),('Eastwood Morrisons',53.01913249,-1.3110272)]
    try:
        for name,lat,lon in sites:
            fr=geodesy.EnuFrame(lat-128/111320,lon-128/(111320*math.cos(math.radians(lat))))
            raw=lambda la,lo:d.sample(la,lo,15)
            gr=grading.Grader(fr,md,raw)
            elev=lambda la,lo:gr.apply(la,lo,raw(la,lo),grading.ROAD_LIFT)
            cells=[md.cell(k,layers=('roads',)).layers['roads'] for k in roads.cells_of_tile(fr,0,0)]
            bp=roads.BridgeProfiles(fr,lambda k:md.cell(k,layers=('roads',)).layers['roads'],elev);bp.vertical=gr.uk_vertical
            t=time.perf_counter();parts=bp.parts(cells,(-500,-500,750,750));bridges=[]
            for fid,sp,xy,z,_ in parts:
                s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
                if len(xy)<2:continue
                la,lo,_=fr.enu_to_geodetic(xy[[0,-1],0],xy[[0,-1],1],0.)
                ground=fr.geodetic_to_enu(la,lo,elev(la,lo))[2]
                row={'id':fid,'class':sp.cls,'length_m':round(float(s[-1]),2),
                     'maximum_grade':round(float(np.max(np.abs(np.diff(z))/np.maximum(np.diff(s),.001))),4),
                     'endpoint_difference_m':np.round(z[[0,-1]]-ground,3).tolist()}
                keep=(s>=5)&(s<=s[-1]-5)
                if keep.any() and sp.profile is not None:
                    dx=np.gradient(xy[:,0]);dy=np.gradient(xy[:,1]);ln=np.maximum(np.hypot(dx,dy),1e-6)
                    n=np.c_[-dy/ln,dx/ln]
                    qs=np.concatenate([xy[keep]+n[keep]*side for side in np.linspace(-sp.width/2,sp.width/2,7)])
                    la,lo,_=fr.enu_to_geodetic(qs[:,0],qs[:,1],0.)
                    gz=fr.geodetic_to_enu(la,lo,elev(la,lo))[2]
                    dz=np.tile(z[keep],7)-gz
                    row['minimum_surface_to_terrain_m']=round(float(dz.min()),3)
                bridges.append(row)
            walks=[];props=[];lines=[];park=[];ctx=[]
            tile_t=[]
            for repeat in range(3):
                tt=time.perf_counter();chunks=roads.build_tile(fr,0,0,cells,elev,walks=walks if repeat==0 else [],
                    props=props if repeat==0 else [],lines=lines if repeat==0 else [],park=park if repeat==0 else [],
                    bridges=bp,deck_context=ctx if repeat==0 else [],left_hand=True)
                tile_t.append(round((time.perf_counter()-tt)*1000,2))
            mesh=roadmesh.build(fr,chunks,elev,(0,0,0));assert mesh is None or np.isfinite(mesh[0]).all()
            decks={}
            for fid,sp,xy,z,_ in parts:decks.setdefault(fid,[]).append((xy,z))
            graph=navgraph.build(fr,cells,elev,(128,128),decks=decks,left_hand=True)
            matched_ring=set()
            for f in cells:
                for i,sp in enumerate(roads.road_specs(f)):
                    if sp and sp.profile and sp.profile.junction=='roundabout':matched_ring.add(str(f.ids[i]))
            rings=[e for e in graph['edges'] if any(fid in str(n) for fid in matched_ring for n in e[:2])]
            record={'site':name,'seconds':round(time.perf_counter()-t,2),'tile_ms':tile_t,'bridges':bridges,
                    'mesh_triangles':0 if mesh is None else len(mesh[1]),
                    'roadside_solids':sum(bool(c.get('box3d')) for c in chunks),
                    'cameras':[{k:c[k] for k in ('id','limit','width','motorway')} for c in graph['cameras']],
                    'roundabout_edges_sampled':len(rings),
                    'roundabout_reverse_lanes':sum(e[4]>0 or e[2]!=1 for e in rings)}
            grades=[];link_grades=[];seen=set()
            for f in cells:
                for i,sp in enumerate(roads.road_specs(f)):
                    if sp is None or sp.cls not in ('motorway','trunk') or str(f.ids[i]) in seen:continue
                    seen.add(str(f.ids[i]))
                    for ll in roads.ground_parts(f,i):
                        x,y,_=fr.geodetic_to_enu(ll[:,1],ll[:,0],0.)
                        xy=roads.densify(np.c_[x,y],4.)
                        near=((xy[:,0]-128)**2+(xy[:,1]-128)**2)<750**2
                        if near.sum()<2:continue
                        xy=xy[max(0,np.flatnonzero(near)[0]-1):np.flatnonzero(near)[-1]+2]
                        la,lo,_=fr.enu_to_geodetic(xy[:,0],xy[:,1],0.);zz=elev(la,lo)
                        value=float(np.max(np.abs(np.diff(zz))/np.maximum(np.linalg.norm(np.diff(xy,axis=0),axis=1),.01)))
                        is_link=__import__('roadprofile').tags_for(f,i).get('highway','').endswith('_link')
                        (link_grades if is_link else grades).append(value)
            record['maximum_nearby_major_ground_road_grade']=round(max(grades),4) if grades else None
            record['maximum_nearby_slip_road_grade']=round(max(link_grades),4) if link_grades else None
            assert all(max(abs(x) for x in b['endpoint_difference_m'])<.12 for b in bridges),(name,'deck join',bridges)
            assert all(b.get('minimum_surface_to_terrain_m',1.)>0 for b in bridges),(name,'terrain intrusion')
            assert not grades or max(grades)<.10,(name,'main-road spike',max(grades))
            assert not link_grades or max(link_grades)<.15,(name,'slip-road spike',max(link_grades))
            if name=='A610 path subway':
                record['mapped_subways']=len(ukcontext.near(fr,(0,0,256,256),kinds=('underpass',)))
                record['synthetic_short_decks']=sum('~osm' not in b['id'] for b in bridges)
            if name=='Eastwood Morrisons':
                items=buildings.road_tile_items(fr,0,0,md,raw)
                ukcontext.decorate_buildings(fr,(0,0,256,256),items)
                before=[(s.ring.copy(),s.height) for s,*_ in items]
                bld=buildings.road_tile(fr,0,0,md,raw,items=items)
                for (s,*_),old in zip(items,before):assert np.array_equal(s.ring,old[0]) and s.height==old[1]
                record['morrisons_buildings']=sum(s.uk_brand=='morrisons' for s,*_ in items)
                park=parking.tile_lot_spots(fr,0,0,md,elev,items,park)
                painted=parking.render_lots(None,fr,(0,0,256,256),md,elev,(0,0,0),park,lines,[s.ring for s,*_ in items])
                record['parking_surface_materials']=painted[3] if painted else []
                record['parking_bay_candidates']=len(park)
            print(json.dumps(record),flush=True);out.append(record)
            (ROOT/'docs/uk-round2-validation.json').write_text(json.dumps(out,indent=2)+'\n')
    finally:
        md.close();d.pool.shutdown()
    target=ROOT/'docs/uk-round2-validation.json';target.write_text(json.dumps(out,indent=2)+'\n')
    return out


if __name__=='__main__':run('--online' in sys.argv)
