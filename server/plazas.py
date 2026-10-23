"""Squares and pedestrian areas as a paved mesh (the user's report #45, Fells Point 2026-10-17: "Paived or brick
terrain that isnt roads are too organic and blurry"; Broadway Square on Mapillary: crisp red brick pavers round its
pavilion, where the terrain showed the aerial photo's blur).

Each Overture land_use polygon of subtype "pedestrian" (surface.PLAZA_CLASSES) is triangulated, its triangles split
until no edge is longer than STEP_M (earthfast.subdivide_tris, Rust) so it follows the graded ground, and draped
LIFT_M over it with the brick pavers tiled in world metres. A road tile gets the triangles whose centre lies in it
(no overlap between tiles). Render only (the terrain under it collides); the road mesh draws over it (a road's lift
is higher). Pure given its inputs (elev)."""
import numpy as np

STEP_M = 2.0            # m: the longest edge after subdivision (the physics block's 2 m lattice)
LIFT_M = 0.04           # m over the graded ground (under the road mesh's asphalt: detail mode lifts it 0.05)
BRICK = "bne_sidewalk_brick"    # red brick pavers in herringbone (buildings.materials.json; sidewalks.BRICK)
BRICK_REPEAT_M = 1.2    # m per repeat (sidewalks.BRICK_REPEAT_M)
MIN_AREA_M2 = 60.0      # smaller polygons are left to the terrain


def _subdivide(pts, tris, step):
    import fast
    if fast.AVAILABLE and hasattr(fast._ef, "subdivide_tris"):
        P, T = fast._ef.subdivide_tris(np.ascontiguousarray(pts, np.float64), np.ascontiguousarray(tris, np.int64),
                                       float(step))
        return np.asarray(P), np.asarray(T)
    P = [tuple(p) for p in np.asarray(pts, np.float64)]
    mids, out, stack = {}, [], [tuple(t) for t in np.asarray(tris)[::-1]]
    while stack:
        t = stack.pop()
        e = [np.hypot(P[t[i]][0] - P[t[(i + 1) % 3]][0], P[t[i]][1] - P[t[(i + 1) % 3]][1]) for i in range(3)]
        k = int(np.argmax(e))
        if e[k] <= step:
            out.append(t)
            continue
        a, b, c = t[k], t[(k + 1) % 3], t[(k + 2) % 3]
        key = (min(a, b), max(a, b))
        if key not in mids:
            P.append(((P[a][0] + P[b][0]) / 2, (P[a][1] + P[b][1]) / 2))
            mids[key] = len(P) - 1
        stack.append((mids[key], b, c))
        stack.append((a, mids[key], c))
    return np.array(P), np.array(out, np.int64)


def polygons(feats_list):
    """The outer rings (lon/lat (k, 2)) of the squares and pedestrian areas among the land_use Features."""
    import surface
    out = []
    for f in feats_list:
        if f is None or len(f) == 0:
            continue
        m = surface._plazas(f)
        if m is None:
            continue
        for i in np.flatnonzero(m):
            for part in f.parts(i):
                if len(part) and len(part[0]) >= 4:
                    out.append(np.asarray(part[0], np.float64))
    return out


def mesh(frame, box, rings, elev, origin, material=BRICK, step=STEP_M, lift=LIFT_M, terrain=False):
    """The paved mesh of the plaza rings (lon/lat) in the tile box (x0, y0, x1, y1) of the anchor frame:
    (positions relative to origin (k, 3), tris, uvs, [material], tri material index) or None. elev(lat, lon) -> m
    (the graded ground the physics block has)."""
    import buildings
    x0, y0, x1, y1 = box
    Ps, Ts, n0 = [], [], 0
    for ring in rings:
        e, n, _ = frame.geodetic_to_enu(ring[:, 1], ring[:, 0], 0.0)
        xy = np.stack([np.asarray(e), np.asarray(n)], 1)
        if np.hypot(*(xy[0] - xy[-1])) < 1e-6:
            xy = xy[:-1]
        if (xy[:, 0].max() < x0 or xy[:, 0].min() > x1 or xy[:, 1].max() < y0 or xy[:, 1].min() > y1
                or len(xy) < 3):
            continue
        area2 = buildings._area2(xy)
        if abs(area2) / 2 < MIN_AREA_M2:
            continue
        if area2 < 0:
            xy = xy[::-1]
        tris = np.asarray(buildings.triangulate(xy), np.int64).reshape(-1, 3)
        if not len(tris):
            continue
        P, T = _terrain_clip(xy,tris,box) if terrain else _subdivide(xy, tris, step)
        if not len(T):continue
        c = P[T].mean(1)
        keep = (c[:, 0] >= x0) & (c[:, 0] < x1) & (c[:, 1] >= y0) & (c[:, 1] < y1)
        if not keep.any():
            continue
        T = T[keep]
        used = np.unique(T)
        remap = np.full(len(P), -1, np.int64)
        remap[used] = np.arange(len(used))
        Ps.append(P[used])
        Ts.append(remap[T] + n0)
        n0 += len(used)
    if not Ps:
        return None
    P = np.concatenate(Ps)
    T = np.concatenate(Ts)
    if terrain:
        import terrain_surface
        z=terrain_surface.heights(frame,elev,P)
    else:
        la, lo, _ = frame.enu_to_geodetic(P[:, 0], P[:, 1], np.zeros(len(P)))
        h = np.asarray(elev(la, lo), np.float64)
        _, _, z = frame.geodetic_to_enu(la, lo, h)
    V = np.c_[P, np.asarray(z) + lift] - np.asarray(origin, np.float64)
    UV = P / BRICK_REPEAT_M
    return V, T, UV, [material], np.zeros(len(T), np.int64)


