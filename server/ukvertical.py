"""Separate upper road profiles from terrain at mapped UK grade separations.

The DEM is one surface, not two floors. Sampling its trench into an upper road and
then adding clearance created motorway humps. This model samples the approach
trend outside a short structure. Motorway/trunk mainlines keep their own grade;
secondary overbridges rise to clear them. Other lower roads may be excavated.
No site coordinates or surveyed-height claims. Long viaducts retain the legacy solver.
"""
import math
import heapq
import threading
import numpy as np
import mapcells


def end_grade(line, z, end, run=8.):
    """A deck's approach grade over metres, not a tiny source connector.

    Clearance and joining constraints can change a submillimetre connector by
    micrometres. Extrapolating that numerical slope over an approach creates
    a real hump. Keep the endpoint height and use the nearby deck trend.
    """
    xy=np.asarray(line,float)[:,:2]
    if end!=0:xy=xy[::-1];z=np.asarray(z)[::-1]
    arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
    distance=min(float(run),float(arc[-1]))
    if distance<1e-4:return 0.
    return float((z[0]-np.interp(distance,arc,z))/distance)


def grade_bounds(top, grade, distance):
    """Reach a deck smoothly while changing the surrounding land minimally."""
    distance=np.asarray(distance,float)
    run=-8.*np.expm1(-distance/8.)
    centre=top+grade*run
    allowance=.05*(distance-run)
    return centre-allowance,centre+allowance


def ground_endpoint_envelope(lines, heights, limits, anchors=()):
    """Remove endpoint DEM peaks through actual road connections.

    Smoothing each short source section independently leaves a portal pixel
    several metres above the continuing road. A min-plus graph envelope bounds
    the grade between its shared endpoints without raising the surrounding
    junctions into another hump. Overlapping roads with distinct identities
    remain independent.
    """
    import roads
    nodes,edges,_=roads._chain_graph(lines)
    values=[[] for _ in nodes];adj=[[] for _ in nodes]
    for (a,b,s),z,limit in zip(edges,heights,limits):
        values[a].append(float(z[0]));values[b].append(float(z[-1]))
        if np.isfinite(limit):
            cost=float(s[-1])*limit
            adj[a].append((b,cost));adj[b].append((a,cost))
    z=np.array([np.median(v) for v in values]);identities={}
    for line,(a,b,_) in zip(lines,edges):
        for node,identity in zip((a,b),getattr(line,'end_ids',(None,None))):
            if identity is not None:identities.setdefault(identity,set()).add(node)
    trusted={}
    for point,identity,height in anchors:
        for node in identities.get(identity,()) if identity is not None else range(len(nodes)):
            if np.linalg.norm(np.asarray(nodes[node])-point)<.75:trusted.setdefault(node,[]).append(height)
    # A DEM trench at an actual abutment is not a low road from which to
    # propagate an excavation. The independent approach trend recovers it.
    for node,values in trusted.items():z[node]=np.median(values)
    queue=[(h,i) for i,h in enumerate(z)]
    heapq.heapify(queue)
    while queue:
        height,i=heapq.heappop(queue)
        if height>z[i]+1e-10:continue
        for j,cost in adj[i]:
            h=height+cost
            if h<z[j]-1e-10:z[j]=h;heapq.heappush(queue,(h,j))
    return np.asarray(nodes),edges,z


def underpass_ranges(ll, tags):
    """An explicitly mapped subway crossing needs a deck in the upper road."""
    if tags.get('highway','').removesuffix('_link') not in ('motorway','trunk','primary','secondary','tertiary'):
        return []
    import ukcontext
    import roads
    pad=.0001
    records=ukcontext.features((ll[:,0].min()-pad,ll[:,1].min()-pad,ll[:,0].max()+pad,ll[:,1].max()+pad),('underpass',))
    scale=np.array([111320.*np.cos(np.radians(ll[:,1].mean())),111320.])
    xy=(ll-ll[0])*scale
    length=np.linalg.norm(np.diff(xy,axis=0),axis=1).sum()
    if length<1.:return []
    out=[]
    for _,_,t,geom in records:
        path=(geom-ll[0])*scale
        if len(path)<2:continue
        for _,at,q in roads._crossings([xy],[path]):
            # The full path corridor plus concrete abutments, clipped to this source section.
            half=5.
            out.append((max(0.,(at-half)/length),min(1.,(at+half)/length),'bridge'))
    merged=[]
    for a,b,k in sorted(out):
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]),k)
        else:merged.append((a,b,k))
    return merged


