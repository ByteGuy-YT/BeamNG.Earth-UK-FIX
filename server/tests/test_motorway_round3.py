"""Motorway profiles, cross-tile furniture and circular signal junctions."""
import unittest
from unittest.mock import patch
import numpy as np
import sys
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
import roads,grading,roadmesh,ukroadside,islands
from test_uk_roads import FRAME,uk
from test_grading import FakeMD

flat=lambda la,lo:np.full(np.shape(la),20.)

class Motorway(unittest.TestCase):
    def test_overpass_clears_motorway_without_lowering_its_profile(self):
        f=uk(lines=[[(-200,0),(-25,0)],[(-25,0),(25,0)],[(25,0),(200,0)],[(0,-300),(0,300)]],
             classes=['secondary']*3+['motorway'],tags=[{'highway':'secondary'},
             {'highway':'secondary','bridge':'yes'},{'highway':'secondary'},
             {'highway':'motorway','oneway':'yes','lanes':'4'}])
        g=grading.Grader(FRAME,FakeMD(f),flat)
        y=np.arange(-200.,201.,4.);la,lo,_=FRAME.enu_to_geodetic(np.zeros(len(y)),y,0.)
        z=g.apply(la,lo,flat(la,lo))
        self.assertLess(np.max(np.abs(z-20.)),.05)
        bp=roads.BridgeProfiles(FRAME,lambda _:f,lambda la,lo:g.apply(la,lo,flat(la,lo),.04));bp.vertical=g.uk_vertical
        deck=bp.parts([f],(-100,-100,100,100))[0]
        self.assertGreater(deck[3].min(),27.4)
        model=g.uk_vertical
        cached=model.cell('regression-cell')
        self.assertIn('regression-cell',model.cache)
        self.assertIs(cached,model.cell('regression-cell'))

    def corridors(self):
        f=uk(lines=[[(-400,10),(400,10)],[(400,-10),(-400,-10)]],classes=['motorway']*2,
             tags=[{'highway':'motorway','oneway':'yes','lanes':'4','shoulder':'yes'}]*2)
        rr=[]
        for fid,sp,xy in zip(('a','b'),roads.road_specs(f),(np.array([[-400.,10.,100.],[400.,10.,108.]]),np.array([[400.,-10.,108.],[-400.,-10.,100.]]))):
            rr.append((fid,sp,roads.offset_polyline(xy,sp.profile.surface_offset),0.))
        return rr

    def test_surface_shift_keeps_shoulder_outside_driving_corridor(self):
        rr=self.corridors()
        for _,sp,line,_ in rr:
            centre=roads.offset_polyline(line,sp.profile.offset)
            expected=10. if line[-1,0]>line[0,0] else -10.
            np.testing.assert_allclose(centre[:,1],expected,atol=.001)

    def test_divider_continuous_across_tiles_and_uses_road_height(self):
        rr=self.corridors();parts=[]
        with patch.object(ukroadside.ukcontext,'near',return_value=()):
            for bounds in ((-256.,-128.,0.,128.),(0.,-128.,256.,128.)):
                cc=ukroadside.chunks(FRAME,rr,bounds,flat)
                parts.extend(c for c in cc if c['m']=='bne_bridge_concrete')
        spans=[]
        for c in parts:
            p,u,L,w,h=c['box3d'];spans.append((p[0]-L/2,p[0]+L/2))
            self.assertGreater(p[2],99.) # never the excavated terrain's 20 m floor
            self.assertAlmostEqual(c['rise'],u[0]*(L-.015)*.01,places=4)
        spans.sort();self.assertLessEqual(spans[0][0],-256.);self.assertGreaterEqual(spans[-1][1],256.)
        self.assertTrue(all(b[0]<=a[1]+.02 for a,b in zip(spans,spans[1:])))
        mesh=roadmesh.build(FRAME,parts,flat,(0,0,0));self.assertTrue(np.isfinite(mesh[0]).all())

    def test_divider_survives_reversed_centimetre_seam_at_lane_split(self):
        rr=self.corridors();fid,sp,line,lon=rr.pop(0)
        # Different source IDs at the split must not change physical ownership.
        rr.extend([('z',sp,np.array([line[0],[0.,line[0,1],104.]]),lon),
                   ('a',sp,np.array([[0.,line[0,1],104.],[-.03,line[0,1],104.],line[-1]]),lon)])
        with patch.object(ukroadside.ukcontext,'near',return_value=()):
            cc=ukroadside.chunks(FRAME,rr,(-128.,-128.,128.,128.),flat)
        spans=[]
        for c in cc:
            if c['m']=='bne_bridge_concrete':
                p,u,L,*_=c['box3d'];spans.append((p[0]-L/2,p[0]+L/2))
        spans.sort();self.assertTrue(spans)
        self.assertTrue(all(b[0]<=a[1]+.02 for a,b in zip(spans,spans[1:])))

    def test_cameras_across_tile_boundary_build_one_gantry(self):
        rr=self.corridors();records=[]
        for oid,x,y in (('n1',-1.,10.),('n2',1.,-10.)):
            la,lo,_=FRAME.enu_to_geodetic(x,y,0.);records.append((oid,'speed_camera',{},np.array([[lo,la]])))
        count=0
        with patch.object(ukroadside.ukcontext,'near',return_value=records):
            for bounds in ((-256.,-128.,0.,128.),(0.,-128.,256.,128.)):
                cc=ukroadside.chunks(FRAME,rr,bounds,flat)
                count+=sum(c['m']=='uk_yellow' for c in cc)
        self.assertEqual(count,1)

class Circular(unittest.TestCase):
    def fixture(self,two_way=False):
        lines=[];tags=[]
        for j in range(8):
            theta=np.linspace(j*np.pi/4,(j+1)*np.pi/4,8)
            line=np.c_[90*np.cos(theta),60*np.sin(theta)]
            if j%2:line=line[::-1]
            lines.append(line.tolist());t={'highway':'primary','junction':'circular','lanes':'2'}
            if j==2:t['bridge']='yes'
            if two_way:t['oneway']='no'
            tags.append(t)
        return uk(lines=lines,tags=tags)

    def test_closed_signal_circular_is_clockwise_including_bridge_and_reversed_ways(self):
        f=self.fixture();rs=roads.road_specs(f);bs=roads.bridge_specs(f)
        for i,sp in enumerate(rs):
            sp=sp or bs[i];self.assertTrue(sp.oneway)
            ll=f.parts(i)[0][0];x,y,_=FRAME.geodetic_to_enu(ll[:,1],ll[:,0],0.)
            cross=(x[:-1]*np.diff(y)-y[:-1]*np.diff(x)).sum()*sp.dir
            self.assertLess(cross,0.)
            self.assertEqual(min(sp.profile.forward,sp.profile.backward),0)

    def test_explicit_two_way_circular_is_preserved(self):
        f=self.fixture(True)
        self.assertTrue(all(not sp.oneway for sp in roads.road_specs(f) if sp))

if __name__=='__main__':unittest.main()
