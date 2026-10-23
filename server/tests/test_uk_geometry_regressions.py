"""General regressions derived from the user's named UK road screenshots.

Synthetic geometry deliberately varies position and terrain; no site-specific fixes.
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import grading
import navgraph
import roadmesh
import osm_enrich
import roads
import sidewalks
import surface
from test_grading import FakeMD
from test_uk_roads import FRAME, uk


def elevation(x, y):
    return 20. + .04 * y - 3. * np.exp(-((x - 130.) / 22.) ** 2)


def hilly(lat, lon):
    x, y, _ = FRAME.geodetic_to_enu(lat, lon, 0.)
    return elevation(x, y)


class StreetGeometry(unittest.TestCase):
    def test_controlled_motorway_has_four_driving_lanes_plus_a_separate_shoulder(self):
        # "motorway only 4 lanes and ai using hard shoulder.png"
        tags = {"highway": "motorway", "lanes": "4", "active_traffic_management": "yes"}
        for direction in ("yes", "-1"):
            f = uk(classes=["motorway"], tags=[{**tags, "oneway": direction}])
            sp = roads.road_specs(f)[0]
            p = sp.profile
            self.assertAlmostEqual(p.drive, 14.6)
            self.assertAlmostEqual(sp.width, 18.4)
            self.assertAlmostEqual(abs(p.offset), 1.4)
            g = navgraph.build(FRAME, [f], hilly, (0, 0), left_hand=True)
            self.assertTrue(g["edges"])
            self.assertTrue(all(e[3] + e[4] == 4 and abs(e[7] - 7.3) < .001 for e in g["edges"]))
            marks = roads.extras(sp, np.array([[0., 0., 0.], [100., 0., 0.]]), -1.8, True)
            self.assertEqual(sum(look["m"] == "uk_line_dashed" for look, _, _ in marks), 3)
        alr = roads.road_specs(uk(classes=["motorway"], tags=[{**tags, "shoulder": "no"}]))[0]
        self.assertAlmostEqual(alr.profile.drive, 14.6)
        self.assertAlmostEqual(alr.width, 14.6)

    def test_main_road_underwood_not_mistaken_for_dual_carriageways(self):
        # "main road underwood totally wrong, only 1 lane tall pavements.png"
        f = uk(lines=[[(0, 0), (200, 0)], [(200, 12), (0, 12)]],
               classes=["tertiary", "tertiary"], tags=[{"highway": "tertiary"}] * 2)
        f.attrs["name"] = np.array(["Main Road", "Main Road"])
        for sp in roads.road_specs(f):
            self.assertEqual((sp.dir, sp.oneway, sp.median), (0, False, None))
            self.assertEqual(sp.width, 5.5)
            self.assertEqual((sp.profile.forward, sp.profile.backward), (1, 1))

    def test_mansfield_road_major_carriageway_estimate_and_explicit_override(self):
        # "mansfield road coming from junction 27 of m1 only 1 thin lane instead of 2.png"
        t = {"highway": "primary", "oneway": "yes"}
        f = uk(tags=[t])
        sp = roads.road_specs(f)[0]
        self.assertEqual((sp.profile.forward, sp.profile.backward, sp.width), (2, 0, 6.5))
        graph = navgraph.build(FRAME, [f], hilly, (0, 0), left_hand=True)
        self.assertTrue(all(e[2:5] == [1, 2, 0] for e in graph["edges"]))
        explicit = roads.road_specs(uk(tags=[{**t, "lanes": "1"}]))[0]
        self.assertEqual((explicit.profile.forward, explicit.width), (1, 3.25))

    def test_lane_arrays_supply_missing_approach_counts(self):
        f = uk(tags=[{"highway": "primary", "oneway": "yes", "turn:lanes": "left|through|through;right"}])
        p = roads.road_specs(f)[0].profile
        self.assertEqual((p.forward, p.backward), (3, 0))
        self.assertIn("lane-count-from-mapped-lane-arrays", p.diagnostics)

    def test_bluebell_fairview_estimates_are_unmarked_with_narrower_pavements(self):
        # "road + pavement seems weirdly scaled compared to irl NG16 5FN underwood.png"
        f = uk(classes=["residential"], tags=[{"highway": "residential", "sidewalk": "both"}])
        sp = roads.road_specs(f)[0]
        self.assertEqual((sp.width, sp.profile.walk_left, sp.profile.walk_right), (5.3, 1.5, 1.5))
        self.assertFalse(sp.profile.lane_markings)
        self.assertFalse(any(look["m"].startswith("uk_line") for look, _, _ in roads.extras(sp, np.array([[0., 0., 0.], [100., 0., 0.]]), -1.8)))

    def test_pavement_cross_sections_never_fold_even_at_island_widths(self):
        # "example of broken rounabout ripley police station, again mainly pavement.png"
        for width in (.5, .9, 1.2, 1.5, 1.8, 2.5):
            for kerb in (.01, .125):
                p = sidewalks.profile(.125, width, kerb)
                self.assertTrue((np.diff(p[:, 0]) >= 0).all(), (width, kerb, p))
                self.assertAlmostEqual(p[6, 0], width)

    def test_pavements_follow_sag_and_the_actual_road_edge(self):
        # "road too thin + floating pavement in ripley.png"
        f = uk(lines=[[(10, 110), (240, 110)]], tags=[{"highway": "primary", "sidewalk": "both"}])
        walks = []
        roads.build_tile(FRAME, 0, 0, [f], hilly, walks=walks, left_hand=True)
        self.assertEqual(len(walks), 2)
        for w in walks:
            curb = w["curb"]
            self.assertLessEqual(np.linalg.norm(np.diff(curb[:, :2], axis=0), axis=1).max(), 2.01)
            self.assertLess(np.abs(curb[:, 2] - elevation(curb[:, 0], curb[:, 1])).max(), .015)
            self.assertEqual(w["h"], .125)
            self.assertAlmostEqual(abs(float(np.mean(curb[:, 1])) - 110.), 6.5 / 2, delta=.03)
            b = sidewalks.Builder((0, 0, 0), collision=True)
            b.add_run(curb, w["out"], w["w"], w["h"])
            self.assertTrue(np.isfinite(b.arrays()[0]).all())

    def test_hilly_roundabout_island_is_not_a_floating_flat_slab(self):
        ang = np.linspace(0, -2 * np.pi, 41)
        ring = np.c_[128 + 45 * np.cos(ang), 128 + 45 * np.sin(ang)]
        f = uk(lines=[ring.tolist()], tags=[{"highway": "primary", "junction": "roundabout", "lanes": "2"}])
        walks = []
        roads.build_tile(FRAME, 0, 0, [f], hilly, walks=walks, left_hand=True)
        islands = [w for w in walks if w.get("fid") == "island"]
        self.assertTrue(islands)
        for w in islands:
            self.assertEqual(w["w"], .25, "an island gets a kerb, not an invented 1.2 m pavement")
            q = w["curb"]
            self.assertLess(np.abs(q[:, 2] - elevation(q[:, 0], q[:, 1])).max(), .02)
            self.assertGreater(np.ptp(q[:, 2]), 1.)


class PaintAndTerrain(unittest.TestCase):
    def test_lane_separators_have_geometry_gaps_including_fixed_bridge_paint(self):
        ch = {"m": "uk_line_dashed", "w": .12, "tl": 6., "p": 6,
              "n": [[0, 0, 5], [60, 0, 8]], "fixed": True}
        pieces = roads.paint_geometry([ch])
        self.assertGreater(len(pieces), 5)
        self.assertTrue(all(p["m"] == "line_white" and p["fixed"] for p in pieces))
        intervals = [(p["n"][0][0], p["n"][-1][0]) for p in pieces]
        self.assertTrue(all(b - a <= 2.001 for a, b in intervals))
        self.assertTrue(all(c - b >= 3.99 for (_, b), (c, _) in zip(intervals[:-1], intervals[1:])))

    def test_giveway_and_zebra_are_not_continuous_white_bars(self):
        for material in ("uk_line_giveway", "uk_line_zebra"):
            p = roads.paint_geometry([{"m": material, "w": .15, "tl": 1., "p": 3,
                                      "n": [[0, 0, 0], [0, 8, 0]]}])
            self.assertGreater(len(p), 5)
            self.assertLess(sum(np.linalg.norm(np.diff(c["n"], axis=0), axis=1).sum() for c in p), 7.)

    def test_under_motorway_mesh_samples_interior_collision_terrain(self):
        # "weird road textures and mesh under SOME motorways.png"
        def ground(lat, lon):
            _, y, _ = FRAME.geodetic_to_enu(lat, lon, 0.)
            return 10. + .025 * y * y
        ch = {"m": "road_asphalt_2lane", "w": 20., "tl": 11., "n": [[0, 0, 0], [100, 0, 0]]}
        P = roadmesh.build(FRAME, [ch], ground, (0, 0, 0))[0]
        centre = P[np.abs(P[:, 1]) < .01]
        self.assertGreater(len(centre), 10)
        self.assertLess(np.abs(centre[:, 2] - 10.).max(), .01)
        import terrain_surface
        self.assertLess(np.abs(P[:,2]-terrain_surface.heights(FRAME,ground,P[:,:2])).max(),1e-6)

    def test_grass_mask_covers_motorway_edges_without_pavements(self):
        # "I LOVE the grass but often overlays onto roads.png"
        f = uk(lines=[[(-80, 0), (80, 0)]], classes=["motorway"],
               tags=[{"highway": "motorway", "lanes": "3", "shoulder": "yes"}])
        x, y = np.meshgrid(np.arange(-40., 42., 2.), np.arange(-20., 22., 2.))
        la, lo, _ = FRAME.enu_to_geodetic(x, y, 0.)
        before = np.full(x.shape, surface.GRASS, np.uint8)
        after = surface.paint_roads(before, la, lo, [f], 2.)
        half = roads.road_specs(f)[0].width / 2
        self.assertTrue((after[np.abs(y) <= half + 1.] == surface.ASPHALT).all())
        self.assertTrue((after[np.abs(y) >= half + 7.] == surface.GRASS).all())


class Bridges(unittest.TestCase):
    def test_smoothed_embankment_is_not_raised_twice_by_raw_dem_clearance(self):
        f = uk(lines=[[(-400, 0), (-35, 0)], [(-35, 0), (35, 0)]], classes=["trunk"] * 2,
               tags=[{"highway": "trunk", "oneway": "yes"},
                     {"highway": "trunk", "oneway": "yes", "bridge": "yes"}])
        flat = lambda la, lo: np.full(np.shape(la), 10.)
        gr = grading.Grader(FRAME, FakeMD(f), flat)
        # Smoothing the terrain has already filled 5 m of the raw depression.
        xy = np.array([[-400., 0.], [-35., 0.]])
        plans = [(str(f.ids[0]), grading.Plan(xy, np.array([15., 15.]), 4.))]
        with patch.object(gr, "_end_lift", return_value=(6., [])):
            gr._lift_uk_approaches(next(iter(roads.cells_of_tile(FRAME, 0, 0))), plans, [roads.road_specs(f)[0]])
        self.assertAlmostEqual(plans[0][1].z[-1], 16., delta=.02)
        self.assertAlmostEqual(plans[0][1].z[0], 15., delta=.02)

    def test_twin_bridge_approaches_share_clearance_without_joining_stacked_levels(self):
        # "not usable bridge m1 between J27 + J26.png": a lower carriageway's
        # pinned ends must not leave a hump where the parallel decks are merged.
        bridges = [np.array([[-15., y], [15., y]]) for y in (0., 18., 24.)]
        points = np.array([[-15., 0.], [-15., 18.], [-15., 24.], [15., 0.], [15., 18.]])
        z = grading.paired_abutment_targets(points, [16., 18., 25., 17., 19.], bridges, [1., 1., 2.])
        np.testing.assert_allclose(z, [18., 18., 25., 19., 19.])

    def test_source_merge_preserves_bridge_and_turn_lane_boundaries(self):
        plan = osm_enrich.section_plan([
            ({"highway": "trunk", "oneway": "yes", "turn:lanes": "through|right"}, 0., .4),
            ({"highway": "trunk", "oneway": "yes", "turn:lanes": "through|through|right", "bridge": "yes"}, .4, 1.)])
        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[1][2]["bridge"], "yes")

    def test_short_bridge_is_retained_on_a_long_source_way(self):
        # "HUGE dips in SOME dual carridgeways ...png"
        f = uk(lines=[[(0, 0), (20000, 0)]], classes=["trunk"])
        from test_roads import rules
        f.rules["flags"] = rules([(0, "is_bridge", .4998, .5002)])
        parts = roads.bridge_parts(f, 0)
        self.assertEqual(len(parts), 1)
        self.assertAlmostEqual(roads._feature_length_m(f, 0) * .0004, 8., delta=.06)
        self.assertEqual(len(roads.bridge_levels(f, 0)), len(parts))

    def test_mapped_bridge_section_is_a_deck_with_the_mapped_lanes(self):
        f = uk(classes=["motorway"], tags=[{"highway": "motorway", "bridge": "yes", "lanes": "4", "shoulder": "no"}])
        self.assertIsNone(roads.road_specs(f)[0])
        self.assertEqual(roads.level_ranges(f, 0), [(0., 1., "bridge")])
        sp = roads.bridge_specs(f)[0]
        self.assertEqual(sp.profile.forward, 4)
        self.assertAlmostEqual(sp.profile.drive, 14.6)

    def test_near_deck_ends_across_grid_boundary_are_one_chain(self):
        # "not usable bridge m1 between J27 + J26.png"
        lines = [np.array([[0., 0.], [20.24, 0.]]), np.array([[20.26, 0.], [40., 0.]])]
        def ground(xy):
            return .1 * xy[:, 0] + np.where((xy[:, 0] > 20) & (xy[:, 0] < 21), 100., 0.)
        z = roads.deck_heights(lines, ground)
        self.assertAlmostEqual(z[0][-1], z[1][0], delta=.003)
        self.assertLess(float(z[0][-1]), 3.)

    def test_uk_major_bridge_approach_continues_across_source_sections(self):
        lines = [[(-400, 0), (-130, 0)], [(-130, 0), (-35, 0)], [(-35, 0), (35, 0)],
                 [(35, 0), (130, 0)], [(130, 0), (400, 0)], [(0, -400), (0, 400)]]
        tags = [{"highway": "primary", "lanes": "2", "oneway": "yes"} for _ in range(5)]
        tags[2]["bridge"] = "yes"
        tags.append({"highway": "secondary", "lanes": "2"})
        f = uk(lines=lines, classes=["primary"] * 5 + ["secondary"], tags=tags)
        flat = lambda la, lo: np.full(np.shape(la), 10.)
        gr = grading.Grader(FRAME, FakeMD(f), flat)
        x = np.arange(-390., -34., 2.)
        la, lo, _ = FRAME.enu_to_geodetic(x, np.zeros(len(x)), 0.)
        h = gr.apply(la, lo, flat(la, lo))
        # The independent lower road stays flat. The underestimated upper
        # bridge gets clearance and a continuous, grade-bounded approach.
        self.assertAlmostEqual(h[-1], 17.5, delta=.05)
        la2,lo2,_=FRAME.enu_to_geodetic(np.array([0.]),np.array([0.]),0.)
        lower=gr.apply(la2,lo2,flat(la2,lo2))
        self.assertAlmostEqual(lower[0],10.,delta=.05)
        self.assertLess(np.abs(np.diff(h) / 2).max(), grading.APPROACH_GRADE * 1.1)
        self.assertLess(h[0], 10.2)


if __name__ == "__main__":
    unittest.main()