def approach_profile(xy, sample):
    """Robust local grade across a short span, using both approaches, not its trench."""
    xy = np.asarray(xy, float)[:, :2]
    s = np.r_[0., np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    if s[-1] < 1.:
        return np.asarray(sample(xy), float)
    u, v = xy[1]-xy[0], xy[-1]-xy[-2]
    u /= max(np.linalg.norm(u), 1e-9); v /= max(np.linalg.norm(v), 1e-9)
    d = np.array([20., 40., 70.])
    q = np.r_[xy[0]-d[:, None]*u, xy[-1]+d[:, None]*v]
    z = np.asarray(sample(q), float)
    # Median pairwise grades tolerate a bad DEM sample on either verge/approach.
    st = np.r_[-d, s[-1]+d]
    slopes = [(z[j]-z[i])/(st[j]-st[i]) for i in range(6) for j in range(i+1,6) if abs(st[j]-st[i])>5]
    slope = float(np.clip(np.median(slopes), -.08, .08))
    intercept = float(np.median(z-slope*st))
    return intercept+slope*s


def project(q, xy, reach=None):
    if reach is not None and len(q)>128 and len(xy)>16:
        # Terrain grids need only the road corridor, not every point against
        # every segment of a kilometre-long source way. Keep the original arc
        # stations while culling by small spatial buckets.
        d=np.diff(xy[:,:2],axis=0);length=np.maximum(np.linalg.norm(d,axis=1),1e-6)
        s=np.r_[0.,np.cumsum(length)];lo=np.minimum(xy[:-1,:2],xy[1:,:2]);hi=np.maximum(xy[:-1,:2],xy[1:,:2])
        distance=np.full(len(q),np.inf);at=np.zeros(len(q))
        cells,inverse=np.unique(np.floor(q/32).astype(np.int64),axis=0,return_inverse=True)
        for j,cell in enumerate(cells):
            ids=np.flatnonzero(inverse==j);low=cell*32-reach;high=(cell+1)*32+reach
            seg=np.flatnonzero((hi>=low).all(1)&(lo<=high).all(1))
            if not len(seg):continue
            delta=q[ids,None,:]-xy[None,seg,:2];v=d[seg];l2=np.maximum((v*v).sum(1),1e-12)
            t=np.clip((delta*v).sum(2)/l2,0.,1.);dist=np.linalg.norm(delta-t[...,None]*v,axis=2);k=dist.argmin(1)
            distance[ids]=dist[np.arange(len(ids)),k];at[ids]=s[seg[k]]+t[np.arange(len(ids)),k]*length[seg[k]]
        return distance,at,s
    d = np.diff(xy[:, :2], axis=0); l2 = np.maximum((d*d).sum(1), 1e-12)
    t = np.clip(((q[:, None, :]-xy[None, :-1, :2])*d).sum(2)/l2, 0., 1.)
    delta = q[:, None, :]-xy[None, :-1, :2]-t[..., None]*d
    dist = np.linalg.norm(delta, axis=2); k = dist.argmin(1)
    s = np.r_[0., np.cumsum(np.sqrt(l2))]
    at = s[k]+t[np.arange(len(q)), k]*np.sqrt(l2[k])
    return dist[np.arange(len(q)), k], at, s


def approach_ownership(xy, plans, priority):
    """Upper approaches own their corridor, never a lower road beside/beneath it.

    Reapplying a truncated approach's lateral fill ramp over a motorway created
    a small bump at its far end. Compare centreline distances to the complete
    ground network before applying the priority pass, with a 1 m soft boundary.
    """
    def distances(rows, ids, initial):
        out=initial.copy()
        if not len(ids) or not rows:return out
        qlo=xy[ids].min(0);qhi=xy[ids].max(0)
        segments=[];reach=max(p.half for p in rows)+1.
        for p in rows:
            if p.bbox[2]<qlo[0] or p.bbox[0]>qhi[0] or p.bbox[3]<qlo[1] or p.bbox[1]>qhi[1]:continue
            a,b=p.xy[:-1],p.xy[1:]
            keep=(np.maximum(a,b)>=qlo-reach).all(1)&(np.minimum(a,b)<=qhi+reach).all(1)
            if keep.any():segments.append(np.c_[a[keep],b[keep]])
        if not segments:return out
        seg=np.concatenate(segments);a,b=seg[:,:2],seg[:,2:]
        low=np.minimum(a,b);high=np.maximum(a,b)
        buckets=np.floor(xy[ids]/32.).astype(np.int64)
        unique,inverse=np.unique(buckets,axis=0,return_inverse=True)
        for j,cell in enumerate(unique):
            k=ids[inverse==j];lo=cell*32.-reach;hi=(cell+1)*32.+reach
            keep=(high>=lo).all(1)&(low<=hi).all(1)
            if not keep.any():continue
            aa=a[keep];d=b[keep]-aa;l2=np.maximum((d*d).sum(1),1e-12)
            for start in range(0,len(k),256):
                kk=k[start:start+256];delta=xy[kk,None,:]-aa
                t=np.clip((delta*d).sum(2)/l2,0.,1.)
                out[kk]=np.linalg.norm(delta-t[...,None]*d,axis=2).min(1)
        return out
    ids=np.arange(len(xy));empty=np.full(len(xy),np.inf)
    dp=distances(priority,ids,empty)
    active=np.flatnonzero(np.isfinite(dp))
    dn=distances(plans,active,empty)
    weight=np.zeros(len(xy));weight[active]=np.clip(1.-(dp[active]-dn[active]),0.,1.)
    # Centreline distance alone assigns a motorway's outside lane to a narrow
    # path running beside/under it. The real pavement footprint owns its own
    # height; no ownership is extended past a source part's end into its bore.
    weight[core_mask(xy,priority)]=1.
    return weight


def core_mask(xy, plans, heights=False):
    protected=np.zeros(len(xy),bool)
    numerator=np.zeros(len(xy));denominator=np.zeros(len(xy))
    strict_num=np.zeros(len(xy));strict_den=np.zeros(len(xy))
    for plan in plans:
        lo=np.array(plan.bbox[:2]);hi=np.array(plan.bbox[2:])
        ids=np.flatnonzero(((xy>=lo)&(xy<=hi)).all(1))
        if not len(ids):continue
        distance,at,s=project(xy[ids],plan.xy,reach=plan.half)
        u=plan.xy[1]-plan.xy[0];v=plan.xy[-1]-plan.xy[-2]
        before=((xy[ids]-plan.xy[0])*u).sum(1)<-1e-6
        after=((xy[ids]-plan.xy[-1])*v).sum(1)>1e-6
        within=(~((at<1e-5)&before&~np.asarray(plan.caps[0])))&(~((at>s[-1]-1e-5)&after&~np.asarray(plan.caps[1])))
        interior=(~((at<1e-5)&before))&(~((at>s[-1]-1e-5)&after))
        valid=(distance<=plan.half)&within
        protected[ids]|=valid
        if heights:
            weight=1/(1+(distance[valid]/4.)**2)
            numerator[ids[valid]]+=weight*np.interp(at[valid],s,plan.z)
            denominator[ids[valid]]+=weight
            strict=valid&interior
            sw=1/(1+(distance[strict]/4.)**2)
            strict_num[ids[strict]]+=sw*np.interp(at[strict],s,plan.z)
            strict_den[ids[strict]]+=sw
    if heights:
        strict=strict_den>0
        numerator[strict]=strict_num[strict];denominator[strict]=strict_den[strict]
        target=np.zeros(len(xy));target[protected]=numerator[protected]/denominator[protected]
        return protected,target
    return protected


class Model:
    def __init__(self, frame, md, raw):
        self.frame, self.md, self.raw = frame, md, raw
        self.cache, self.lock = {}, threading.RLock()
        self.path_cache={}
        self.upper_plans={}
        self.highways={}
        self.bridge_drives={}
        self.floor_specs={}
        self.levels={}
        self.near_cache={}
        self.network_cache={}
        self.network_graphs={}
        self.network_bounds={}
        self.cut_cache={}
        self.graph_cache={}
        self.mainline_plans={}
        self.mainline_profiles={}
        self.solutions={}
        self.node_profiles={}
        self.natural_ends={}
        self.natural_roads={}
        self.endpoint_graphs={}
        self.end_heights={}
        self.aligned_ends={}
        self.seed_distances={}
        self.pavements={}
        self.plan_specs={}

    def sample(self, xy):
        la, lo, _ = self.frame.enu_to_geodetic(xy[:,0], xy[:,1], 0.)
        return np.asarray(self.raw(la, lo), float)

    def cell(self, key):
        import roads
        with self.lock:
            if key in self.cache:
                return self.cache[key]
            f = self.md.cell(key, layers=('roads',), kind='demand').layers.get('roads')
            out = []
            if f is not None:
                for i, sp in enumerate(roads.bridge_specs(f)):
                    if sp is None or sp.profile is None:
                        continue
                    try:level=float(__import__('roadprofile').tags_for(f,i).get('layer','1') or 1.)
                    except (TypeError,ValueError):level=1.
                    self.levels[str(f.ids[i])]=level
                    self.highways[str(f.ids[i])]=sp.profile.highway
                    self.bridge_drives[str(f.ids[i])]=sp.profile.drive
                    self.pavements[str(f.ids[i])]=(sp.width/2,sp.profile.surface_offset)
                    for ring in roads.bridge_parts(f, i):
                        la, lo = ring[:,1], ring[:,0]
                        x,y,_ = self.frame.geodetic_to_enu(la, lo, 0.)
                        # Preserve source corners exactly, as BridgeProfiles
                        # does. A uniform four-metre resample cut across sharp
                        # ramp bends, failed the .75 m route match and silently
                        # selected a different solver for the entire chain.
                        xy=roads.densify(np.c_[x,y],2.)
                        xy=roads.RouteLine(xy,roads._route_end_ids(f,i,ring))
                        length = np.linalg.norm(np.diff(xy, axis=0), axis=1).sum()
                        # Routing connectors can split a real deck into a
                        # sub-metre part. Omitting that part made the whole
                        # connected bridge fall back to a different height
                        # solver while its ground approaches used this one.
                        if length<1e-4:
                            continue
                        # Short road/rail/path crossings only; water viaducts keep their solver.
                        z = approach_profile(xy, self.sample)
                        if length>180.:
                            from grading import smooth_profile
                            from grading import resample
                            regular,station=resample(xy,2.)
                            natural=smooth_profile(self.sample(regular),2.,40.)
                            st=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
                            natural=np.interp(st,station,natural)
                            correction=np.interp(st,[0.,st[-1]],[z[0]-natural[0],z[-1]-natural[-1]])
                            z=natural+correction
                        out.append((xy, z, sp.width/2+abs(sp.profile.surface_offset), str(f.ids[i])))
            self.cache[key] = out
            return out

    def near(self, xy, margin=100.):
        la,lo,_ = self.frame.enu_to_geodetic(xy[:,0],xy[:,1],0.)
        pad=margin/111320.; pl=pad/max(.05,math.cos(math.radians(float(np.mean(la)))))
        keys=mapcells.cells_for_bbox(float(min(la))-pad,float(min(lo))-pl,float(max(la))+pad,float(max(lo))+pl)
        cache_key=tuple(sorted(map(str,keys)))
        lo_xy=xy[:,:2].min(0)-margin;hi_xy=xy[:,:2].max(0)+margin
        def local(rows):
            return [r for r in rows if (r[0].max(0)>=lo_xy).all() and (r[0].min(0)<=hi_xy).all()]
        if cache_key in self.near_cache:return [self.solution(r) for r in local(self.near_cache[cache_key])]
        out, seen = [], set()
        for key in sorted(keys,key=str):
            for row in self.cell(key):
                sig=(row[3],tuple(np.round(row[0][0],2)),tuple(np.round(row[0][-1],2)))
                if sig not in seen:
                    seen.add(sig);out.append(row)
        if len(self.near_cache)>128:self.near_cache.clear()
        self.near_cache[cache_key]=out
        return [self.solution(row) for row in local(out)]

    @staticmethod
    def signature(row):
        return (row[3],*np.round(row[0][0],3),*np.round(row[0][-1],3))

    def clear_ground(self,row):
        """Resolve lower-road clearance only for a requested bridge component.

        Reading a data cell must not construct the approach networks of every
        unrelated bridge in it and then repeat that expansion in its neighbours.
        """
        import roads
        xy,z,half,fid=row
        if self.highways.get(fid) in ('motorway','trunk'):return row
        ground=self.network(row)[3];raise_by=0.
        upper_s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
        for gi in self.crossing_indices(xy,ground):
            lower,lsp=ground[gi];crossings=roads._crossings([xy],[lower])
            if not crossings:continue
            key=(tuple(np.round(lower[0],3)),tuple(np.round(lower[-1],3)),lsp.width,lsp.profile.offset)
            if key not in self.mainline_profiles:
                from grading import plan_road
                la,lo,_=self.frame.enu_to_geodetic(lower[:,0],lower[:,1],0.)
                self.mainline_profiles[key]=plan_road(self.frame,np.c_[lo,la],lsp,self.raw)
            plan=self.mainline_profiles[key]
            for _,at,q in crossings:
                if min(at,upper_s[-1]-at)<=roads.AT_GRADE_REACH_M:continue
                _,ls,ps=project(np.asarray(q)[None,:2],plan.xy)
                raise_by=max(raise_by,float(np.interp(ls[0],ps,plan.z))+roads.DECK_ROAD_CLEAR-float(np.interp(at,upper_s,z)))
        return xy,z+max(0.,raise_by),half,fid

    def solution(self, row):
        """Solve a complete touching/parallel component, independent of the query box.

        A terrain block and a road tile request different bounding boxes. Solving
        only the rows in those boxes gave the same abutment two different heights.
        """
        import roads
        wanted=self.signature(row)
        if wanted in self.solutions:return self.solutions[wanted]
        pool={wanted:row};loaded=set();component={wanted}
        while True:
            for sig in sorted(component):
                line=pool[sig][0]
                la,lo,_=self.frame.enu_to_geodetic(line[:,0],line[:,1],0.)
                pad=100./111320.;pl=pad/max(.05,math.cos(math.radians(float(np.mean(la)))))
                for key in sorted(mapcells.cells_for_bbox(float(min(la))-pad,float(min(lo))-pl,float(max(la))+pad,float(max(lo))+pl),key=str):
                    if key in loaded:continue
                    loaded.add(key)
                    for candidate in self.cell(key):pool[self.signature(candidate)]=candidate
            keys=sorted(pool);rows=[pool[k] for k in keys]
            _,edges,_=roads._chain_graph([r[0] for r in rows]);links={}
            for i,(a,b,_) in enumerate(edges):
                for node in (a,b):links.setdefault(node,[]).append(i)
            neighbours={i:set(links[a]+links[b]) for i,(a,b,_) in enumerate(edges)}
            for i,j in roads._deck_beside([r[0] for r in rows],[2*r[2]+8. for r in rows]):
                neighbours[i].add(j);neighbours[j].add(i)
            for i,j,_,_ in roads._deck_crossings([r[0] for r in rows]):
                if self.levels.get(rows[i][3])!=self.levels.get(rows[j][3]):
                    neighbours[i].add(j);neighbours[j].add(i)
            reached={keys.index(wanted)};todo=list(reached)
            while todo:
                for j in neighbours[todo.pop()]-reached:reached.add(j);todo.append(j)
            enlarged={keys[i] for i in reached}
            if enlarged==component:break
            component=enlarged
        out=[self.clear_ground(pool[k]) for k in sorted(component)]
        # Adjacent carriageways share a bridge's vertical alignment. DEM pixels
        # on opposite embankment edges are not independent deck surveys.
        targets=[r[1].copy() for r in out]
        def tangent(line):
            d=np.empty_like(line);d[0]=line[1]-line[0];d[-1]=line[-1]-line[-2]
            if len(line)>2:d[1:-1]=line[2:]-line[:-2]
            return d/np.maximum(np.linalg.norm(d,axis=1),1e-9)[:,None]
        tangents=[tangent(r[0]) for r in out]
        for i,(line,z,half,fid) in enumerate(out):
            for j in range(i):
                other,oz,oh,ofid=out[j]
                if self.levels.get(fid)!=self.levels.get(ofid):continue
                if (line.max(0)+half+oh+8.<other.min(0)).any() or (other.max(0)+half+oh+8.<line.min(0)).any():continue
                distance,at,s=project(line,other)
                k=np.clip(np.searchsorted(s,at),0,len(other)-1)
                dot=abs((tangents[i]*tangents[j][k]).sum(1))
                along0=(line-other[0])@tangents[j][0];along1=(line-other[-1])@tangents[j][-1]
                inside=(distance<half+oh+8.)&(dot>.9)&(along0>=-2.)&(along1<=2.)
                targets[i][inside]=np.maximum(targets[i][inside],np.interp(at[inside],s,oz))
                distance,at,s=project(other,line)
                k=np.clip(np.searchsorted(s,at),0,len(line)-1)
                dot=abs((tangents[j]*tangents[i][k]).sum(1))
                along0=(other-line[0])@tangents[i][0];along1=(other-line[-1])@tangents[i][-1]
                inside=(distance<half+oh+8.)&(dot>.9)&(along0>=-2.)&(along1<=2.)
                targets[j][inside]=np.maximum(targets[j][inside],np.interp(at[inside],s,z))
        targets=roads._join_decks([r[0] for r in out],targets)
        # A mainline and a diverging ramp may share part of one physical deck.
        # Use one longitudinal reference there. Max/average passes over each
        # raw DEM estimate left distinct heights at overlapping outer lanes.
        reference_values=[z.copy() for z in targets]
        lengths=[float(np.linalg.norm(np.diff(r[0],axis=0),axis=1).sum()) for r in out]
        for i,(line,z,half,fid) in enumerate(out):
            refs=sorted((j for j,r in enumerate(out) if self.highways.get(r[3]) in ('motorway','trunk')
                         and self.levels.get(r[3])==self.levels.get(fid)
                         and (self.highways.get(fid) not in ('motorway','trunk') or lengths[j]>lengths[i]+.01)),
                        key=lambda j:(-lengths[j],out[j][3]))
            assigned=np.zeros(len(line),bool)
            for j in refs:
                other,_,oh,_=out[j]
                if (line.max(0)+half+oh+8.<other.min(0)).any() or (other.max(0)+half+oh+8.<line.min(0)).any():continue
                distance,at,s=project(line,other);k=np.clip(np.searchsorted(s,at),0,len(other)-1)
                dot=abs((tangents[i]*tangents[j][k]).sum(1))
                before=(line-other[0])@tangents[j][0];after=(line-other[-1])@tangents[j][-1]
                use=(distance<half+oh+4.)&(dot>.9)&(before>=-8.)&(after<=8.)&~assigned
                if not use.any():continue
                ref=reference_values[j];height=np.interp(at,s,ref)
                height+=np.where(at<1e-5,np.minimum(before,0.)*(ref[1]-ref[0])/max(s[1],1e-9),0.)
                height+=np.where(at>s[-1]-1e-5,np.maximum(after,0.)*(ref[-1]-ref[-2])/max(s[-1]-s[-2],1e-9),0.)
                targets[i][use]=height[use];assigned|=use
        targets=roads._limit_deck_grades([r[0] for r in out],roads._join_decks([r[0] for r in out],targets),raise_only=True)
        targets=roads.constrain_deck_levels([r[0] for r in out],targets,
                    [self.levels.get(r[3],0) for r in out],
                    [2*self.pavements.get(r[3],(r[2],0.))[0] for r in out],roads.DECK_ROAD_CLEAR,margin=.15)
        out=[(r[0],z,r[2],r[3]) for r,z in zip(out,targets)]
        for solved in out:self.solutions[self.signature(solved)]=solved
        return self.solutions[wanted]

    def deck(self, fid, xy):
        best=None
        for line,z,_,name in self.near(xy, 5.):
            if name == fid:
                dist,at,s=project(xy[:,:2],line)
                error=float(dist.max())
                if error<.75 and (best is None or error<best[0]):best=(error,np.interp(at,s,z))
        return best[1] if best else None

    def paths(self, xy):
        """Mapped pedestrian subways; floor and bore are independent of the upper road."""
        import ukcontext, roads
        la,lo,_=self.frame.enu_to_geodetic(xy[:,0],xy[:,1],0.)
        bounds=(float(min(lo))-.001,float(min(la))-.001,float(max(lo))+.001,float(max(la))+.001)
        out=[]
        for oid,_,t,ll in ukcontext.features(bounds,('underpass',)):
            if t.get('tunnel')=='building_passage' or len(ll)<2:continue
            if oid not in self.path_cache:
                x,y,_=self.frame.geodetic_to_enu(ll[:,1],ll[:,0],0.)
                line=roads.densify(np.c_[x,y],2.)
                floor=approach_profile(line,self.sample)
                for upper,top,half,_ in self.near(line,5.):
                    cr=roads._crossings([line],[upper])
                    if cr:
                        q=np.asarray(cr[0][2])[None,:2];_,station,s=project(q,upper)
                        ceiling=float(np.interp(station[0],s,top))
                        floor=np.minimum(floor,ceiling-5.4)
                self.path_cache[oid]=(line,floor,1.5)
            out.append(self.path_cache[oid])
        return out

    def network(self, structure):
        """One canonical ground network for both floors' connected approaches."""
        import roads
        line,z,half,fid=structure
        key=(fid,tuple(np.round(line[0],2)),tuple(np.round(line[-1],2)))
        if key in self.graph_cache:return self.graph_cache[key]
        la,lo,_=self.frame.enu_to_geodetic(line[:,0],line[:,1],0.)
        pad=450./111320.;pl=pad/max(.05,math.cos(math.radians(float(np.mean(la)))))
        keys=mapcells.cells_for_bbox(float(min(la))-pad,float(min(lo))-pl,float(max(la))+pad,float(max(lo))+pl)
        keys=tuple(sorted(keys,key=str))
        network_key=tuple(map(str,keys))
        if network_key in self.network_graphs:
            result=self.network_graphs[network_key]
            self.graph_cache[key]=result
            return result
        lines=[];seen=set()
        for ck in keys:
            if ck not in self.network_cache:
                f=self.md.cell(ck,layers=('roads',),kind='demand').layers.get('roads');rows=[]
                if f is not None:
                    for i,sp in enumerate(roads.road_specs(f)):
                        if sp is None or sp.profile is None:continue
                        for ll in roads.ground_parts(f,i):
                            x,y,_=self.frame.geodetic_to_enu(ll[:,1],ll[:,0],0.)
                            rows.append((roads.RouteLine(np.c_[x,y],roads._route_end_ids(f,i,ll)),sp))
                self.network_cache[ck]=rows
            for xy,sp in self.network_cache[ck]:
                sig=tuple(np.round(np.r_[xy[0],xy[-1]],2))
                if sig not in seen:seen.add(sig);lines.append((xy,sp))
        nodes,edges,adj=roads._chain_graph([xy for xy,_ in lines]);nodes=np.asarray(nodes)
        result=(nodes,edges,adj,lines)
        self.network_graphs[network_key]=result
        self.graph_cache[key]=result
        return result

    def ground_nodes(self, structure):
        """Natural, smoothed ground heights at the network's actual endpoints.

        Raw DEM at an abutment can be a trench pixel. Propagating that pixel's
        correction onto other source sections created several-metre humps.
        """
        nodes,edges,adj,lines=self.network(structure)
        key=id(lines)
        if key not in self.node_profiles:
            from grading import plan_roads
            parts=[]
            for xy,sp in lines:
                la,lo,_=self.frame.enu_to_geodetic(xy[:,0],xy[:,1],0.)
                parts.append((np.c_[lo,la],sp))
            plans=plan_roads(self.frame,parts,self.raw)
            values=[[] for _ in nodes]
            for p,(a,b,_) in zip(plans,edges):
                values[a].append(p.z[0]);values[b].append(p.z[-1])
            self.node_profiles[key]=np.array([np.median(v) for v in values])
        return self.node_profiles[key]

    def natural_cell(self,key):
        """Cache unmodified profiles once; never recurse into resolved floors."""
        import roads
        if key in self.natural_ends:return self.natural_ends[key]
        f=self.md.cell(key,layers=('roads',),kind='demand').layers.get('roads');parts=[];ends=[]
        if f is not None:
            for i,sp in enumerate(roads.road_specs(f)):
                if sp is None or sp.profile is None:continue
                for ll in roads.ground_parts(f,i):
                    parts.append((ll,sp));ends.append((str(f.ids[i]),roads._route_end_ids(f,i,ll),ll[[0,-1]]))
        from grading import plan_roads
        rows=[];network=[]
        for (fid,ids,ll),(source,sp),p in zip(ends,parts,plan_roads(self.frame,parts,self.raw)):
            x,y,_=self.frame.geodetic_to_enu(ll[:,1],ll[:,0],0.)
            for j,at in enumerate((0,-1)):rows.append((fid,ids[j],np.array([x[j],y[j]]),p.z[at]))
            xx,yy,_=self.frame.geodetic_to_enu(source[:,1],source[:,0],0.)
            highway=sp.profile.highway.removesuffix('_link')
            limit=.08 if highway in ('motorway','trunk') else .15 if highway in ('primary','secondary') else np.inf
            network.append((fid,roads.RouteLine(np.c_[xx,yy],ids),p.z[[0,-1]],limit))
        self.natural_ends[key]=rows;self.natural_roads[key]=network
        return rows

    def endpoint_height(self, point, identity):
        """One natural endpoint height regardless of source section or map cell."""
        cache_key=(identity,) if identity is not None else (None,*np.round(point,3))
        if cache_key in self.end_heights:return self.end_heights[cache_key]
        la,lo,_=self.frame.enu_to_geodetic(*point,0.)
        keys=mapcells.cells_for_bbox(float(la)-.00002,float(lo)-.00003,float(la)+.00002,float(lo)+.00003)
        values={}
        for key in keys:
            for fid,other,q,h in self.natural_cell(key):
                if identity is not None and other is not None and identity!=other:continue
                if np.linalg.norm(q-point)<.75:values[(fid,*np.round(q,3))]=h
        value=float(np.median(list(values.values()))) if values else float(self.sample(point[None])[0])
        # Select by the node itself, never the road tile requesting it. Only
        # nodes near a cell boundary need neighbouring source data; eagerly
        # planning all eight neighbours made local loading far too expensive.
        pad=120./111320.;pl=pad/max(.05,math.cos(math.radians(float(la))))
        key=tuple(sorted(mapcells.cells_for_bbox(float(la)-pad,float(lo)-pl,float(la)+pad,float(lo)+pl),key=str))
        if key not in self.endpoint_graphs:
            network={};anchors=[]
            for ck in key:
                self.natural_cell(ck)
                for fid,line,z,limit in self.natural_roads[ck]:
                    network.setdefault((fid,*np.round(line[0],3),*np.round(line[-1],3)),(line,z,limit))
                for line,z,_,_ in self.cell(ck):
                    ids=getattr(line,'end_ids',(None,None))
                    anchors.extend((line[at],ids[at],z[at]) for at in (0,-1))
            rows=list(network.values())
            nodes,edges,z=ground_endpoint_envelope([r[0] for r in rows],[r[1] for r in rows],[r[2] for r in rows],anchors)
            identities={}
            for (line,_,_),(a,b,_) in zip(rows,edges):
                for node,ident in zip((a,b),line.end_ids):
                    if ident is not None:identities.setdefault(ident,[]).append(node)
            self.endpoint_graphs[key]=(nodes,z,identities)
        nodes,z,identities=self.endpoint_graphs[key]
        candidates=identities.get(identity,[]) if identity is not None else range(len(nodes))
        at=min(candidates,key=lambda j:np.linalg.norm(nodes[j]-point),default=None)
        if at is not None and np.linalg.norm(nodes[at]-point)<.75:value=float(z[at])
        self.end_heights[cache_key]=value
        return value

    def aligned_endpoint(self, point, identity):
        """Resolve a routing junction once, then pin every incident road to it."""
        import roads
        key=(identity,) if identity is not None else (None,*np.round(point,3))
        if key in self.aligned_ends:return self.aligned_ends[key]
        baseline=self.endpoint_height(point,identity);anchors=[]
        for structure in self.near(point[None],450.):
            line,z,_,_=structure;nodes,_,adj,_=self.network(structure)
            if not len(nodes):continue
            node=int(np.argmin(np.linalg.norm(nodes-point,axis=1)))
            if np.linalg.norm(nodes[node]-point)>.75:continue
            for end,other in ((0,1),(-1,-2)):
                sn=int(np.argmin(np.linalg.norm(nodes-line[end],axis=1)))
                if np.linalg.norm(nodes[sn]-line[end])>.75:continue
                sk=(self.signature(structure),end)
                if sk not in self.seed_distances:self.seed_distances[sk]=roads._dijkstra(adj,{sn:0.})
                d=float(self.seed_distances[sk][node])
                if d>320.:continue
                grade=end_grade(line,z,end)
                anchors.append((d,float(z[end]),float(grade),line[end]))
        anchors.sort(key=lambda a:(a[0],a[1],*a[3]))
        if not anchors:value=baseline
        elif anchors[0][0]<.001:value=float(np.mean([a[1] for a in anchors if a[0]<.001]))
        else:
            # A deck fixes its abutment, not every junction within hundreds
            # of metres. Keep the natural junction height unless reaching
            # an actual connected deck requires a gentler approach.
            bounds=[grade_bounds(a[1],a[2],a[0]) for a in anchors]
            low=max(b[0] for b in bounds)
            high=min(b[1] for b in bounds)
            value=float(np.clip(baseline,low,high)) if low<=high else (low+high)/2
        self.aligned_ends[key]=float(value)
        return float(value)

    def crossing_indices(self,line,ground):
        key=id(ground)
        if key not in self.network_bounds:
            self.network_bounds[key]=(np.array([g[0].min(0) for g in ground]).reshape(-1,2),
                                      np.array([g[0].max(0) for g in ground]).reshape(-1,2))
        lo,hi=self.network_bounds[key]
        return np.flatnonzero((hi>=line.min(0)).all(1)&(lo<=line.max(0)).all(1))

    def cuts(self, structure):
        """Lower clearance follows source seams; at most 5% added approach grade."""
        import roads
        line,z,half,fid=structure
        key=(fid,tuple(np.round(line[0],2)),tuple(np.round(line[-1],2)))
        if key in self.cut_cache:return self.cut_cache[key]
        nodes,edges,adj,lines=self.network(structure)
        cuts=[]
        for k in self.crossing_indices(line,lines):
            xy,sp=lines[k]
            # A relative bridge layer does not establish an absolute height
            # for another road. Keep every vehicular road on its independent
            # approach profile; inferring a floor as deck minus clearance dug
            # false trenches through slip roads and their junctions. Explicit
            # road tunnels have their own floor/portal model.
            if sp.cls not in ('track','path','footway','cycleway'):continue
            for _,upper_at,q in roads._crossings([line],[xy]):
                upper_s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(line,axis=0),axis=1))]
                if min(upper_at,upper_s[-1]-upper_at)<=roads.AT_GRADE_REACH_M:continue
                _,lower_at,s=project(np.asarray(q)[None,:2],xy)
                a,b,ss=edges[k]
                distances=roads._dijkstra(adj,{a:float(lower_at[0]),b:float(s[-1]-lower_at[0])})
                clearance=5.4 if sp.cls in ('track','path','footway','cycleway') else roads.DECK_ROAD_CLEAR
                floor=float(np.interp(upper_at,upper_s,z))-clearance
                cuts.append((nodes,distances,floor,half,xy,float(lower_at[0])))
        self.cut_cache[key]=cuts
        return cuts

    def adjust(self, plans, specs, store=True):
        """Approaches join the upper profile; crossing ground routes stay below its soffit."""
        import roads
        if not plans:
            return
        nearby={}
        for (_,p),sp in zip(plans,specs):
            queries=[(p.xy,100.)] if sp.cls in ('track','path','footway','cycleway') else [(p.xy[[end]],450.) for end in (0,-1)]
            for points,margin in queries:
                for row in self.near(points,margin):nearby[self.signature(row)]=row
        structures=list(nearby.values())
        lower_cuts=[cut for structure in structures for cut in self.cuts(structure)]
        upper_seeds=[]
        for structure in structures:
            line,z,half,name=structure
            nodes,edges,adj,lines=self.network(structure)
            if not len(nodes):continue
            for be in (0,-1):
                at=int(np.argmin(np.linalg.norm(nodes-line[be],axis=1)))
                if np.linalg.norm(nodes[at]-line[be])>.75:continue
                distances=roads._dijkstra(adj,{at:0.})
                correction=float(z[be]-self.ground_nodes(structure)[at])
                radius=max(100.,abs(correction)*np.pi/(2*.045))
                j=1 if be==0 else -2
                outward_grade=end_grade(line,z,be)
                upper_seeds.append((nodes,distances,line[be],z[be],outward_grade,radius,self.ground_nodes(structure)))
        for i, ((fid,p), sp) in enumerate(zip(plans,specs)):
            if sp.profile is None:
                continue
            topology=p.xy
            if sp.profile.surface_offset:
                topology=roads.offset_polyline(np.c_[p.xy,np.zeros(len(p.xy))],-sp.profile.surface_offset)[:,:2]
            s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(p.xy,axis=0),axis=1))]
            baseline=p.z.copy()
            # Reconcile natural endpoint heights before propagating one shared
            # correction through source splits. Preserve the intervening grade.
            ends=topology[[0,-1]]
            # Round caps fill genuine surface junctions across the terrain
            # lattice. Only an abutment stops at its cut plane; excluding all
            # endpoint caps left ungraded grid vertices in junction centres.
            p.caps=tuple(not any(np.linalg.norm(q-r[0][at])<.75 and
                                (identity is None or getattr(r[0],'end_ids',(None,None))[at] in (None,identity))
                                for r in structures for at in (0,-1)) for q,identity in zip(ends,p.end_ids))
            target=np.array([self.endpoint_height(q,identity) for q,identity in zip(ends,p.end_ids)])
            delta=target-p.z[[0,-1]]
            length=max(s[-1],1e-9)
            run=np.maximum(36.,abs(delta)*np.pi/(2*.045))
            w0=(1-s/length)*.5*(1+np.cos(np.pi*np.clip(s/run[0],0,1)))
            w1=s/length*.5*(1+np.cos(np.pi*np.clip((length-s)/run[1],0,1)))
            baseline=p.z+delta[0]*w0+delta[1]*w1
            zz=baseline.copy()
            lower=np.full(len(p.xy),-np.inf);upper=np.full(len(p.xy),np.inf)
            upper_active=np.zeros(len(p.xy),bool)
            for nodes,distances,seed,top,outward_grade,radius,_ in upper_seeds:
                ends=topology[[0,-1]]
                if np.min(np.linalg.norm(ends-seed,axis=1))>radius+1.:continue
                idx=[int(np.argmin(np.linalg.norm(nodes-q,axis=1))) for q in ends]
                if any(np.linalg.norm(nodes[j]-q)>.75 for j,q in zip(idx,ends)):continue
                d=np.minimum(distances[idx[0]]+s,distances[idx[1]]+s[-1]-s)
                # An admissible grade envelope changes only DEM defects that
                # cannot reach the fixed deck. Extrapolated tangent planes
                # raised already recovered roads and whole roundabouts into
                # humps; independent cosine fades also fought each other.
                low,high=grade_bounds(top,outward_grade,d)
                lower=np.maximum(lower,low)
                upper=np.minimum(upper,high)
            valid=lower<=upper
            zz[valid]=np.clip(zz[valid],lower[valid],upper[valid])
            zz[~valid]=(lower[~valid]+upper[~valid])/2
            upper_active=abs(zz-baseline)>1e-8
            for nodes,distances,floor,half,seed_line,seed_at in lower_cuts:
                ends=topology[[0,-1]]
                idx=[int(np.argmin(np.linalg.norm(nodes-q,axis=1))) for q in ends]
                if any(np.linalg.norm(nodes[j]-q)>.75 for j,q in zip(idx,ends)):continue
                d=np.minimum(distances[idx[0]]+s,distances[idx[1]]+s[-1]-s)
                # The crossing can be inside an edge, not at a graph node.
                dist,at,_=project(topology,seed_line)
                d=np.minimum(d,np.where(dist<.75,np.abs(at-seed_at),np.inf))
                run=np.maximum(0.,d-half-2.)
                target=floor+.05*(run-10.*(1.-np.exp(-run/10.)))
                zz=np.minimum(zz,target)
            major=sp.profile.highway.removesuffix('_link') in ('motorway','trunk','primary','secondary')
            if major or upper_active.any():
                pins=np.array([self.aligned_endpoint(q,identity) for q,identity in zip(ends,p.end_ids)])
                delta=pins-zz[[0,-1]]
                length=max(s[-1],1e-9);run=np.maximum(80.,abs(delta)*np.pi/(2*.045))
                w0=(1-s/length)*.5*(1+np.cos(np.pi*np.clip(s/run[0],0,1)))
                w1=s/length*.5*(1+np.cos(np.pi*np.clip((length-s)/run[1],0,1)))
                zz+=delta[0]*w0+delta[1]*w1
            # Major through roads need a gentler DEM-noise envelope than their
            # short slip roads. Shared endpoints remain fixed; only feasible
            # interior spikes are limited, without flattening a real hill.
            limit=.06 if sp.profile.mainline else .07 if sp.profile.highway.removesuffix('_link') in ('motorway','trunk') else .12
            if major:
                average=abs(zz[-1]-zz[0])/max(s[-1],1e-9)
                if average>limit:
                    # A gentle preference must not disable spike protection
                    # on a source section whose fixed ends need more grade.
                    # Retain the feasible major-road envelope and both pins.
                    limit=max(average+1e-9,.08 if limit<=.08 else .15)
                # Remove DEM steps while keeping both shared endpoint pins.
                # Work on the complete source section, never a tile slice.
                low=np.maximum(zz[0]-limit*s,zz[-1]-limit*(s[-1]-s))
                high=np.minimum(zz[0]+limit*s,zz[-1]+limit*(s[-1]-s))
                zz=np.clip(zz,low,high)
                for j in range(1,len(zz)):zz[j]=np.clip(zz[j],zz[j-1]-limit*(s[j]-s[j-1]),zz[j-1]+limit*(s[j]-s[j-1]))
                for j in range(len(zz)-2,-1,-1):zz[j]=np.clip(zz[j],zz[j+1]-limit*(s[j+1]-s[j]),zz[j+1]+limit*(s[j+1]-s[j]))
            if not np.array_equal(zz,p.z):
                from grading import Plan
                plans[i]=(fid,Plan(p.xy,zz,p.half,p.end_ids,p.caps))
            if major and store:
                from grading import Plan
                key=(fid,tuple(np.round(p.xy[0],3)),tuple(np.round(p.xy[-1],3)))
                self.mainline_plans[key]=Plan(p.xy,zz,p.half,p.end_ids,p.caps)
                self.floor_specs[key]=sp
                self.plan_specs[self.mainline_plans[key]]=sp
            if upper_active.any() and store:
                from grading import Plan
                key=(fid,tuple(np.round(p.xy[0],3)),tuple(np.round(p.xy[-1],3)))
                self.upper_plans[key]=Plan(p.xy,zz,p.half,p.end_ids,p.caps)
                self.floor_specs[key]=sp
                self.plan_specs[self.upper_plans[key]]=sp

    def excavate(self, xy, base, lift, surface_plans=()):
        """Keep terrain out of bridge slabs across their entire width, including verges.

        Zero depth exactly at abutments; the deck owns collision over the cavity.
        This applies identically to the physics block and visible near terrain.
        """
        out=np.asarray(base,float).copy()
        protected=core_mask(xy,surface_plans)
        for line,z,half,_ in self.near(xy, 5.):
            lo=line.min(0)-half-2.;hi=line.max(0)+half+2.
            keep=((xy>=lo)&(xy<=hi)).all(1)
            ids=np.flatnonzero(keep)
            if not len(ids):continue
            dist,at,s=project(xy[ids],line)
            reach=np.minimum(at,s[-1]-at)
            depth=np.minimum(2.8,np.maximum(0.,reach)*.6)
            top=np.interp(at,s,z)
            inside=(dist<=half+1.)&(reach>.15)&~protected[ids]
            out[ids[inside]]=np.minimum(out[ids[inside]],top[inside]-depth[inside]+lift)
        for line,floor,half in self.paths(xy):
            u=(line[1]-line[0]);u/=max(np.linalg.norm(u),1e-9)
            v=(line[-1]-line[-2]);v/=max(np.linalg.norm(v),1e-9)
            extra=np.array([line[0]-30*u,line[-1]+30*v])
            outside=self.sample(extra)
            line=np.vstack([extra[0],line,extra[1]])
            floor=np.r_[outside[0],floor,outside[1]]
            lo=line.min(0)-half-3.;hi=line.max(0)+half+3.
            ids=np.flatnonzero(((xy>=lo)&(xy<=hi)).all(1))
            if not len(ids):continue
            dist,at,s=project(xy[ids],line)
            inside=dist<half+1.5
            weight=np.clip((half+1.5-dist)/1.5,0.,1.)
            # A subway's portal/approach is not permission to excavate a
            # surface street it crosses. Its roof belongs below that street.
            weight[protected[ids]]=0.
            target=np.interp(at,s,floor)+lift
            out[ids[inside]]-=np.maximum(0.,out[ids[inside]]-target[inside])*weight[inside]
        return out

    def interfaces(self, xy, base, lift):
        """Full-width abutment constraints before the terrain is triangulated.

        A nearby branch cannot blend one edge of a deck's approach above or
        below its slab while the centreline remains correct.
        """
        out=np.asarray(base,float).copy();num=np.zeros(len(xy));den=np.zeros(len(xy))
        for structure in self.near(xy,10.):
            line,z,half,name=structure
            nodes,_,_,_=self.network(structure)
            if not len(nodes):continue
            half,offset=self.pavements.get(name,(half,0.))
            shifted=__import__('roads').offset_polyline(np.c_[line,np.zeros(len(line))],offset)[:,:2] if offset else line
            for end,other in ((0,1),(-1,-2)):
                if np.linalg.norm(nodes-line[end],axis=1).min()>.75:continue
                u=line[end]-line[other];length=max(np.linalg.norm(u),1e-9);u/=length
                delta=xy-shifted[end];station=delta@u;cross=abs(delta[:,0]*u[1]-delta[:,1]*u[0])
                keep=(station>=-1.)&(station<6.)&(cross<half+.001)
                if not keep.any():continue
                w=.5*(1+np.cos(np.pi*np.clip(station[keep]/6.,0,1)))
                target=z[end]+(z[end]-z[other])/length*station[keep]+lift
                weight=w/np.maximum(station[keep],1e-4)**2
                num[keep]+=weight*w*(target-base[keep]);den[keep]+=weight
        good=den>0;out[good]+=num[good]/den[good]
        return out

    def surface(self, xy, reference=None, owner=None):
        """The road layer, independent of the DEM/terrain blending beneath it.

        Nearby parts blend only their resolved road profiles. A two-metre guard
        band provides every lattice corner used by the pavement, including at
        junctions; terrain outside a narrow ribbon cannot pull its tyres down.
        """
        xy=np.asarray(xy,float);lowest=np.full(len(xy),np.inf);candidates=[]
        rows=dict(self.mainline_plans);rows.update(self.upper_plans)
        structures=self.near(xy,40.) if self.md is not None and len(xy) else []
        for p in rows.values():
            lo=np.asarray(p.bbox[:2]);hi=np.asarray(p.bbox[2:]);ids=np.flatnonzero(((xy>=lo)&(xy<=hi)).all(1))
            if not len(ids):continue
            distance,at,s=project(xy[ids],p.xy,reach=p.half+2.)
            u=p.xy[1]-p.xy[0];u/=max(np.linalg.norm(u),1e-9)
            v=p.xy[-1]-p.xy[-2];v/=max(np.linalg.norm(v),1e-9)
            before=(xy[ids]-p.xy[0])@u;after=(xy[ids]-p.xy[-1])@v
            valid=(distance<p.half+2.)
            if not p.caps[0]:valid&=(at>1e-5)|(before>=-2.)
            if not p.caps[1]:valid&=(at<s[-1]-1e-5)|(after<=2.)
            weight=np.clip((p.half+2.-distance)/2.,0.,1.)
            weight=weight*weight*(3.-2.*weight)/(1.+(distance/4.)**2);weight[~valid]=0.
            target=np.interp(at,s,p.z)
            target+=np.where(at<1e-5,np.minimum(before,0.)*(p.z[1]-p.z[0])/max(s[1],1e-9),0.)
            target+=np.where(at>s[-1]-1e-5,np.maximum(after,0.)*(p.z[-1]-p.z[-2])/max(s[-1]-s[-2],1e-9),0.)
            target=self.road_interfaces(xy[ids],target,p,structures)
            active=weight>1e-12
            lowest[ids]=np.minimum(lowest[ids],np.where(active,target,np.inf))
            # A bridge cut needs its lattice guard beyond the abutment; the
            # road/bridge end tangents can differ across a wide outer lane.
            # Ordinary junction caps must not override an interior through
            # road several metres beyond their source endpoint.
            interior=((at>1e-5)|(before>=(-2. if not p.caps[0] else -1e-6)))&((at<s[-1]-1e-5)|(after<=(2. if not p.caps[1] else 1e-6)))
            candidates.append((p,ids,target,weight,distance,interior))
        # Ground roads form one continuous surface at junctions and shared
        # verges. Separate storeys retain separate floors; terrain supports
        # the lowest one while an upper pavement requests its own layer.
        if not candidates:return np.zeros(len(xy),bool),np.zeros(len(xy))
        target=np.full((len(candidates),len(xy)),np.inf);weight=np.zeros_like(target);distance=np.full_like(target,np.inf)
        strict=np.zeros_like(target,dtype=bool)
        for j,(_,ids,zz,ww,dd,inside) in enumerate(candidates):
            target[j,ids]=zz;weight[j,ids]=ww;distance[j,ids]=dd;strict[j,ids]=inside
        anchor=lowest if reference is None else np.asarray(reference)
        difference=np.full_like(target,np.inf)
        np.subtract(target,anchor[None,:],out=difference,where=np.isfinite(target)&np.isfinite(anchor[None,:]))
        valid=(weight>1e-12)&(abs(difference)<3.)
        # A source endpoint cap supports a corner wedge, but it must use the
        # continuing road there. Extrapolating its own end slope across the
        # next source section creates a step at the cap's outer boundary.
        ends={}
        for j,(p,*_) in enumerate(candidates):
            for e,k in ((0,0),(-1,1)):
                identity=p.end_ids[k]
                key=('id',identity) if identity is not None else ('xy',*np.round(p.xy[e],2))
                ends.setdefault(key,[]).append(j)
        for i,(p,*_) in enumerate(candidates):
            cap=valid[i]&~strict[i]
            if not cap.any():continue
            neighbours=set()
            for e,k in ((0,0),(-1,1)):
                identity=p.end_ids[k]
                key=('id',identity) if identity is not None else ('xy',*np.round(p.xy[e],2))
                neighbours.update(ends[key])
            num=np.zeros(len(xy));den=np.zeros(len(xy))
            for j in neighbours-{i}:
                use=cap&strict[j]&valid[j]
                num[use]+=target[j,use]*weight[j,use];den[use]+=weight[j,use]
            use=den>1e-12;target[i,use]=num[use]/den[use]
        ww=weight*valid;total=ww.sum(0);mask=total>1e-12;z=np.zeros(len(xy))
        z[mask]=(np.where(ww>0,target,0)*ww).sum(0)[mask]/total[mask]
        # A motorway's pavement must keep its resolved longitudinal alignment.
        # Supporting fill follows that pavement through its outer edge; the
        # other carriageway's DEM estimate cannot stand above it or excavate it.
        pavement=np.full(len(xy),np.inf)
        for j,(p,*_) in enumerate(candidates):
            sp=self.plan_specs.get(p)
            if sp is None or sp.profile.highway.removesuffix('_link') not in ('motorway','trunk'):continue
            keep=valid[j]&(distance[j]<sp.width/2+2.)
            pavement[keep]=np.minimum(pavement[keep],target[j,keep])
        keep=np.isfinite(pavement);z[keep]=pavement[keep];mask[keep]=True
        return mask,z

    def floor_plan(self, fid, line):
        """The complete source section owning a pavement, including its pins."""
        rows=dict(self.mainline_plans);rows.update(self.upper_plans);best=None
        q=np.asarray(line,float)[:,:2]
        for key,p in rows.items():
            if key[0]!=fid:continue
            distance,_,_=project(q[[0,-1]],p.xy)
            score=float(distance.sum())
            if best is None or score<best[0]:best=(score,p)
        return best[1] if best is not None else None

    def road_heights(self, xy, plan, lift=.04):
        """A road's own floor. Nearby or crossing roads cannot change its level."""
        import terrain_surface
        structures=self.near(np.asarray(xy)[:,:2],40.) if self.md is not None and len(xy) else []
        def elevation(la,lo):
            x,y,_=self.frame.geodetic_to_enu(la,lo,0.);q=np.c_[x,y]
            pieces=[project(q[j:j+256],plan.xy) for j in range(0,len(q),256)]
            if not pieces:return np.empty(0)
            at=np.concatenate([r[1] for r in pieces]);s=pieces[0][2];z=np.interp(at,s,plan.z)
            for end,other,edge in ((0,1,at<1e-5),(-1,-2,at>s[-1]-1e-5)):
                d=plan.xy[end]-plan.xy[other];length=max(np.linalg.norm(d),1e-9);d/=length
                station=np.maximum((q-plan.xy[end])@d,0.)
                z+=np.where(edge,station*(plan.z[end]-plan.z[other])/length,0.)
            z=self.road_interfaces(q,z,plan,structures)
            sp=self.plan_specs.get(plan)
            if sp is not None and sp.profile.highway.removesuffix('_link') not in ('motorway','trunk'):
                mask,shared=self.surface(q,reference=z)
                z[mask]=shared[mask]
            # The shared field already resolves each candidate's abutment.
            # Repeating the correction steepens it and creates a second crest.
            return z+lift
        return terrain_surface.heights(self.frame,elevation,np.asarray(xy)[:,:2])

    def road_interfaces(self, xy, base, plan, structures):
        """Match the entire abutment plane of this road's connected bridge.

        Centre pins alone do not meet across a wide curved road: its outer
        lane can already project metres along the bridge while the ground
        profile still clamps to the endpoint. Keep this constraint tied to
        routing identity so an adjacent ramp cannot alter the carriageway.
        """
        out=np.asarray(base,float).copy();num=np.zeros(len(xy));den=np.zeros(len(xy))
        for line,z,half,name in structures:
            width,offset=self.pavements.get(name,(half,0.))
            shifted=__import__('roads').offset_polyline(np.c_[line,np.zeros(len(line))],offset)[:,:2] if offset else line
            ids=getattr(line,'end_ids',(None,None))
            for end,other in ((0,1),(-1,-2)):
                matches=[k for k in (0,-1) if np.linalg.norm(plan.xy[k]-shifted[end])<2.5
                         and (plan.end_ids[k] is None or ids[end] is None or plan.end_ids[k]==ids[end])]
                if not matches:continue
                # An offset miter can reverse a sub-millimetre source segment.
                # Its direction is not the bridge's longitudinal direction.
                u=line[end]-line[other];length=max(np.linalg.norm(u),1e-9);u/=length
                delta=xy-shifted[end];station=delta@u;cross=abs(delta[:,0]*u[1]-delta[:,1]*u[0])
                keep=(station>=-plan.half-2.)&(station<24.)&(cross<max(width,plan.half)+2.)
                if not keep.any():continue
                w=.5*(1+np.cos(np.pi*np.clip(station[keep]/24.,0,1)))
                strength=w/np.maximum(station[keep],.05)**2
                # Repair the cross-section at the seam, not the road's
                # longitudinal grade. Blending the whole approach toward an
                # extrapolated deck plane produced a crest even on a valid
                # steadily climbing road.
                seam=xy[keep]-station[keep,None]*u
                _,at,arc=project(seam,plan.xy)
                seam_height=np.interp(at,arc,plan.z)
                for pe,po,edge in ((0,1,at<1e-5),(-1,-2,at>arc[-1]-1e-5)):
                    direction=plan.xy[pe]-plan.xy[po]
                    distance=max(np.linalg.norm(direction),1e-9);direction/=distance
                    extension=np.maximum((seam-plan.xy[pe])@direction,0.)
                    seam_height+=np.where(edge,extension*(plan.z[pe]-plan.z[po])/distance,0.)
                num[keep]+=strength*w*(z[end]-seam_height);den[keep]+=strength
        use=den>0;out[use]+=num[use]/den[use]
        return out

    def approach_heights(self, xy, line, end):
        rows=dict(self.mainline_plans);rows.update(self.upper_plans)
        nearby=[p for p in rows.values() if np.linalg.norm(p.xy[[0,-1]]-line[end,:2],axis=1).min()<2.5]
        if not nearby:return self.surface_heights(xy)
        best=np.full(len(xy),np.inf);z=np.zeros(len(xy))
        for p in nearby:
            distance,_,_=project(xy,p.xy);keep=distance<best
            if keep.any():z[keep]=self.road_heights(xy[keep],p);best[keep]=distance[keep]
        return z

    def approach_footprint(self, xy, line, end):
        """A bridge transition belongs to its connected approach corridor.

        Extending a rectangular ramp patch through a neighbouring carriageway
        put the ramp's higher surface directly across that road's outer lane.
        """
        rows=dict(self.mainline_plans);rows.update(self.upper_plans)
        own=[];other=[]
        for key,p in rows.items():
            sp=self.floor_specs.get(key);drive=p.xy
            if sp is not None and sp.profile.offset:
                drive=__import__('roads').offset_polyline(np.c_[p.xy,np.zeros(len(p.xy))],sp.profile.offset)[:,:2]
            if np.linalg.norm(p.xy[[0,-1]]-line[end,:2],axis=1).min()<2.5:own.append((p,drive))
            elif (np.asarray(p.bbox[2:])>=xy.min(0)).all() and (np.asarray(p.bbox[:2])<=xy.max(0)).all():other.append((p,drive))
        if not own:return np.ones(len(xy),bool)
        distance=np.full(len(xy),np.inf)
        for p,drive in own:distance=np.minimum(distance,project(xy,drive)[0])
        keep=np.ones(len(xy),bool)
        for p,drive in other:
            d,_,_=project(xy,drive)
            keep&=~((d<distance-.1)&(d<p.half))
        return keep

    def protected_mainlines(self, line, end):
        """Driving lanes a neighbouring approach patch must not occupy."""
        import roads,roadmesh
        rows=dict(self.mainline_plans);rows.update(self.upper_plans);out=[]
        low=line[end,:2]-30.;high=line[end,:2]+30.
        for key,p in rows.items():
            sp=self.floor_specs.get(key)
            if sp is None or sp.profile.highway.removesuffix('_link') not in ('motorway','trunk','primary','secondary'):continue
            if np.linalg.norm(p.xy[[0,-1]]-line[end,:2],axis=1).min()<2.5:continue
            if (np.asarray(p.bbox[2:])<low).any() or (np.asarray(p.bbox[:2])>high).any():continue
            height=float(self.road_heights(line[[end],:2],p)[0])
            if abs(height-line[end,2])>3.:continue
            drive=roads.offset_polyline(np.c_[p.xy,np.zeros(len(p.xy))],sp.profile.offset)[:,:2] if sp.profile.offset else p.xy
            normal=roadmesh._normals(drive)*(sp.profile.drive/2+.03)
            left,right=drive+normal,drive-normal
            for i in range(len(drive)-1):
                q=np.array([left[i],right[i],right[i+1],left[i+1]])
                if (q.max(0)>=low).all() and (q.min(0)<=high).all():out.append(q)
            angles=np.arange(32)*2*np.pi/32
            circle=np.c_[np.cos(angles),np.sin(angles)]*(sp.profile.drive/2+.08)
            for end_at in (0,-1):
                if (drive[end_at]>=low-sp.profile.drive).all() and (drive[end_at]<=high+sp.profile.drive).all():out.append(drive[end_at]+circle)
        # Ground polygons stop at the abutment cut plane. Protect the actual
        # neighbouring deck too: a ramp's rectangle could otherwise cross the
        # first metre of its traffic lane, beyond the ground polygon's end.
        for centre,z,half,name in self.near(np.asarray(line)[:,:2],10.):
            if self.highways.get(name,'').removesuffix('_link') not in ('motorway','trunk','primary','secondary'):continue
            _,offset=self.pavements.get(name,(half,0.))
            shifted=roads.offset_polyline(np.c_[centre,np.zeros(len(centre))],offset)[:,:2] if offset else centre
            if np.linalg.norm(shifted[[0,-1]]-line[end,:2],axis=1).min()<2.5:continue
            distance,at,s=project(line[[end],:2],centre)
            if abs(float(np.interp(at[0],s,z))-line[end,2])>3.:continue
            normal=roadmesh._normals(centre)*(self.bridge_drives.get(name,2*half)/2+.03)
            left,right=centre+normal,centre-normal
            for i in range(len(centre)-1):
                q=np.array([left[i],right[i],right[i+1],left[i+1]])
                if (q.max(0)>=low).all() and (q.min(0)<=high).all():out.append(q)
            radius=self.bridge_drives.get(name,2*half)/2+.08
            angles=np.arange(32)*2*np.pi/32;circle=np.c_[np.cos(angles),np.sin(angles)]*radius
            for end_at in (0,-1):
                if (centre[end_at]>=low-radius).all() and (centre[end_at]<=high+radius).all():out.append(centre[end_at]+circle)
        return out

    def ground_exclusions(self, line, width):
        """A neighbouring deck cannot put a lip or wall through a surface lane.

        Protect only nearby, parallel traffic lanes at the same level. A real
        upper crossing with headroom keeps its complete deck, as does this
        deck's connected ground approach.
        """
        import roads,roadmesh
        line=np.asarray(line,float);rows=dict(self.mainline_plans);rows.update(self.upper_plans)
        if len(line)<2:return []
        low=line[:,:2].min(0)-width;high=line[:,:2].max(0)+width;out=[]
        axis=line[-1,:2]-line[0,:2];axis/=max(np.linalg.norm(axis),1e-9)
        for key,p in rows.items():
            sp=self.floor_specs.get(key)
            if sp is None or sp.profile.highway.removesuffix('_link') not in ('motorway','trunk'):continue
            if (np.asarray(p.bbox[2:])<low).any() or (np.asarray(p.bbox[:2])>high).any():continue
            if np.linalg.norm(p.xy[[0,-1],None,:]-line[None,[0,-1],:2],axis=2).min()<2.5:continue
            drive=roads.offset_polyline(np.c_[p.xy,np.zeros(len(p.xy))],sp.profile.offset)[:,:2] if sp.profile.offset else p.xy
            a,b=drive[:-1],drive[1:]
            keep=(np.maximum(a,b)>=low).all(1)&(np.minimum(a,b)<=high).all(1)
            ids=np.flatnonzero(keep)
            if not len(ids):continue
            mid=(a[ids]+b[ids])/2;direction=b[ids]-a[ids]
            direction/=np.maximum(np.linalg.norm(direction,axis=1),1e-9)[:,None]
            distance,at,s=project(mid,line[:,:2])
            _,pa,ps=project(mid,p.xy);height=np.interp(pa,ps,p.z)
            la,lo,_=self.frame.enu_to_geodetic(mid[:,0],mid[:,1],0.)
            height=self.frame.geodetic_to_enu(la,lo,height+.04)[2]
            use=(abs(direction@axis)>.85)&(distance<width/2+sp.profile.drive/2+.1)&(abs(height-np.interp(at,s,line[:,2]))<3.)
            if not use.any():continue
            normal=roadmesh._normals(drive)*(sp.profile.drive/2+.04)
            left,right=drive+normal,drive-normal
            for k in ids[use]:out.append(np.array([left[k],right[k],right[k+1],left[k+1]]).tolist())
        return out

    def surface_heights(self, xy, lift=.04):
        import terrain_surface
        if not len(xy):return np.empty(0)
        def elevation(la,lo):
            x,y,_=self.frame.geodetic_to_enu(la,lo,0.);q=np.c_[x,y]
            mask,z=self.surface(q)
            if not mask.all():z[~mask]=self.sample(q[~mask])
            return self.interfaces(q,z+lift,lift)
        return terrain_surface.heights(self.frame,elevation,np.asarray(xy)[:,:2])
