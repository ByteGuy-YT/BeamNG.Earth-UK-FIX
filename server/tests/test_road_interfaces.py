"""Road approaches must stay driveable across data splits and terrain cells."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
import roads,grading,roadmesh,ukcontext,ukvertical,terrain_surface
from test_uk_roads import FRAME,uk
from test_grading import FakeMD

class Interfaces(unittest.TestCase):
 def test_short_ground_source_peak_is_limited_through_shared_nodes(self):
  lines=[roads.RouteLine(np.array([[0.,0.],[16.,0.]]),('A','J')),
         roads.RouteLine(np.array([[16.,0.],[176.,0.]]),('J','B'))]
  _,edges,z=ukvertical.ground_endpoint_envelope(lines,[[24.,18.],[18.,20.]],[.08,.08])
  self.assertAlmostEqual(z[edges[0][0]],19.28)
  self.assertEqual(z[edges[0][1]],18.)
  for a,b,s in edges:self.assertLessEqual(abs(z[b]-z[a]),.08*s[-1]+1e-9)
  # A road crossing at the same coordinates but with separate routing IDs
  # must not become a connection to that low floor.
  separate=roads.RouteLine(np.array([[0.,0.],[16.,0.]]),('upperA','upperB'))
  _,ee,zz=ukvertical.ground_endpoint_envelope([*lines,separate],[[24.,18.],[18.,20.],[40.,40.]],[.08,.08,.08])
  np.testing.assert_allclose(zz[list(ee[-1][:2])],40.)

 def test_grade_envelope_recovers_abutment_trench_from_approach_trend(self):
  line=roads.RouteLine(np.array([[0.,0.],[16.,0.]]),('A','B'))
  _,_,z=ukvertical.ground_endpoint_envelope([line],[[15.,20.]],[.08],[(np.array([0.,0.]),'A',20.)])
  np.testing.assert_allclose(z,20.)

 def test_road_collision_uses_one_grid_without_losing_surface_planes(self):
  def raw(la,lo):
   x,y,_=FRAME.geodetic_to_enu(la,lo,0.)
   return 20.+.15*np.sin(x/8.)+.1*np.cos(y/7.)
  class Surface:
   def surface_heights(self,xy):return terrain_surface.heights(FRAME,raw,xy)
  floor=roadmesh.road_surface(np.array([[0.,0.,0.],[200.,40.,0.]]),24.,Surface())
  p,t,_=map(np.asarray,floor['join_mesh'])
  self.assertLess(len(t),4000,'a 200 m road must not overlay several redundant collision grids')
  # Every resulting triangle lies in the same terrain plane, including its
  # interior. Fewer triangles must not bridge over a dip or remove collision.
  centre=p[t].mean(1)
  np.testing.assert_allclose(centre[:,2],Surface().surface_heights(centre[:,:2]),atol=2e-7)
  physical=roadmesh.deck([floor],np.zeros(3))
  self.assertEqual(len(physical[1]),len(t))

 def test_bridge_lattice_guard_keeps_neighbouring_fill_out_of_lane_edge(self):
  from types import SimpleNamespace
  m=ukvertical.Model(FRAME,None,None)
  own=grading.Plan(np.array([[0.,0.],[40.,0.]]),np.array([20.,20.]),7.,('J','B'),(False,True))
  neighbour=grading.Plan(np.array([[-20.,8.],[40.,8.]]),np.array([20.4,20.4]),7.)
  for key,p in (('own',own),('other',neighbour)):
   m.mainline_plans[(key,)]=p
   m.plan_specs[p]=SimpleNamespace(profile=SimpleNamespace(highway='motorway'),width=12.)
  mask,z=m.surface(np.array([[-.3,5.],[0.,5.],[.3,5.]]))
  self.assertTrue(mask.all());np.testing.assert_allclose(z,20.,atol=1e-9)

 def test_distant_bridge_does_not_raise_a_flat_surface_junction(self):
  f=uk(lines=[[(-300,0),(-5,0)],[(-5,0),(5,0)],[(5,0),(180,0)],[(180,0),(300,0)],[(180,0),(180,100)],[(0,-100),(0,100)]],
       classes=['primary']*5+['secondary'],
       tags=[{'highway':'primary'},{'highway':'primary','bridge':'yes'},{'highway':'primary'},
             {'highway':'primary'},{'highway':'primary'},{'highway':'secondary'}])
  raw=lambda la,lo:np.full(np.shape(la),20.)
  g=grading.Grader(FRAME,FakeMD(f),raw)
  la,lo,_=FRAME.enu_to_geodetic(np.array([180.,180.,190.]),np.array([0.,10.,0.]),0.)
  z=g.apply(la,lo,raw(la,lo))
  np.testing.assert_allclose(z,20.,atol=.03)

 def test_bridge_seam_repair_keeps_a_valid_approach_grade(self):
  model=ukvertical.Model(FRAME,None,None)
  p=grading.Plan(np.array([[-60.,0.],[0.,0.]]),np.array([16.,20.]),5.,('A','J'))
  # A tiny connector has a steep numerical slope, while the deck beyond it
  # is level. Neither is permission to bend the resolved approach upward.
  line=roads.RouteLine(np.array([[0.,0.],[.0001,0.],[8.,0.],[30.,0.]]),('J','B'))
  bridge=(line,np.array([20.,20.000008,20.,20.]),5.,'bridge')
  q=np.c_[np.linspace(-40.,0.,161),np.zeros(161)]
  natural=20.+q[:,0]/15.
  actual=model.road_interfaces(q,natural,p,[bridge])
  np.testing.assert_allclose(actual,natural,atol=1e-9)
  with patch.object(model,'near',return_value=[bridge]):
   floor=model.road_heights(q,p)
  self.assertLess((abs(np.diff(floor))/.25).max(),.067)
  self.assertLess(floor.max(),20.041)

 def test_join_repairs_transverse_residual_without_rebending_approach(self):
  class Floor:
   def approach_heights(self,xy,line,end):return 20.+.06*xy[:,0]+.01*xy[:,1]
   def protected_mainlines(self,line,end):return []
  line=np.array([[-20.,0.,18.8],[0.,0.,20.]])
  ch=roadmesh.bridge_join(FRAME,line,10.,-1,lambda la,lo:la*0,(-100,-100,100,100),vertical=Floor())
  pp=np.asarray(ch['join_mesh'][0]);seam=pp[abs(pp[:,0])<1e-8]
  np.testing.assert_allclose(seam[:,2],20.,atol=1e-8)
  centre=pp[(abs(pp[:,1])<1e-8)&(pp[:,0]>=0)]
  np.testing.assert_allclose(centre[:,2],20.+.06*centre[:,0],atol=1e-8)

 def test_sloping_approach_meets_an_angled_abutment_across_both_lanes(self):
  model=ukvertical.Model(FRAME,None,None)
  plan=grading.Plan(np.array([[-40.,0.],[0.,0.]]),np.array([18.4,20.]),6.,('A','J'))
  line=roads.RouteLine(np.array([[0.,0.],[20.,10.]]),('J','B'))
  normal=np.array([-1.,2.])/np.sqrt(5.)
  xy=np.linspace(-5.,5.,21)[:,None]*normal
  # Include the approach's endpoint extrapolation, as the actual mesh does.
  base=20.+.04*xy[:,0]
  z=model.road_interfaces(xy,base,plan,[(line,np.array([20.,20.]),6.,'deck')])
  np.testing.assert_allclose(z,20.,atol=1e-9)

 def test_submillimetre_source_segment_cannot_reverse_offset_approach(self):
  xy=np.array([[0.,0.,20.],[.00025,.00043,20.00001],[1.,1.72,20.04],[20.,34.7,20.8]])
  shifted=roads.offset_polyline(xy,1.4)
  self.assertGreater(float((shifted[1,:2]-shifted[0,:2])@(xy[1,:2]-xy[0,:2])),0.)
  model=ukvertical.Model(FRAME,None,None);model.pavements['bridge']=(6.,1.4)
  line=roads.RouteLine(xy[:,:2],('J','B'))
  plan=grading.Plan(np.array([[-30.,-52.],[0.,0.]])+shifted[0,:2],np.array([19.,20.]),7.,('A','J'))
  q=shifted[0,:2]+np.linspace(0.,20.,81)[:,None]*np.array([-1.,-1.72])/np.hypot(1.,1.72)
  z=model.road_interfaces(q,np.full(len(q),20.),plan,[(line,xy[:,2],8.,'bridge')])
  self.assertLess(abs(np.diff(z)).max(),.03)

 def test_ground_roads_share_one_junction_floor_and_keep_an_upper_storey(self):
  model=ukvertical.Model(FRAME,None,None)
  a=grading.Plan(np.array([[-40.,0.],[0.,0.]]),np.array([20.,20.]),6.,('A','J'))
  b=grading.Plan(np.array([[0.,0.],[0.,40.]]),np.array([20.4,20.4]),6.,('J','B'))
  upper=grading.Plan(np.array([[-40.,0.],[40.,0.]]),np.array([28.,28.]),6.)
  model.mainline_plans.update({('a',):a,('b',):b,('upper',):upper})
  from types import SimpleNamespace
  for p in (a,b):model.plan_specs[p]=SimpleNamespace(profile=SimpleNamespace(mainline=False,highway='primary'),width=12.)
  q=np.array([[-2.,0.],[0.,0.],[2.,0.],[0.,2.]])
  np.testing.assert_allclose(model.road_heights(q,a),model.road_heights(q,b),atol=1e-8)
  self.assertGreater((model.road_heights(q,upper)-model.road_heights(q,a)).min(),7.4)

 def test_corridor_projection_culling_matches_full_projection(self):
  rng=np.random.default_rng(32);x=np.arange(0.,1000.,2.);line=np.c_[x,10*np.sin(x/70)]
  q=np.c_[rng.uniform(0.,1000.,400),rng.uniform(-20.,20.,400)]
  full=ukvertical.project(q,line);culled=ukvertical.project(q,line,reach=6.)
  keep=full[0]<6.
  np.testing.assert_allclose(culled[0][keep],full[0][keep],atol=1e-10)
  np.testing.assert_allclose(culled[1][keep],full[1][keep],atol=1e-10)
  np.testing.assert_allclose(culled[2],full[2],atol=1e-10)

 def test_unrequested_distant_roads_do_not_prepare_bridge_networks(self):
  f=uk(lines=[[(-100.,0.),(100.,0.)],[(5000.,0.),(5100.,0.)]],classes=['primary']*2,
       tags=[{'highway':'primary'}]*2)
  g=grading.Grader(FRAME,FakeMD(f),lambda la,lo:np.full(np.shape(la),20.))
  g._base_cell(__import__('mapcells').cell_of(FRAME.lat0,FRAME.lon0))
  self.assertFalse(g.resolved_plans)
  la,lo,_=FRAME.enu_to_geodetic(np.array([-2.,2.]),np.zeros(2),0.)
  plans=g.plans(la,lo)
  self.assertEqual(len(plans),1)
  self.assertEqual(len(g.resolved_plans),1)

 def test_sharp_and_submetre_bridge_parts_use_the_shared_solver(self):
  f=uk(lines=[[(0,0),(1,0),(1,1),(20,1)],[(20,1),(20.2,1)]],
       classes=['motorway']*2,tags=[{'highway':'motorway','oneway':'yes','bridge':'yes'}]*2)
  model=ukvertical.Model(FRAME,FakeMD(f),lambda la,lo:np.full(np.shape(la),20.))
  for i in range(len(f)):
   ll=roads.bridge_parts(f,i)[0];x,y,_=FRAME.geodetic_to_enu(ll[:,1],ll[:,0],0.)
   xy=roads.densify(np.c_[x,y],2.)
   z=model.deck(str(f.ids[i]),xy)
   self.assertIsNotNone(z,'every part of the bridge must use its ground approaches\' height model')
   self.assertTrue(np.isfinite(z).all())

 def test_ground_interior_connector_is_a_real_height_graph_node(self):
  from test_roads import features,rules,FRAME as F
  f=features([[(0,0),(500,0)],[(250,0),(250,100)]],['motorway','motorway'])
  f.rules['connectors']=rules([(0,'A',0,0),(0,'J',.5,.5),(0,'B',1,1),(1,'J',0,0),(1,'C',1,1)],'text')
  self.assertEqual(len(roads.ground_parts(f,0)),2)

 def test_trench_pixel_does_not_become_hump_on_next_source_section(self):
  f=uk(lines=[[(-150,0),(-5,0)],[(-5,0),(5,0)],[(5,0),(21,0)],[(21,0),(180,0)]],
       classes=['trunk']*4,tags=[{'highway':'trunk','oneway':'yes'},
       {'highway':'trunk','oneway':'yes','bridge':'yes'},
       {'highway':'trunk','oneway':'yes'},{'highway':'trunk','oneway':'yes'}])
  def raw(la,lo):
   x,_,_=FRAME.geodetic_to_enu(la,lo,0.)
   return 20.-5*np.exp(-((x-5)/3)**2)
  g=grading.Grader(FRAME,FakeMD(f),raw)
  x=np.arange(8.,160.,2.);la,lo,_=FRAME.enu_to_geodetic(x,np.zeros(len(x)),0.)
  z=g.apply(la,lo,raw(la,lo))
  self.assertLess(z.max(),20.15,'a local trench must not be added to the recovered road')
  self.assertGreater(z.min(),19.5)
  self.assertLess(abs(np.diff(z)/2).max(),.06)

 def test_subway_approach_cannot_cut_through_surface_street(self):
  model=ukvertical.Model(FRAME,None,None)
  line=np.array([[0.,-10.],[0.,10.]])
  model.sample=lambda xy:np.full(len(xy),20.)
  street=grading.Plan(np.array([[-100.,20.],[100.,20.]]),np.array([20.,20.]),4.)
  xy=np.c_[np.arange(-4.,5.),np.full(9,20.)]
  with patch.object(model,'near',return_value=[]),patch.object(model,'paths',return_value=[(line,np.array([13.,13.]),1.5)]):
   z=model.excavate(xy,np.full(len(xy),20.),0.,[street])
  np.testing.assert_allclose(z,20.,atol=1e-9)

 def test_adjacent_bridge_cavity_cannot_excavate_ground_carriageway(self):
  model=ukvertical.Model(FRAME,None,None)
  line=np.array([[-20.,0.],[20.,0.]])
  model.sample=lambda xy:np.full(len(xy),20.)
  street=grading.Plan(np.array([[-100.,8.],[100.,8.]]),np.array([20.,20.]),5.)
  xy=np.array([[0.,8.],[0.,0.]])
  with patch.object(model,'near',return_value=[(line,np.array([20.,20.]),10.,'bridge')]),patch.object(model,'paths',return_value=[]):
   z=model.excavate(xy,np.full(2,20.),0.,[street])
  self.assertEqual(z[0],20.);self.assertLess(z[1],18.)

 def test_colliding_join_pins_full_width_and_meets_actual_terrain(self):
  line=np.array([[0.,0.,20.],[10.,0.,20.]])
  def ground(la,lo):
   x,y,_=FRAME.geodetic_to_enu(la,lo,0.)
   return 20.-.4*np.exp(-((x-10)/1.5)**2)+.015*y
  ch=roadmesh.bridge_join(FRAME,line,12.,-1,ground,(-100,-100,100,100))
  pp,tt,_=ch['join_mesh'];pp=np.array(pp);tt=np.array(tt)
  np.testing.assert_allclose(pp[abs(pp[:,0]-10)<1e-7,2],20.,atol=1e-8)
  far=pp[abs(pp[:,0]-16)<1e-7]
  np.testing.assert_allclose(far[:,2],terrain_surface.heights(FRAME,ground,far[:,:2]),atol=1e-8)
  mesh=roadmesh.deck([ch],np.zeros(3));self.assertTrue(np.isfinite(mesh[0]).all())
  self.assertEqual(len(mesh[1]),len(tt),'every interface triangle is physical collision geometry')

 def test_surface_collision_ignores_a_trench_in_underlying_terrain(self):
  model=ukvertical.Model(FRAME,None,None)
  p=grading.Plan(np.array([[-40.,0.],[40.,0.]]),np.array([19.2,20.8]),5.)
  model.mainline_plans['road']=p
  model.sample=lambda xy:np.full(len(xy),-50.)
  model.interfaces=lambda xy,z,lift:z
  floor=roadmesh.road_surface(np.array([[-40.,0.,0.],[40.,0.,0.]]),10.,model)
  physical=roadmesh.deck([floor],np.zeros(3))
  pp=physical[0];la,lo,_=FRAME.enu_to_geodetic(pp[:,0],pp[:,1],0.)
  expected=FRAME.geodetic_to_enu(la,lo,20.+.02*pp[:,0]+.04)[2]
  np.testing.assert_allclose(pp[:,2],expected,atol=2e-5)
  render=roadmesh.build(FRAME,[floor,{'m':'uk_line_dashed','w':.1,'tl':10.,'p':1,'n':[[-38.,0.,0.],[38.,0.,0.]]}],
                        lambda la,lo:np.full(np.shape(la),-50.),np.zeros(3),vertical=model)
  # Markings must follow the colliding road rather than being buried in the
  # old terrain trench. Neither drawing nor physics may retain that cliff.
  self.assertGreater(render[0][:,2].min(),19.)
  self.assertTrue(roads.collider_boxes(None,[floor]).get('deck'))

 def test_curved_surface_tile_seam_has_no_different_mitre_or_height(self):
  class Surface:
   def surface_heights(self,xy):return 30.+.02*xy[:,0]-.01*xy[:,1]
  line=np.array([[230.,20.,0.],[250.,10.,0.],[270.,30.,0.],[290.,30.,0.]])
  floors=[roadmesh.road_surface(line,12.,Surface(),box) for box in ((0.,0.,256.,256.),(256.,0.,512.,256.))]
  edges=[]
  for floor in floors:
   pp=np.asarray(floor['join_mesh'][0]);edge=pp[abs(pp[:,0]-256.)<1e-7]
   edges.append(edge[np.argsort(edge[:,1])])
  self.assertGreater(len(edges[0]),2)
  np.testing.assert_allclose(edges[0],edges[1],atol=1e-7)

 def test_curved_road_interior_does_not_receive_endpoint_extrapolation(self):
  model=ukvertical.Model(FRAME,None,None)
  # Interior points of a hairpin can lie behind the first end's tangent or
  # ahead of the last. Those planes do not make them approach extensions.
  p=grading.Plan(np.array([[0.,0.],[20.,0.],[20.,20.],[-20.,20.],[-20.,0.]]),np.array([20.,21.,22.,24.,25.]),4.)
  model.mainline_plans['curve']=p
  mask,z=model.surface(np.array([[-10.,20.],[0.,20.]]))
  self.assertTrue(mask.all());np.testing.assert_allclose(z,[23.5,23.],atol=1e-9)

 def test_stacked_bridge_floors_have_headroom_and_bounded_approaches(self):
  x=np.arange(-200.,201.,4.)
  lines=[np.c_[x,np.zeros(len(x))],np.c_[np.zeros(len(x)),x]]
  z=roads.constrain_deck_levels(lines,[np.full(len(x),20.),np.full(len(x),22.)],[1,2],[12.,12.])
  self.assertGreaterEqual(z[1][50]-z[0][50],roads.DECK_ROAD_CLEAR-.001)
  for line,height in zip(lines,z):self.assertLessEqual((abs(np.diff(height))/np.linalg.norm(np.diff(line,axis=0),axis=1)).max(),.080001)

 def test_changing_layer_at_actual_merge_does_not_add_a_storey(self):
  lines=[np.array([[0.,0.],[40.,0.]]),np.array([[40.,0.],[80.,10.]])]
  z=[np.array([20.,20.]),np.array([20.,20.])]
  got=roads.constrain_deck_levels(lines,z,[1,2],[12.,12.])
  np.testing.assert_allclose(got,z)

 def test_nearby_road_cannot_pull_a_carriageway_to_a_different_floor(self):
  model=ukvertical.Model(FRAME,None,None)
  lower=grading.Plan(np.array([[-40.,0.],[40.,0.]]),np.array([20.,20.]),6.)
  upper=grading.Plan(np.array([[-40.,8.],[40.,8.]]),np.array([27.5,27.5]),6.)
  model.mainline_plans[('low',)]=lower;model.mainline_plans[('high',)]=upper
  for plan,y,height in ((lower,0.,20.),(upper,8.,27.5)):
   ch=roadmesh.road_surface(np.array([[-40.,y,0.],[40.,y,0.]]),10.,model,plan=plan)
   p=np.asarray(ch['join_mesh'][0]);la,lo,_=FRAME.enu_to_geodetic(p[:,0],p[:,1],0.)
   expected=FRAME.geodetic_to_enu(la,lo,np.full(len(p),height+.04))[2]
   np.testing.assert_allclose(p[:,2],expected,atol=1e-6)

 def test_ramp_patch_is_clipped_exactly_out_of_protected_traffic_lanes(self):
  xy=np.array([[0.,-2.],[10.,-2.],[10.,2.],[0.,2.]])
  pp=np.c_[xy,20.+.02*xy[:,0]];tt=np.array([[0,1,2],[0,2,3]])
  quad=np.array([[1.,-1.],[3.,-1.],[3.,1.],[1.,1.]])
  p,t,uv=roadmesh.subtract_footprints(pp,tt,xy/10.,[quad])
  centres=p[t,:2].mean(1)
  self.assertFalse(((centres[:,0]>1.)&(centres[:,0]<3.)&(abs(centres[:,1])<1.)).any())
  a=p[t[:,1],:2]-p[t[:,0],:2];b=p[t[:,2],:2]-p[t[:,0],:2]
  self.assertAlmostEqual(float(abs(a[:,0]*b[:,1]-a[:,1]*b[:,0]).sum()/2),36.,places=7)
  np.testing.assert_allclose(p[:,2],20.+.02*p[:,0],atol=1e-9)
  np.testing.assert_allclose(uv,p[:,:2]/10.,atol=1e-9)

 def test_slip_road_mesh_cannot_stand_across_mainline_driving_lanes(self):
  main={'n':[[0.,0.,20.],[40.,0.,20.]],'w':12.,'m':'road_asphalt_2lane','fixed':True,'deck':True,'deck_priority':2}
  ramp={'n':[[0.,8.,20.3],[40.,8.,20.3]],'w':8.,'m':'road_asphalt_2lane','fixed':True,'deck':True,'deck_priority':1}
  p,t,*_=roadmesh.deck([main,ramp],np.zeros(3))
  # Vertices of the ramp's top where it meets the mainline are flush; a
  # higher independent bridge is outside the bounded merge correction.
  self.assertTrue(roadmesh.deck_exclusions(ramp,[main]))
  upper={**ramp,'n':[[0.,8.,27.5],[40.,8.,27.5]]}
  self.assertFalse(roadmesh.deck_exclusions(upper,[main]))
  render=roadmesh.build(FRAME,[main,ramp],lambda la,lo:la*0,np.zeros(3))
  self.assertTrue(np.isfinite(p).all() and np.isfinite(render[0]).all())

 def test_abutment_matches_across_width_and_ignores_unconnected_bridge(self):
  model=ukvertical.Model(FRAME,None,None)
  plan=grading.Plan(np.array([[-40.,0.],[0.,0.]]),np.array([19.5,19.5]),5.,('A','J'))
  line=roads.RouteLine(np.array([[0.,0.],[10.,5.]]),('J','B'))
  normal=np.array([-5.,10.])/np.sqrt(125.)
  xy=np.linspace(-4.,4.,9)[:,None]*normal
  bridge=(line,np.array([20.,20.5]),5.,'upper')
  z=model.road_interfaces(xy,np.full(len(xy),19.5),plan,[bridge])
  np.testing.assert_allclose(z,20.,atol=1e-9)
  other=roads.RouteLine(line.copy(),('other','different'))
  z=model.road_interfaces(xy,np.full(len(xy),19.5),plan,[(other,np.array([27.,27.5]),5.,'foreign')])
  np.testing.assert_allclose(z,19.5,atol=1e-9)

 def test_carriageway_cap_closes_corner_without_fanning_out_hard_shoulder(self):
  class Surface:
   def surface_heights(self,xy):return 20.+xy[:,0]*.02
  floor=roadmesh.road_surface(np.array([[-40.,0.,0.],[0.,0.,0.]]),12.,Surface(),cap_width=8.,cap_offset=-1.)
  p=np.asarray(floor['join_mesh'][0]);cap=p[p[:,0]>.01]
  self.assertGreater(cap[:,0].max(),4.)
  self.assertGreaterEqual(cap[:,1].min(),-5.051);self.assertLessEqual(cap[:,1].max(),3.051)
  collision=roadmesh.deck([floor],np.zeros(3));self.assertEqual(len(collision[1]),len(floor['join_mesh'][1]))

if __name__=='__main__':unittest.main()
