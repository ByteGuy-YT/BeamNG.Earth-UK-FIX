"""Physical geometry contracts across regions; no screenshot-site overrides."""
import sys,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
import roads,roadmesh,ukroadside,roadprofile,grading
import cdae
from test_uk_roads import uk,FRAME
from test_grading import FakeMD

class Geometry(unittest.TestCase):
    def test_surface_branch_joins_interior_bridge_connector_height(self):
        from test_roads import features,rules,FRAME as F
        f=features([[(-50,0),(0,0)],[(0,0),(50,0)],[(0,0),(0,200)],[(25,-200),(25,200)]],
                   ['primary','primary','secondary','secondary'],flags=[(0,'is_bridge'),(1,'is_bridge')],
                   ids=['left','right','branch','under'])
        f.rules['connectors']=rules([(0,'a',0,0),(0,'j',1,1),(1,'j',0,0),(1,'b',1,1),
                                     (2,'j',0,0),(2,'c',1,1)],'text')
        flat=lambda la,lo:np.full(np.shape(la),10.)
        g=grading.Grader(F,FakeMD(f),flat);parts=g.bridge_model.parts([f],(-200,-200,200,200))
        bridge=next(p for p in parts if p[0]=='right');la,lo,_=F.enu_to_geodetic(0.,0.,0.)
        ground=float(g.apply(la,lo,flat(la,lo)))
        deck=float(F.enu_to_geodetic(bridge[2][0,0],bridge[2][0,1],bridge[3][0])[2])
        self.assertAlmostEqual(ground,deck,delta=.05)

    def test_adjacent_deck_edge_overlap_is_not_a_stacked_road(self):
        x=np.arange(0.,401.,4.)
        lines=[np.c_[x,np.zeros(len(x))],np.c_[x,np.full(len(x),10.)]]
        self.assertEqual(roads._deck_stacks(lines,[1.,2.],[13.,13.]),[])
        z=roads.deck_profile(lines,lambda q:np.full(len(q),10.),levels=[1.,2.],widths=[13.,13.])
        self.assertLess(max(v.max() for v in z),11.)
        # An actual parallel double deck is still separated.
        stacked=[lines[0],lines[1]-[0.,10.]]
        self.assertTrue(roads._deck_stacks(stacked,[1.,2.],[13.,13.]))

    def test_motorway_keeps_rolling_profile_beyond_short_underpass(self):
        f=uk(lines=[[(-3000,0),(-25,0)],[(-25,0),(25,0)],[(25,0),(3000,0)],[(0,-300),(0,300)]],
             classes=['motorway']*3+['secondary'],
             tags=[{'highway':'motorway','oneway':'yes'},
                   {'highway':'motorway','oneway':'yes','bridge':'yes'},
                   {'highway':'motorway','oneway':'yes'},{'highway':'secondary'}])
        def rolling(la,lo):
            x,y,_=FRAME.geodetic_to_enu(la,lo,0.)
            return 100.+.01*x+5.*np.sin(x/400.)
        g=grading.Grader(FRAME,FakeMD(f),rolling)
        x=np.r_[np.arange(-2800.,-100.,20.),np.arange(100.,2800.,20.)]
        la,lo,_=FRAME.enu_to_geodetic(x,np.zeros(len(x)),0.)
        z=g.apply(la,lo,rolling(la,lo))
        np.testing.assert_allclose(z,rolling(la,lo),atol=.15,err_msg='abutment height must not replace the natural mainline grade')

    def test_layer_change_at_merge_across_short_intermediate_segment(self):
        # The crossing arms connect through a third source segment. It is a
        # near-junction overlap, not an additional storey of road.
        lines=[np.array([[-50.,0.],[0.,0.]]),np.array([[0.,0.],[20.,20.]]),
               np.array([[20.,20.],[-30.,-20.]])]
        lines=[roads.densify(p,2.) for p in lines]
        z=roads.deck_profile(lines,lambda q:np.full(len(q),10.),levels=[1.,1.,2.],widths=[4.5]*3)
        self.assertLess(max(v.max() for v in z),11.)
        self.assertAlmostEqual(z[0][-1],z[1][0])
        self.assertAlmostEqual(z[1][-1],z[2][0])

    def test_bridge_clearance_and_upper_approaches_share_one_solution(self):
        from test_roads import features,FRAME as F
        f=features([[(-400,0),(-25,0)],[(-25,0),(25,0)],[(25,0),(400,0)],[(0,-400),(0,400)]],
                   ['motorway']*3+['secondary'],flags=[(1,'is_bridge')],ids=['a','bridge','b','under'])
        flat=lambda la,lo:np.full(np.shape(la),10.)
        g=grading.Grader(F,FakeMD(f),flat);bp=g.bridge_model
        parts=bp.parts([f],(-500,-500,500,500));self.assertTrue(parts)
        bridge=parts[0];s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(bridge[2],axis=0),axis=1))]
        self.assertGreaterEqual(np.interp(s[-1]/2,s,bridge[3]),10.+roads.DECK_ROAD_CLEAR-.01)
        la,lo,_=F.enu_to_geodetic(np.array([-25.,25.,0.]),np.array([0.,0.,50.]),0.)
        z=g.apply(la,lo,flat(la,lo))
        np.testing.assert_allclose(z[:2],bridge[3][[0,-1]],atol=.02)
        self.assertAlmostEqual(z[2],10.,delta=.02,msg='lower route stays on its own profile')

    def test_mapped_expressway_lanes_do_not_turn_shoulders_into_travel_lanes(self):
        import json,navgraph
        from test_roads import features,FRAME as F
        f=features([[(0,0),(200,0)]],['motorway'],ids=['main'])
        f.attrs['osm_tags']=np.array([json.dumps({'highway':'motorway','oneway':'yes','lanes':'2',
                                                 'shoulder:left:width':'1','shoulder:right:width':'2.5'})])
        sp=roads.road_specs(f)[0]
        self.assertEqual(sp.lanes,(2,0));self.assertIsNone(sp.profile)
        self.assertAlmostEqual(navgraph.driving_width(sp),7.2)
        self.assertAlmostEqual(sp.width,10.7)
        extras=roads.extras(sp,np.array([[0.,0.,0.],[200.,0.,0.]]),-71.)
        self.assertEqual(sum(look['m']=='line_dashed_long' for look,_,_ in extras),1)
        graph=navgraph.build(F,[f],lambda la,lo:np.zeros(np.shape(la)),(100,0),window=300)
        self.assertTrue(graph['edges'])
        self.assertTrue(all(e[3:5]==[2,0] for e in graph['edges']))
        f.attrs['osm_tags']=np.array([json.dumps({'highway':'motorway','oneway':'yes','lanes':'2','width':'30.5'})])
        sp=roads.mapped_lanes(f,[roads.Spec(30.5,'paved',False,'motorway',True,dir=1)])[0]
        self.assertLess(sp.width,12.,'an implausible imported width cannot make a two-lane ramp thirty metres wide')

    def test_curved_surface_ribbons_follow_terrain_between_their_vertices(self):
        import terrain_surface
        from test_plazas import FRAME as F
        def elev(la,lo):
            x,y,_=F.geodetic_to_enu(la,lo,0.)
            return 4.+.5*np.sin(x*.7)*np.cos(y*.8)
        chunks=[{'n':[[1.,1.,0.],[12.,8.,0.],[21.,4.,0.]],'w':7.,'m':'road_asphalt_2lane','tl':10.}]
        p,t,uv,_,_=roadmesh.build(F,chunks,elev,(0,0,0),lift=.01)
        for weights in ([.2,.3,.5],[.6,.2,.2]):
            q=(p[t]*np.array(weights)[None,:,None]).sum(1)
            ground=terrain_surface.heights(F,elev,q[:,:2])
            np.testing.assert_allclose(q[:,2]-ground,.01,atol=1e-7)
        self.assertTrue(np.isfinite(uv).all())
        self.assertTrue(((uv[:,0]>=-1e-8)&(uv[:,0]<=1.00000001)).all())
        self.assertLess(len(p),2000,'bounded shared grid vertices, not unbounded subdivision')

    def test_coincident_unconnected_bridge_ends_do_not_become_a_junction(self):
        a=roads.RouteLine([[0.,0.],[100.,0.]],('A','upper'))
        b=roads.RouteLine([[100.,0.],[100.,100.]],('lower','B'))
        nodes,edges,_=roads._chain_graph([a,b])
        self.assertNotEqual(edges[0][1],edges[1][0])
        z=roads._join_decks([a,b],[np.array([10.,10.]),np.array([0.,0.])])
        self.assertEqual(z[0][-1],10.)
        self.assertEqual(z[1][0],0.)

    def test_connector_inside_long_bridge_splits_the_height_graph(self):
        from test_roads import features,rules,FRAME as F
        f=features([[(0,0),(500,0)],[(250,0),(250,250)]],['motorway','motorway'],
                   flags=[(0,'is_bridge'),(1,'is_bridge')],ids=['main','ramp'])
        f.rules['connectors']=rules([(0,'A',0.,0.),(0,'J',.5,.5),(0,'B',1.,1.),(1,'J',0.,0.),(1,'C',1.,1.)])
        bp=roads.BridgeProfiles(F,lambda k:f,lambda la,lo:np.full(np.shape(la),10.))
        got=bp.parts([f],(-20,-20,520,270))
        self.assertEqual(len(got),3,'mainline split at the real interior routing junction')
        lines=[v[1] for v in bp.done.values()];_,edges,_=roads._chain_graph(lines)
        degrees={}
        for a,b,_ in edges:
            for node in (a,b):degrees[node]=degrees.get(node,0)+1
        self.assertIn(3,degrees.values())

    def test_parking_pavement_conforms_to_terrain_triangles_between_vertices(self):
        import plazas,terrain_surface
        from test_plazas import FRAME as F,ring
        poly=ring([(1,1),(39,3),(37,36),(2,31)])
        def elev(la,lo):
            x,y,_=F.geodetic_to_enu(la,lo,0.)
            return 3.+.3*np.sin(x*.7)*np.cos(y*.8)
        p,t,*_=plazas.mesh(F,(0,0,256,256),[poly],elev,(0,0,0),terrain=True,lift=.02)
        pts=(p[t]*np.array([.2,.3,.5])[None,:,None]).sum(1)
        ground=terrain_surface.heights(F,elev,pts[:,:2])
        np.testing.assert_allclose(pts[:,2]-ground,.02,atol=.00001)
        self.assertLess(len(p),1600,'bounded grid and clipped boundary, not indiscriminate fine subdivision')

    def test_flat_city_tunnel_is_underground_and_internal_join_is_not_a_portal(self):
        from test_roads import features,FRAME as F
        f=features([[(0,0),(500,0)],[(500,0),(1000,0)]],['motorway','motorway'],
                   flags=[(0,'is_tunnel'),(1,'is_tunnel')],ids=['a','b'])
        flat=lambda la,lo:np.full(np.shape(la),10.)
        g=grading.Grader(F,FakeMD(f),flat);tp=g.tunnel_model
        whole=roads.BridgeProfiles.parts(tp,[f],(-20,-20,1020,20))
        self.assertEqual(len(whole),2)
        a,b=whole
        self.assertAlmostEqual(a[3][-1],b[3][0],places=5)
        self.assertLess(a[3][-1],10.-roads.TUNNEL_COVER+.1)
        self.assertTrue(tp.parts([f],(-20,-20,1020,20)),'a physical tunnel, not a road painted on top')
        sections=g._tunnel_sections(f)
        self.assertTrue(any(kind==2 for *_,kind in sections))
        for fid,sp,xy,z,kind in sections:
            if kind and np.linalg.norm(xy[-1]-[500.,0.])<.1:self.assertFalse(tp.mouth(fid)[1])
            if kind and np.linalg.norm(xy[0]-[500.,0.])<.1:self.assertFalse(tp.mouth(fid)[0])
        mouths=g._mouth_plans(sections)
        self.assertFalse(any(np.min(np.linalg.norm(p.xy-[500.,0.],axis=1))<20. for _,p in mouths),
                         'internal segment joins do not excavate a false entrance through a surface road or car park')
        for fid,sp,xy,z,kind in sections:
            if kind==2:self.assertLess(z.min(),3.)
        import navgraph
        floors={}
        for (fid,_),(_,xy,z,_) in tp.done.items():floors.setdefault(fid,[]).append((xy,z))
        graph=navgraph.build(F,[f],flat,(500.,0.),window=1200.,tunnel_floors=floors)
        self.assertTrue(graph['edges'],'a mapped tunnel remains a connected AI road')
        self.assertLess(min(v[2] for v in graph['nodes'].values()),3.,'AI follows the physical tunnel floor')

    def test_surface_street_keeps_its_grading_and_lift_over_an_underground_join(self):
        from test_roads import features,FRAME as F
        f=features([[(0,0),(500,0)],[(500,0),(1000,0)],[(500,-100),(500,100)]],
                   ['motorway','motorway','residential'],flags=[(0,'is_tunnel'),(1,'is_tunnel')],ids=['a','b','surface'])
        flat=lambda la,lo:np.full(np.shape(la),10.)
        g=grading.Grader(F,FakeMD(f),flat)
        la,lo,_=F.enu_to_geodetic(np.array([498.,500.,502.]),np.zeros(3),0.)
        z=g.apply(la,lo,flat(la,lo),grading.ROAD_LIFT)
        np.testing.assert_allclose(z,10.+grading.ROAD_LIFT,atol=.002,
                                   err_msg='surface road above a tunnel must not lose its road height or fall into a false portal')

    def test_bridge_profile_has_no_vertical_drop_after_clearance_clamping(self):
        x=np.arange(0.,401.,4.);lines=[np.c_[x,np.zeros(len(x))]]
        z=np.minimum(20.,np.minimum(x*.2,(400-x)*.2));z[-2]=20.
        out=roads._limit_deck_grades(lines,[z],.08)[0]
        self.assertLessEqual(np.abs(np.diff(out)/np.diff(x)).max(),.080001)
        self.assertAlmostEqual(out[0],0.)
        self.assertAlmostEqual(out[-1],0.)

    def test_bridge_fork_keeps_one_height_after_independent_clearance_smoothing(self):
        x=np.arange(0.,201.,4.)
        lines=[np.c_[x,np.zeros(len(x))],np.c_[200.+x,x*.2],np.c_[200.+x,-x*.2]]
        zs=[np.linspace(10.,23.,len(x)),np.linspace(15.,10.,len(x)),np.linspace(18.,12.,len(x))]
        joined=roads._join_decks(lines,zs)
        self.assertAlmostEqual(joined[0][-1],joined[1][0],places=9)
        self.assertAlmostEqual(joined[0][-1],joined[2][0],places=9)
        for before,after in zip(zs,joined):self.assertTrue((after>=before-1e-9).all(),'preserve required clearance')
        self.assertEqual(joined[0][0],10.)
        self.assertEqual(joined[1][-1],10.)
        self.assertLess(np.abs(np.diff(joined[1])/np.diff(x)).max(),.13,'spread correction instead of a vertex spike')

    def test_layer_change_at_bridge_junction_is_not_a_stacked_overpass(self):
        x=np.arange(0.,201.,4.)
        lines=[np.c_[x,np.zeros(len(x))],np.c_[200.+x,x*.2]]
        zs=roads.deck_profile(lines,lambda q:np.full(len(q),10.),levels=[1.,2.],widths=[12.,8.])
        self.assertAlmostEqual(zs[0][-1],zs[1][0],places=9)
        self.assertLess(max(z.max() for z in zs),11.,'no fictitious extra deck clearance at an actual connection')

    def test_curved_bridge_uses_identical_edges_at_tile_cut(self):
        t=np.linspace(-.9,.9,80);pts=np.c_[200*np.sin(t),200*np.cos(t),20.+t]
        sp=roads.Spec(14.,'paved',False,'primary')
        decks=[('curve',sp,pts,0.)]
        left=[c for c in roads._deck_chunks(decks,(-256,0,0,256)) if c.get('deck') and not c.get('ctx')]
        right=[c for c in roads._deck_chunks(decks,(0,0,256,256)) if c.get('deck') and not c.get('ctx')]
        a=roadmesh.ribbons(left)[-1];b=roadmesh.ribbons(right)[0]
        for side in (0,1):np.testing.assert_allclose(a[side][-1],b[side][0],atol=.002)

    def test_dense_interchange_has_bounded_engine_meshes_without_losing_triangles(self):
        n=70002;p=np.c_[np.arange(n),np.arange(n)%3,np.zeros(n)]
        t=np.arange(n).reshape(-1,3);uv=p[:,:2];m=np.zeros(len(t),int)
        mesh=(p,t,uv,['road_asphalt_2lane'],m)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'dense.cdae';roadmesh.write(str(path),mesh);s=cdae.read(path)
        self.assertGreater(len(s['meshes']),1)
        self.assertEqual(sum(x['indices'][0]//3 for x in s['meshes']),len(t))
        self.assertTrue(all(x['verts'][0]<=60000 for x in s['meshes']))
        self.assertEqual(s['objects'][0],len(s['meshes']))
        self.assertEqual(s['details'][0],1)
    def test_simplification_keeps_vertical_curve_on_straight_bridge(self):
        x=np.arange(-300.,301.,4.);p=np.c_[x,x*.27,20.+3*np.cos(x/95.)]
        q=roads.simplify(p)
        np.testing.assert_allclose(np.interp(x,q[:,0],q[:,2]),p[:,2],atol=.026)

    def test_ribbon_keeps_sharp_source_corner(self):
        p=np.array([[0.,0.,20.],[1.,0.,21.],[1.,1.,22.],[10.,1.,23.]])
        xy,s,z=roadmesh._resample(p,2.)
        for pt in p:self.assertLess(np.linalg.norm(np.c_[xy,z]-pt,axis=1).min(),1e-8)

    def test_wall_does_not_cross_parallel_road_at_other_height(self):
        x=np.arange(0.,101.,2.);xy=np.c_[x,np.zeros(len(x))];z=np.full(len(x),10.)
        sp=roads.Spec(6.,'paved',False,'secondary');other=np.array([[0.,7.,14.],[100.,7.,14.]])
        keep=roads.retaining_clear('low',xy,z,np.tile([0.,1.],(len(x),1)),4.,np.full(len(x),17.),np.ones(len(x),bool),[('high',sp,other,0.)])
        self.assertFalse(keep.any())

    def test_wall_preserves_vertically_separate_road(self):
        x=np.arange(0.,101.,2.);xy=np.c_[x,np.zeros(len(x))]
        sp=roads.Spec(6.,'paved',False,'secondary');other=np.array([[0.,7.,30.],[100.,7.,30.]])
        keep=roads.retaining_clear('low',xy,np.full(len(x),10.),np.tile([0.,1.],(len(x),1)),4.,np.full(len(x),17.),np.ones(len(x),bool),[('high',sp,other,0.)])
        self.assertTrue(keep.all())

    def test_oneway_street_estimate_is_not_only_a_narrow_traffic_lane(self):
        for cls in ('residential','tertiary','secondary'):
            sp=roads.road_specs(uk(classes=[cls],tags=[{'highway':cls,'oneway':'yes'}]))[0]
            self.assertGreaterEqual(sp.width,4.)
        sp=roads.road_specs(uk(classes=['residential'],tags=[{'highway':'residential','oneway':'yes','width':'2.8'}]))[0]
        self.assertAlmostEqual(sp.width,2.8)

    def test_single_lane_roundabout_has_turning_width(self):
        sp=roads.road_specs(uk(tags=[{'highway':'secondary','junction':'roundabout','lanes':'1'}]))[0]
        self.assertGreaterEqual(sp.width,4.5)

    def test_lower_surface_road_is_not_dug_to_fit_an_underestimated_bridge(self):
        f=uk(lines=[[(-150,0),(-25,0)],[(-25,0),(25,0)],[(25,0),(150,0)],[(0,-150),(0,150)]],
             tags=[{'highway':'secondary'},{'highway':'secondary','bridge':'yes'},{'highway':'secondary'},{'highway':'tertiary'}])
        flat=lambda la,lo:np.full(np.shape(la),20.)
        g=grading.Grader(FRAME,FakeMD(f),flat)
        la,lo,_=FRAME.enu_to_geodetic(np.zeros(51),np.linspace(-100,100,51),0.)
        z=g.apply(la,lo,flat(la,lo))
        self.assertGreater(z.min(),19.5)

    def test_mapped_half_gantry_cannot_leave_opposite_panels_floating(self):
        from test_motorway_round3 import Motorway
        rr=Motorway().corridors()
        ll=[]
        for y in (0.,22.):
            la,lo,_=FRAME.enu_to_geodetic(0.,y,0.);ll.append([lo,la])
        records=[('g','gantry',{},np.array(ll))]
        with patch.object(ukroadside.ukcontext,'near',return_value=records):
            cc=ukroadside.chunks(FRAME,rr,(-100,-100,100,100),lambda la,lo:np.zeros(np.shape(la)))
        beams=[c['box3d'] for c in cc if c['m']=='uk_metal' and c['box3d'][4]==.55]
        self.assertEqual(len(beams),1)
        p,u,L,_,_=beams[0];p=np.array(p[:2]);u=np.array(u)
        for c in cc:
            if c['m']=='uk_black':self.assertLess(abs((np.array(c['box3d'][0][:2])-p)@u)+.45,L/2)

if __name__=='__main__':unittest.main()
