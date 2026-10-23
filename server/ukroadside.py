"""Batched UK motorway furniture: mapped gantries and paired-carriageway medians."""
import numpy as np
import furniture
import ukcontext


def box(p, u, length, width, height, material):
    return {'box3d': [list(map(float,p)),list(map(float,u)),float(length),float(width),float(height)],'m':material}


def _nearest_many(points, line):
    """Project a tile's median samples once per opposing corridor, not per bollard."""
    d=np.diff(line[:,:2],axis=0);l2=np.maximum((d*d).sum(1),1e-9)
    t=np.clip(((points[:,None,:2]-line[None,:-1,:2])*d).sum(2)/l2,0.,1.)
    pp=line[None,:-1,:2]+t[...,None]*d
    dist=np.linalg.norm(pp-points[:,None,:2],axis=2);k=dist.argmin(1);ii=np.arange(len(points))
    q=pp[ii,k]
    if line.shape[1]>2:q=np.c_[q,line[k,2]+t[ii,k]*(line[k+1,2]-line[k,2])]
    return dist[ii,k],q,d[k]/np.sqrt(l2[k,None])


def chunks(frame, roads, bounds, elev):
    import roads as rd
    main=[r for r in roads if r[1].profile is not None and r[1].cls=='motorway' and r[1].oneway
          and not r[1].profile.highway.endswith('_link')]
    # Enriched lane-count splits can retain a centimetre-long reversed seam.
    # It is not a change of travel direction: discard it before pairing and
    # sampling, otherwise its tangent suppresses the reservation at the join.
    main=[(fid,sp,line[np.r_[True,np.linalg.norm(np.diff(line[:,:2],axis=0),axis=1)>.1]],lon)
          for fid,sp,line,lon in main]
    main=[r for r in main if len(r[2])>=2]
    if not main:return []
    out=[]
    records=ukcontext.near(frame,bounds,margin=100.,kinds=('gantry','speed_camera'))
    locations=[]
    for oid,kind,t,ll in sorted(records,key=lambda r:(r[1]!='gantry',r[0])):
        if not len(ll):continue
        la,lo=ll[:,1].mean(),ll[:,0].mean();x,y,_=frame.geodetic_to_enu(la,lo,0.)
        q=np.array([x,y]);hit=ukcontext.match_road(frame,q,main,35.)
        if not hit and kind=='gantry':
            candidates=[ukcontext.match_road(frame,q,[r],35.) for r in main]
            hit=min((h for h in candidates if h),key=lambda h:h[0],default=None)
        if not hit:continue
        dist,fid,sp,p,tangent=hit
        if kind=='speed_camera' and 'red light' in t.get('description','').lower():continue
        # Opposing directions of the same physical gantry, a few metres apart.
        if any(abs((q-old)@tangent)<18. and abs((q-old)[0]*tangent[1]-(q-old)[1]*tangent[0])<75.
               and abs(tangent@ot)>.9 for old,ot in locations):continue
        # Resolve ownership after global deduplication. Cameras on opposite sides
        # of a tile boundary must not each build the same cross-motorway gantry.
        locations.append((q,tangent))
        if not (bounds[0]<=q[0]<bounds[2] and bounds[1]<=q[1]<bounds[3]):continue
        across=np.array([-tangent[1],tangent[0]])
        end0=p[:2]-across*(sp.width/2+1.4);end1=p[:2]+across*(sp.width/2+1.4)
        lane_centres=[p[:2]]
        for ofid,osp,ln,_ in main:
            if ofid==fid:continue
            other=ukcontext.match_road(frame,p[:2],[(ofid,osp,ln,None)],55.)
            if not other:continue
            dd,_,_,op,ot=other
            travel=tangent*(sp.dir or 1);other_travel=ot*(osp.dir or 1)
            if travel@other_travel>-.85 or dd<(sp.profile.drive+osp.profile.drive)/2-.5:continue
            if abs((op[:2]-p[:2])@tangent)>8.:continue
            signed=(op[:2]-p[:2])@across
            if signed>0:end1=op[:2]+across*(osp.width/2+1.4)
            else:end0=op[:2]-across*(osp.width/2+1.4)
            lane_centres.append(op[:2]);break
        if kind=='gantry' and len(ll)>1:
            gx,gy,_=frame.geodetic_to_enu(ll[[0,-1],1],ll[[0,-1],0],0.)
            ends=np.c_[gx,gy]
            if 5.<np.linalg.norm(ends[1]-ends[0])<75.:
                # A mapped line may cover only one carriageway. The signal
                # panels below cover both: retain a beam over every panel.
                projected=(ends-p[:2])@across
                actual=np.array([(end0-p[:2])@across,(end1-p[:2])@across])
                end0=p[:2]+across*min(projected.min(),actual.min())
                end1=p[:2]+across*max(projected.max(),actual.max())
        span=np.linalg.norm(end1-end0);centre=(end0+end1)/2
        la,lo,_=frame.enu_to_geodetic(np.array([end0[0],end1[0]]),np.array([end0[1],end1[1]]),0.)
        z=frame.geodetic_to_enu(la,lo,elev(la,lo))[2]
        top=float(max(z))+6.5
        for q0,z0 in zip((end0,end1),z):out.append(box([*q0,float(z0)],across,.35,.45,top-float(z0)+.55,'uk_metal'))
        out.append(box([*centre,top],across,span,.65,.55,'uk_metal'))
        out.append(box([*centre,top+.75],across,span,.16,.15,'uk_metal'))
        # A ladder-like truss, low triangle count and no projected lights.
        for s in np.arange(-span/2,span/2,3.):
            q0=centre+across*s
            out.append(box([*q0,top+.2],across,.12,.18,.65,'uk_metal'))
        for lc in lane_centres:
            for s in np.linspace(-sp.profile.drive/2+1.8,sp.profile.drive/2-1.8,max(1,sp.profile.forward+sp.profile.backward)):
                q0=lc+across*s
                out.append(box([*q0,top-.75],across,.9,.25,.8,'uk_black'))
        has_camera=kind=='speed_camera'
        if not has_camera:
            for _,rk,_,rg in records:
                if rk=='speed_camera' and len(rg):
                    cx,cy,_=frame.geodetic_to_enu(rg[0,1],rg[0,0],0.)
                    delta=np.array([cx,cy])-centre
                    if abs(delta@tangent)<15. and abs(delta@across)<span/2+3.:has_camera=True;break
        if has_camera:
            q0=p[:2]+across*(sp.width/2-.6)
            out.append(box([*q0,top-.35],across,.6,.5,.5,'uk_yellow'))
    # Central reservation: pair actual opposing motorway corridors, never all one-way roads.
    seen=set()
    for fid,sp,line,_ in main:
        length=furniture._arclen(line)[-1]
        if length<10.:continue
        stations=np.r_[np.arange(0.,length,8.),length]
        points,tangents=furniture._at(line,stations)
        local=(points[:,0]>=bounds[0]-50.)&(points[:,0]<=bounds[2]+50.)&(points[:,1]>=bounds[1]-50.)&(points[:,1]<=bounds[3]+50.)
        points,tangents=points[local],tangents[local]
        if len(points)<2:continue
        best_d=np.full(len(points),np.inf);best_q=np.zeros((len(points),3));best_sp=[None]*len(points);best_ids=[None]*len(points)
        for ofid,osp,other,_ in main:
            if ofid==fid:continue
            lo=points[:,:2].min(0)-45.;hi=points[:,:2].max(0)+45.
            if (other[:,:2].max(0)<lo).any() or (other[:,:2].min(0)>hi).any():continue
            dd,qq,ot=_nearest_many(points,other)
            dot=np.sum(tangents*(sp.dir or 1)*ot*(osp.dir or 1),axis=1)
            gap=dd-(sp.profile.drive+osp.profile.drive)/2
            valid=(dd<best_d)&(dd<=45.)&(dot<=-.9)&(gap>.25)&(gap<16.)
            best_d[valid]=dd[valid];best_q[valid]=qq[valid]
            for j in np.flatnonzero(valid):best_sp[j]=osp;best_ids[j]=ofid
        centres=[]
        for p,t,q,osp,ofid in zip(points,tangents,best_q,best_sp,best_ids):
            if osp is None:centres.append(None);continue
            across=(q[:2]-p[:2]);across/=np.linalg.norm(across)
            normal=np.array([-t[1],t[0]])
            edge0=p[:2]+normal*sp.profile.offset+across*sp.profile.drive/2
            edge1=q[:2]-normal*osp.profile.offset-across*osp.profile.drive/2
            gap=float((edge1-edge0)@across)
            if gap<.2:centres.append(None);continue
            c=(edge0+edge1)/2
            # Own one physical side of the reservation, rather than comparing
            # source IDs. Opposing ways often split at different lane-change
            # positions; ID ownership switches there and leaves short holes.
            axis=int(np.argmax(np.abs(across)))
            centres.append((np.r_[c,(p[2]+q[2])/2-.1],gap,across[axis]>0.))
        for a,b in zip(centres[:-1],centres[1:]):
            if a is None or b is None or not (a[2] or b[2]):continue
            for segment in rd.clip_polyline(np.array([a[0],b[0]]),*bounds):
                p,q=segment[0],segment[-1];delta=q[:2]-p[:2];L=np.linalg.norm(delta)
                if L<.02:continue
                c=(p+q)/2;sig=tuple(np.round(np.r_[p[:2],q[:2]],2))
                if sig in seen:continue
                seen.add(sig)
                ch=box(c,delta/L,L+.015,min(.45,max(.15,min(a[1],b[1])-.1)),.95,'bne_bridge_concrete')
                ch['rise']=float(q[2]-p[2]);out.append(ch)
    return out


