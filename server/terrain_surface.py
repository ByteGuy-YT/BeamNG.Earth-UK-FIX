"""Sample the triangulated two-metre terrain, rather than a different smooth surface."""
import numpy as np

STEP=2.


def clip_triangles(xy,tris,attributes,materials):
    """Cut draped triangles at terrain grid edges, carrying their UVs and lift.

    Merely sampling ribbon edges still crosses the terrain's diagonals. On a
    curved cutting that made even a two-metre road triangle go through the
    ground. Batched polygon clipping follows the actual planes, without adding
    scene objects or repeatedly sampling the DEM for each triangle.
    """
    xy=np.asarray(xy,float);tris=np.asarray(tris,int);attributes=np.asarray(attributes,float)
    vertices=[];faces=[];mats=[];nv=0
    for begin in range(0,len(tris),2048):
        tri=tris[begin:begin+2048];pts=xy[tri]
        lo=np.floor(pts.min(1)/STEP).astype(int)
        hi=np.maximum(lo+1,np.ceil((pts.max(1)-1e-9)/STEP).astype(int))
        size=hi-lo;count=size.prod(1);owner=np.repeat(np.arange(len(tri)),count)
        start=np.repeat(np.r_[0,np.cumsum(count)[:-1]],count)
        at=np.arange(len(owner))-start
        cell=lo[owner]+np.c_[at%size[owner,0],at//size[owner,0]]
        data=np.concatenate([pts,attributes[tri]],axis=2)[owner]
        width=data.shape[2];p=np.zeros((len(data),9,width));p[:,:3]=data;n=np.full(len(p),3,int)
        def cut(p,n,normal,limit):
            index=np.arange(p.shape[1])[None];valid=index<n[:,None]
            prev=p[np.arange(len(p))[:,None],np.where(index==0,n[:,None]-1,index-1)]
            d=(p[:,:,:2]*normal[:,None,:]).sum(2)-limit[:,None]
            dp=(prev[:,:,:2]*normal[:,None,:]).sum(2)-limit[:,None]
            inside=(d>=-1e-9)&valid;cross=((d>=-1e-9)!=(dp>=-1e-9))&valid
            total=inside.astype(int)+cross;dest=np.cumsum(total,axis=1)-total
            out=np.zeros_like(p);row,col=np.nonzero(cross)
            t=dp[row,col]/(dp[row,col]-d[row,col])
            out[row,dest[row,col]]=prev[row,col]+t[:,None]*(p[row,col]-prev[row,col])
            row,col=np.nonzero(inside);out[row,dest[row,col]+cross[row,col]]=p[row,col]
            return out,total.sum(1)
        low=cell*STEP;high=low+STEP
        for normal,limit in (([1,0],low[:,0]),([-1,0],-high[:,0]),([0,1],low[:,1]),([0,-1],-high[:,1])):
            p,n=cut(p,n,np.broadcast_to(normal,(len(p),2)),limit)
        normal=np.c_[np.ones(len(p)),np.where(cell.sum(1)%2==0,-1.,1.)]
        limit=(low*normal).sum(1)+np.where(cell.sum(1)%2==0,0.,STEP)
        for sign in (1.,-1.):
            q,nn=cut(p,n,normal*sign,limit*sign)
            keep=nn>=3;q=q[keep];nn=nn[keep];mm=np.asarray(materials)[begin:begin+len(tri)][owner[keep]]
            if not len(q):continue
            offsets=np.r_[0,np.cumsum(nn)[:-1]];valid=np.arange(9)[None]<nn[:,None]
            v=q[valid];ts=[];ms=[]
            for j in range(1,int(nn.max())-1):
                good=nn>j+1;ix=offsets[good]
                t=np.c_[ix,ix+j,ix+j+1];a=v[t[:,1],:2]-v[t[:,0],:2];b=v[t[:,2],:2]-v[t[:,0],:2]
                nonzero=np.abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])>1e-10
                ts.append(t[nonzero]+nv);ms.append(mm[good][nonzero])
            vertices.append(v);faces.extend(ts);mats.extend(ms);nv+=len(v)
    if not vertices:return xy[:0],np.empty((0,3),int),attributes[:0],np.empty(0,int)
    data=np.concatenate(vertices);t=np.concatenate(faces);m=np.concatenate(mats)
    unique,inv=np.unique(np.round(data,9),axis=0,return_inverse=True)
    return unique[:,:2],inv[t],unique[:,2:],m

def heights(frame,elev,xy):
    xy=np.asarray(xy,float)
    ij=np.floor(xy/STEP).astype(np.int64);ab=xy/STEP-ij
    corners=np.concatenate([ij,ij+[1,0],ij+[0,1],ij+[1,1]])
    unique,inv=np.unique(corners,axis=0,return_inverse=True)
    la,lo,_=frame.enu_to_geodetic(unique[:,0]*STEP,unique[:,1]*STEP,0.)
    _,_,z=frame.geodetic_to_enu(la,lo,np.asarray(elev(la,lo),float))
    z00,z10,z01,z11=np.asarray(z)[inv].reshape(4,len(xy))
    a,b=ab.T
    z45=np.where(a>=b,z00+a*(z10-z00)+b*(z11-z10),z00+a*(z11-z01)+b*(z01-z00))
    z135=np.where(a+b<=1,z00+a*(z10-z00)+b*(z01-z00),z11+(1-a)*(z01-z11)+(1-b)*(z10-z11))
    return np.where((ij.sum(1)%2)==0,z45,z135)