def _terrain_clip(xy,tris,box):
    """Paving cut against the same triangles as the collision/visible terrain.

    Interior cells are batched; only polygon boundaries require clipping. This
    avoids an independent four-metre triangulation tearing through the ground
    in parking lots, without adding another scene object for each grid cell.
    """
    from polygon import Path
    import farfield
    sp=2.;x0,y0,x1,y1=box
    lo=np.maximum(np.floor(xy.min(0)/sp).astype(int),np.floor(np.array([x0,y0])/sp).astype(int))
    hi=np.minimum(np.ceil(xy.max(0)/sp).astype(int),np.ceil(np.array([x1,y1])/sp).astype(int))
    if (hi<=lo).any():return np.empty((0,2)),np.empty((0,3),int)
    nx,ny=hi-lo;xx,yy=np.meshgrid(np.arange(lo[0],hi[0]),np.arange(lo[1],hi[1]))
    cells=np.c_[xx.ravel(),yy.ravel()];boundary=np.zeros((ny,nx),bool)
    for a,b in zip(xy,np.roll(xy,-1,axis=0)):
        count=max(1,int(np.ceil(np.linalg.norm(b-a)/sp*2)))
        samples=np.floor((a+np.linspace(0,1,count+1)[:,None]*(b-a))/sp).astype(int)-lo
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                ix=samples[:,0]+dx;iy=samples[:,1]+dy
                good=(ix>=0)&(ix<nx)&(iy>=0)&(iy<ny);boundary[iy[good],ix[good]]=True
    inner=Path(xy).contains_points((cells+.5)*sp)&~boundary.ravel()
    vertices=[];faces=[];nv=0
    def add(poly):
        nonlocal nv
        if len(poly)<3:return
        p=np.asarray(poly,float)
        t=np.array([(0,j,j+1) for j in range(1,len(p)-1)],int)
        a=p[t[:,1]]-p[t[:,0]];b=p[t[:,2]]-p[t[:,0]]
        t=t[np.abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])>1e-10]
        if len(t):vertices.append(p);faces.append(t+nv);nv+=len(p)
    if inner.any():
        c=cells[inner];p=np.stack([c,c+[1,0],c+[0,1],c+[1,1]],1)*sp
        even=(c.sum(1)%2)==0
        t=np.where(even[:,None,None],np.array([[0,1,3],[0,3,2]]),np.array([[0,1,2],[1,3,2]]))
        vertices.append(p.reshape(-1,2));faces.append((t+np.arange(len(c))[:,None,None]*4).reshape(-1,3));nv=4*len(c)
    src=xy[tris];src_lo=src.min(1);src_hi=src.max(1)
    def cut(poly,n,limit):
        if len(poly)<3:return []
        out=[];prev=poly[-1];pd=float(prev@n-limit)
        for cur in poly:
            cd=float(cur@n-limit)
            if (cd>=-1e-10)!=(pd>=-1e-10):out.append(prev+(cur-prev)*(pd/(pd-cd)))
            if cd>=-1e-10:out.append(cur)
            prev,pd=cur,cd
        return out
    for cell in cells[boundary.ravel()]:
        low=cell*sp;high=low+sp
        for k in np.flatnonzero((src_hi>=low).all(1)&(src_lo<=high).all(1)):
            p=list(src[k])
            for n,d in (([1,0],low[0]),([-1,0],-high[0]),([0,1],low[1]),([0,-1],-high[1])):
                p=cut(p,np.asarray(n),d)
                if len(p)<3:break
            if len(p)<3:continue
            normal=np.array([1.,-1.]) if cell.sum()%2==0 else np.array([1.,1.])
            limit=float(low@normal)+(0. if cell.sum()%2==0 else sp)
            add(cut(p,normal,limit));add(cut(p,-normal,-limit))
    if not faces:return np.empty((0,2)),np.empty((0,3),int)
    p=np.concatenate(vertices);t=np.concatenate(faces)
    # Canonical boundary coordinates ensure neighbouring road tiles share it.
    unique,inv=np.unique(np.round(p,9),axis=0,return_inverse=True)
    return unique,inv[t]


def merge(a, b):
    """Two meshes (positions, tris, uvs, materials, tri material index; either None) as one."""
    if a is None:
        return b
    if b is None:
        return a
    Pa, Ta, UVa, Ma, Ia = a
    Pb, Tb, UVb, Mb, Ib = b
    mats = list(Ma)
    idx = []
    for m in Mb:
        if m not in mats:
            mats.append(m)
        idx.append(mats.index(m))
    return (np.concatenate([Pa, Pb]), np.concatenate([Ta, np.asarray(Tb) + len(Pa)]), np.concatenate([UVa, UVb]),
            mats, np.concatenate([Ia, np.asarray(idx, np.int64)[np.asarray(Ib)]]))
