"""Mapped UK details: sizing, evidence, directional cameras and bounded geometry."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import numpy as np

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
import buildings as bld
import furniture
import navgraph
import osm_enrich
import roads
import ukcontext
from test_buildings import rect
from test_uk_roads import FRAME,uk


def ll(x,y):
    la,lo,_=FRAME.enu_to_geodetic(x,y,0.)
    return np.array([lo,la])


class Cameras(unittest.TestCase):
    def road(self,oneway=False):
        t={'highway':'primary','maxspeed':'30 mph'}
        if oneway:t['oneway']='yes'
        sp=roads.road_specs(uk(tags=[t]))[0]
        return [('r',sp,np.array([[0.,0.,20.],[200.,0.,20.]]),-1.8)]
    def test_relation_direction_and_mph_reach_the_stock_trigger_contract(self):
        records=[('n1','speed_camera',{'_from':ll(10,0).tolist(),'maxspeed':'30 mph'},np.array([ll(100,0)]))]
        row=ukcontext.cameras(FRAME,records,self.road(),(-20,-20,220,20))[0]
        self.assertAlmostEqual(row['limit'],13.4112)
        np.testing.assert_allclose(row['dir'],[1,0],atol=.001)
        self.assertGreater(row['pos'][1],3.25+.6)
    def test_unknown_two_way_direction_is_visual_only(self):
        r=[('n1','speed_camera',{'direction':'90','maxspeed':'30 mph'},np.array([ll(100,0)]))]
        self.assertIsNone(ukcontext.cameras(FRAME,r,self.road(),(0,-20,200,20))[0]['limit'])
    def test_unambiguous_oneway_can_use_mapped_road_limit(self):
        r=[('n1','speed_camera',{},np.array([ll(100,0)]))]
        self.assertAlmostEqual(ukcontext.cameras(FRAME,r,self.road(True),(0,-20,200,20))[0]['limit'],13.4112)
    def test_conditional_camera_does_not_enforce_a_guessed_schedule(self):
        r=[('n1','speed_camera',{'maxspeed:conditional':'20 @ (08:00-09:00)'},np.array([ll(100,0)]))]
        self.assertIsNone(ukcontext.cameras(FRAME,r,self.road(True),(0,-20,200,20))[0]['limit'])
    def test_motorway_trigger_excludes_shoulder(self):
        sp=roads.road_specs(uk(classes=['motorway'],tags=[{'highway':'motorway','lanes':'4','maxspeed':'70 mph'}]))[0]
        line=[('m',sp,np.array([[0.,0.,20.],[200.,0.,20.]]),-1.8)]
        r=[('n1','speed_camera',{},np.array([ll(100,0)]))]
        c=ukcontext.cameras(FRAME,r,line,(0,-20,200,20))[0]
        self.assertAlmostEqual(c['width'],14.6)
        self.assertAlmostEqual(c['point'][1],sp.profile.offset,delta=.001)
        c=ukcontext.cameras(FRAME,r,line,(0,-20,200,20),surface_centres=False)[0]
        self.assertAlmostEqual(c['point'][1],0.,delta=.001)


class Appearance(unittest.TestCase):
    def test_school_use_changes_no_dimensions(self):
        s=bld.plan(rect(0,0,30,18),{'class':'school','height':9.,'num_floors':3,'roof_shape':'flat'},lat=53.34,lon=-1.8)
        before=copy.deepcopy(s)
        ring=np.array([ll(-10,-10),ll(40,-10),ll(40,30),ll(-10,30),ll(-10,-10)])
        with patch.object(ukcontext,'near',return_value=(('w1','school',{},ring),)):
            ukcontext.decorate_buildings(FRAME,(0,0,256,256),[(s,10.,10.)])
        self.assertEqual(s.uk_use,'school')
        np.testing.assert_array_equal(s.ring,before.ring)
        self.assertEqual((s.height,s.floors,s.floor_h,s.roof),(before.height,before.floors,before.floor_h,before.roof))
        mesh=bld.build([(s,10.,10.)])
        self.assertIn(bld.MATERIALS.index(bld.SCHOOL),mesh[3])
        self.assertTrue(np.isfinite(mesh[0]).all())
    def test_neighbour_of_school_is_not_reclassified(self):
        ring=np.array([ll(0,0),ll(20,0),ll(20,20),ll(0,20),ll(0,0)])
        records=(('w1','school',{},ring),)
        self.assertIsNone(ukcontext.building_use(FRAME,rect(30,0,10,10),0,0,records))
        self.assertEqual(ukcontext.building_use(FRAME,rect(2,2,10,10),0,0,records),'school')
    def test_fuel_canopy_preserves_bounds_and_remains_open_for_driving(self):
        s=bld.plan(rect(0,0,20,10),{'class':'roof','height':4.,'roof_shape':'flat'},lat=53.34,lon=-1.8)
        s.uk_use='fuel'
        mesh=bld.build([(s,10.,10.)]);col=bld.collision_mesh([(s,10.,10.)])
        for m in (mesh,col):
            self.assertTrue(np.isfinite(m[0]).all())
            self.assertGreaterEqual(m[0][:,0].min(),0.)
            self.assertLessEqual(m[0][:,0].max(),20.)
            self.assertGreaterEqual(m[0][:,1].min(),0.)
            self.assertLessEqual(m[0][:,1].max(),10.)
        self.assertEqual(bld.collider_boxes([(s,10.,10.)],0,0),[])
        low=col[0][col[0][:,2]<13.]
        self.assertFalse(((low[:,0]>1)&(low[:,0]<19)&(low[:,1]>1)&(low[:,1]<9)).any())
    def test_mapped_postbox_and_bus_stop_are_tile_owned(self):
        records=(('n1','post_box',{},np.array([ll(100,7)])),('n2','bus_stop',{},np.array([ll(110,8)])))
        line=Cameras().road()
        flat=lambda la,lo:np.full(np.shape(la),20.)
        with patch.object(ukcontext,'near',return_value=records):
            rows=ukcontext.street_props(FRAME,(0,0,200,100),line,flat)
            none=ukcontext.street_props(FRAME,(200,0,400,100),line,flat)
        self.assertEqual({r[0] for r in rows},{'ukpostbox','ukbus_stop'})
        self.assertEqual(none,[])


class Controls(unittest.TestCase):
    def test_mid_block_mapped_signal_splits_into_a_controlled_two_arm_node(self):
        f=uk(lines=[[(0,0),(400,0)]],tags=[{}])
        p=ll(200,0)
        tags={'highway':'primary','_nodes':[{'highway':'traffic_signals','lon':p[0],'lat':p[1]}]}
        f.attrs['osm_tags']=np.array([json.dumps(tags)])
        segments=osm_enrich.control_sections([(0.,1.,tags)],np.asarray(f.parts(0)[0][0]))
        self.assertEqual(len(segments),2)
        divided=osm_enrich.split_features(f,{0:segments})
        graph=navgraph.build(FRAME,[divided],lambda la,lo:np.full(np.shape(la),20.),(200,0),left_hand=True)
        self.assertEqual(len(graph['signals']),1)
        self.assertEqual(len(graph['signals'][0]['app']),2)
    def test_approach_node_keeps_its_existing_junction_instead_of_a_second_controller(self):
        f=uk(lines=[[(0,0),(400,0)]])
        p=ll(375,0);tags={'_nodes':[{'highway':'traffic_signals','lon':p[0],'lat':p[1]}]}
        segments=osm_enrich.control_sections([(0.,1.,tags)],np.asarray(f.parts(0)[0][0]))
        self.assertEqual(len(segments),1)
    def test_same_limit_source_split_does_not_create_repeat_entries(self):
        sp=roads.road_specs(uk(tags=[{'maxspeed':'30 mph'}]))[0]
        lines=[('a',sp,np.array([[0.,0.,0.],[200.,0.,0.]]),0),
               ('b',sp,np.array([[200.,0.,0.],[400.,0.,0.]]),0)]
        rows=furniture.speed_signs(lines,{'a':30.,'b':30.},(-20,-20,420,20),True)
        self.assertEqual(len(rows),2)
        self.assertTrue(all(r[1]<50 or r[1]>350 for r in rows))
    def test_mapped_setback_and_reversed_control_direction(self):
        p=ll(170,0)
        tags={'highway':'primary','_nodes':[{'lon':p[0],'lat':p[1],'highway':'traffic_signals','traffic_signals:direction':'forward'}]}
        sp=roads.road_specs(uk(tags=[tags]))[0]
        self.assertEqual(sp.profile.controls,('','traffic_signals'))
        self.assertAlmostEqual(sp.profile.control_setbacks[1],30.,delta=.1)
        rt=osm_enrich.reverse_tags(tags)
        self.assertEqual(rt['_nodes'][0]['traffic_signals:direction'],'backward')
        self.assertEqual(tags['_nodes'][0]['traffic_signals:direction'],'forward')
    def test_one_mapped_central_signal_controls_all_incoming_arms(self):
        p=ll(0,0)
        marked=roads.road_specs(uk(tags=[{'_nodes':[{'lon':p[0],'lat':p[1],'highway':'traffic_signals'}]}]))[0]
        plain=roads.road_specs(uk())[0]
        arms=[(str(i),marked if i==0 else plain,np.array(u,float),np.zeros(3),True,100.)
              for i,u in enumerate(((1,0),(0,1),(-1,0),(0,-1)))]
        self.assertEqual(len(furniture.junction_controls(arms,None)),4)
        for arm in arms:
            q,_=furniture.control_transform(arm,arms,True,[(3.25,np.array([np.zeros(2),a[2]*80])) for a in arms])
            self.assertGreater(np.linalg.norm(q),4.)
    def test_national_limit_uses_nsl_face(self):
        sp=roads.road_specs(uk(tags=[{'maxspeed':'GB:nsl_single'}]))[0]
        rows=furniture.speed_signs([('r',sp,np.array([[0.,0.,0.],[300.,0.,0.]]),0)],{'r':60},(-10,-10,320,10),True)
        self.assertTrue(rows)
        self.assertEqual({r[0] for r in rows},{'uknsl'})


class AssetBudget(unittest.TestCase):
    def test_original_models_have_bounded_geometry_and_valid_material_bindings(self):
        root=Path(__file__).resolve().parents[2]/'mod/beamng_earth/levels/beamng_earth/art/shapes/beamngEarth/uk_street'
        counts=json.loads((root/'asset-budget.json').read_text())
        self.assertLessEqual(max(counts.values()),120)
        for name,count in counts.items():
            xml=ET.parse(root/(name+'.dae'));ns={'c':'http://www.collada.org/2005/11/COLLADASchema'}
            tris=xml.findall('.//c:triangles',ns)
            self.assertEqual(sum(int(t.get('count')) for t in tris),count)
            bound={t.get('symbol') for t in xml.findall('.//c:instance_material',ns)}
            self.assertTrue(all(t.get('material') in bound for t in tris))


class LocalIndex(unittest.TestCase):
    def test_spatial_index_decodes_geometry_and_filters_kinds(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'context.sqlite';db=sqlite3.connect(path)
            db.executescript('CREATE TABLE features(id INTEGER PRIMARY KEY,osm_id TEXT,kind TEXT,tags TEXT,geometry TEXT);'
                             'CREATE VIRTUAL TABLE bounds USING rtree(id,minx,maxx,miny,maxy);')
            for i,(x,k) in enumerate(((0.,'school'),(1.,'speed_camera'),(20.,'school')),1):
                db.execute('INSERT INTO features VALUES(?,?,?,?,?)',(i,'n'+str(i),k,'{}',json.dumps([[x,0.]])))
                db.execute('INSERT INTO bounds VALUES(?,?,?,?,?)',(i,x,x,0.,0.))
            db.commit();db.close()
            ukcontext.features.cache_clear()
            try:
                with patch.dict(os.environ,{'BEAMNG_EARTH_UK_CONTEXT_DB':str(path)}):
                    records=ukcontext.features((-2.,-2.,2.,2.),('speed_camera',))
                    self.assertEqual(len(records),1)
                    np.testing.assert_array_equal(records[0][3],[[1.,0.]])
            finally:
                if getattr(ukcontext._local,'db',None):ukcontext._local.db.close()
                ukcontext._local.db=None;ukcontext._local.path=None;ukcontext.features.cache_clear()


if __name__=='__main__':unittest.main()
