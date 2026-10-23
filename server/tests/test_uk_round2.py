"""Regression cases for all systemic causes in compressedImages(2)."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
import grading,navgraph,roadmesh,roads,ukvertical,ukcontext,ukroadside,parking,buildings
from test_uk_roads import FRAME,uk
from test_grading import FakeMD
from test_buildings import rect

flat=lambda la,lo:np.full(np.shape(la),20.)

class Structures(unittest.TestCase):
    def fixture(self):
        f=uk(lines=[[(-200,0),(-25,0)],[(-25,0),(25,0)],[(25,0),(200,0)],[(0,-150),(0,150)]],
             classes=['secondary']*3+['motorway'],tags=[{'highway':'secondary','lanes':'2'},
             {'highway':'secondary','lanes':'2','bridge':'yes'},
             {'highway':'secondary','lanes':'2'},{'highway':'motorway','lanes':'3','oneway':'yes'}])
        return f,grading.Grader(FRAME,FakeMD(f),flat)
    def test_upper_profile_ignores_local_dem_trench(self):
        xy=np.c_[np.linspace(-25,25,20),np.zeros(20)]
        sample=lambda q:20.+.01*q[:,0]-8*np.exp(-(q[:,0]/8)**2)
        z=ukvertical.approach_profile(xy,sample)
        self.assertLess(np.max(np.abs(np.diff(z)/np.diff(xy[:,0]))),.02)
        self.assertGreater(z.min(),19.5)
    def test_lower_road_grade_preserved_and_upper_approach_meets_deck(self):
        f,g=self.fixture()
        x=np.array([-70.,-25.,0.,25.,70.]);la,lo,_=FRAME.enu_to_geodetic(x,np.zeros(5),0.)
        h=g.apply(la,lo,flat(la,lo))
        self.assertGreater(h[0],20.);self.assertLess(h[0],h[1])
        self.assertAlmostEqual(h[2],20.,delta=.05)
        b=roads.BridgeProfiles(FRAME,lambda _:f,lambda la,lo:g.apply(la,lo,flat(la,lo),.04));b.vertical=g.uk_vertical
        deck=b.parts([f],(-100,-100,100,100))[0]
        self.assertLess(np.ptp(deck[3]),.05)
        self.assertAlmostEqual(h[1]+.04,deck[3][0],delta=.03)
        self.assertAlmostEqual(h[-2]+.04,deck[3][-1],delta=.03)
    def test_entire_deck_width_clear_of_terrain(self):
        f,g=self.fixture()
        half=roads.bridge_specs(f)[1].width/2
        X,Y=np.meshgrid(np.arange(-16,17,4.),np.linspace(-half,half,9));xy=np.c_[X.ravel(),Y.ravel()]
        g._cell_plans(__import__('mapcells').cell_of(FRAME.lat0,FRAME.lon0))
        out=g.uk_vertical.excavate(xy,np.full(len(xy),25.),0.)
        top=min(r[1].min() for r in g.uk_vertical.near(xy))
        self.assertLessEqual(out.max(),top-2.7)
    def test_mapped_ground_section_overrides_generic_positive_layer(self):
        f=uk(tags=[{'highway':'motorway','lanes':'4'}]);f.attrs['osm_match']=np.array(['matched'])
        import mapgeom
        f.rules['level']=mapgeom.rule_table([(0,1.,[0.,1.])],'float')
        with patch.object(ukcontext,'features',return_value=()):self.assertEqual(roads.level_ranges(f,0),[])
    def test_path_subway_creates_only_short_upper_span(self):
        f=uk(lines=[[(-200,0),(200,0)]],tags=[{'highway':'trunk'}])
        ll=f.parts(0)[0][0]
        la,lo,_=FRAME.enu_to_geodetic(np.array([0.,0.]),np.array([-30.,30.]),0.)
        rec=(('w1','underpass',{'tunnel':'yes','highway':'footway'},np.c_[lo,la]),)
        with patch.object(ukcontext,'features',return_value=rec):r=ukvertical.underpass_ranges(np.asarray(ll),{'highway':'trunk'})
        self.assertEqual(len(r),1);self.assertAlmostEqual((r[0][1]-r[0][0])*400,10.,delta=.2)
    def test_multiple_subways_sorted_and_ground_between_them_retained(self):
        f=uk(lines=[[(-200,0),(200,0)]],tags=[{'highway':'trunk'}]);f.attrs['osm_match']=np.array(['matched'])
        rec=[]
        for x in (120.,-120.,0.):
            la,lo,_=FRAME.enu_to_geodetic(np.array([x,x]),np.array([-30.,30.]),0.)
            rec.append((str(x),'underpass',{'tunnel':'yes','highway':'footway'},np.c_[lo,la]))
        with patch.object(ukcontext,'features',return_value=tuple(rec)):
            self.assertEqual(len(roads.bridge_parts(f,0)),3)
            self.assertEqual(len(roads.ground_parts(f,0)),4)
            r=roads.level_ranges(f,0);self.assertEqual(r,sorted(r))
    def test_same_road_id_two_spans_selects_the_physical_span(self):
        model=ukvertical.Model(FRAME,None,None)
        a=np.array([[0.,0.],[10.,0.]]);b=a+[100.,0.]
        rows=[(a,np.array([20.,20.]),3.,'same'),(b,np.array([70.,70.]),3.,'same')]
        with patch.object(model,'near',return_value=rows):
            np.testing.assert_allclose(model.deck('same',b),[70.,70.])
    def test_priority_approach_does_not_raise_lower_road_beside_it(self):
        low=grading.Plan(np.array([[-100.,0.],[100.,0.]]),np.array([10.,10.]),8.)
        upper=grading.Plan(np.array([[-50.,8.],[50.,8.]]),np.array([18.,18.]),4.)
        xy=np.array([[0.,0.],[0.,8.]])
        weight=ukvertical.approach_ownership(xy,[low,upper],[upper])
        np.testing.assert_allclose(weight,[0.,1.])
    def test_lower_cut_crosses_source_seams_without_steep_pit(self):
        f=uk(lines=[[(-100,0),(-25,0)],[(-25,0),(25,0)],[(25,0),(100,0)],
                    [(0,-300),(0,-20)],[(0,-20),(0,20)],[(0,20),(0,300)]],
             classes=['secondary']*3+['motorway']*3,
             tags=[{'highway':'secondary'},
                   {'highway':'secondary','bridge':'yes'},
                   {'highway':'secondary'}]+[{'highway':'motorway','oneway':'yes'}]*3)
        g=grading.Grader(FRAME,FakeMD(f),flat)
        y=np.arange(-200.,201.,2.);x=np.zeros(len(y));la,lo,_=FRAME.enu_to_geodetic(x,y,0.)
        z=g.apply(la,lo,flat(la,lo))
        self.assertLess(np.max(np.abs(np.diff(z))/2.),.051)
        self.assertAlmostEqual(z[len(y)//2],20.,delta=.05)
    def test_slip_road_underpass_is_also_separated(self):
        ll=np.array([[-1.,53.],[-.999,53.]])
        rec=(('w1','underpass',{'tunnel':'yes'},np.array([[-.9995,52.9999],[-.9995,53.0001]])),)
        with patch.object(ukcontext,'features',return_value=rec):
            self.assertEqual(len(ukvertical.underpass_ranges(ll,{'highway':'trunk_link'})),1)

class StreetDetails(unittest.TestCase):
    def test_destination_arrays_recover_slip_lane_count(self):
        f=uk(tags=[{'highway':'motorway_link','oneway':'yes','destination:lanes':'A610|M1'}],classes=['motorway'])
        p=roads.road_specs(f)[0].profile
        self.assertEqual((p.forward,p.backward),(2,0))
    def test_pole_base_samples_own_location_on_slope(self):
        from test_uk_street_details import Controls
        # An ordinary mapped multi-arm junction, with an along-road elevation change.
        f=uk(lines=[[(-100,0),(0,0)],[(0,0),(100,0)],[(0,-100),(0,0)]],tags=[{'highway':'primary','_control':'traffic_signals'}]*3)
        from test_roads import rules
        f.rules['connectors']=rules([(0,'c',1,1),(1,'c',0,0),(2,'c',1,1)],'text')
        def hill(la,lo):
            x,y,_=FRAME.geodetic_to_enu(la,lo,0.);return 20.+x*.1+y*.05
        g=navgraph.build(FRAME,[f],hill,(0,0),left_hand=True)
        self.assertTrue(g['signals'])
        for j in g['signals']:
            for a in j['app']:self.assertAlmostEqual(a[9],20.+a[7]*.1+a[8]*.05+a[12],delta=.02)
    def test_supermarket_appearance_does_not_resize_building(self):
        s=buildings.plan(rect(0,0,80,50),{'class':'retail','height':8.,'roof_shape':'flat'},lat=53.34,lon=-1.8)
        la,lo,_=FRAME.enu_to_geodetic(np.array([-2,82,82,-2,-2]),np.array([-2,-2,52,52,-2]),0.)
        r=(('w1','supermarket',{'brand':'Morrisons'},np.c_[lo,la]),)
        old=s.ring.copy();height=s.height
        with patch.object(ukcontext,'near',return_value=r):ukcontext.decorate_buildings(FRAME,(0,0,256,256),[(s,20.,20.)])
        self.assertEqual((s.uk_use,s.uk_brand),('supermarket','morrisons'));np.testing.assert_array_equal(old,s.ring);self.assertEqual(s.height,height)
        mesh=buildings.build([(s,20.,20.)]);self.assertIn(buildings.MATERIALS.index(buildings.MORRISONS),mesh[3])
    def test_parking_has_visible_asphalt_and_bay_paint(self):
        ring=rect(0,0,100,100)
        with patch.object(parking,'context_rings',return_value=[ring]):
            mesh=parking.render_lots(None,FRAME,(0,0,256,256),None,flat,(0,0,0),[[20,20,20,90,1]],[],[])
        self.assertIn('road_asphalt_2lane',mesh[3]);self.assertIn('line_white',mesh[3]);self.assertTrue(np.isfinite(mesh[0]).all())
    def test_gantry_and_median_in_combined_mesh(self):
        f=uk(lines=[[(-100,-12),(100,-12)],[(100,12),(-100,12)]],classes=['motorway']*2,
             tags=[{'highway':'motorway','oneway':'yes','lanes':'3'}]*2)
        rs=roads.road_specs(f);rr=[('a',rs[0],np.array([[-100.,-12,20],[100.,-12,20]]),0),('b',rs[1],np.array([[100.,12,20],[-100.,12,20]]),0)]
        la,lo,_=FRAME.enu_to_geodetic(0.,-12.,0.)
        records=(('n1','speed_camera',{},np.array([[lo,la]])),)
        with patch.object(ukcontext,'near',return_value=records):ch=ukroadside.chunks(FRAME,rr,(-128,-128,128,128),flat)
        self.assertTrue(any(c['m']=='uk_yellow' for c in ch));self.assertTrue(any(c['m']=='bne_bridge_concrete' for c in ch))
        m=roadmesh.build(FRAME,ch,flat,(0,0,0));self.assertTrue(np.isfinite(m[0]).all());self.assertLess(len(m[1]),2000)

if __name__=='__main__':unittest.main()