def subways(frame, roads, bounds, elev, vertical=None):
    """Visible walls/roof and paved floor of explicitly mapped pedestrian bores."""
    import roads as rd
    out=[]
    for _,_,tags,ll in ukcontext.near(frame,bounds,kinds=('underpass',)):
        if len(ll)<2 or tags.get('tunnel')=='building_passage':continue
        x,y,_=frame.geodetic_to_enu(ll[:,1],ll[:,0],0.)
        centre=np.array([np.mean(x),np.mean(y)])
        if not(bounds[0]<=centre[0]<bounds[2] and bounds[1]<=centre[1]<bounds[3]):continue
        xy=rd.densify(np.c_[x,y],4.)
        la,lo,_=frame.enu_to_geodetic(xy[:,0],xy[:,1],0.)
        floor=None
        if vertical is not None:
            from ukvertical import project
            for line,height,_ in vertical.paths(xy):
                distance,at,s=project(xy,line)
                if distance.max()<.1:floor=np.interp(at,s,height);break
        z=frame.geodetic_to_enu(la,lo,elev(la,lo) if floor is None else floor)[2]
        # The floor follows the same excavated terrain, so collision and drawing agree.
        for a,b,za,zb in zip(xy[:-1],xy[1:],z[:-1],z[1:]):
            d=b-a;L=np.linalg.norm(d)
            if L<.1:continue
            u=d/L;v=np.array([-u[1],u[0]]);p=(a+b)/2;h=float(min(za,zb))
            for side in (-1,1):out.append(box([*(p+v*side*1.65),h],u,L+.05,.3,3.2,'bne_bridge_concrete'))
            out.append(box([*p,h+3.2],u,L+.05,3.6,.4,'bne_bridge_concrete'))
            out.append({'n':[[*a,float(za+.015)],[*b,float(zb+.015)]],'w':3.,'m':'road_asphalt_2lane','tl':10.,'p':1})
    return out
