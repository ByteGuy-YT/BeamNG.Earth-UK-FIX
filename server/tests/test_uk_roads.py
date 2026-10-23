"""UK road contracts: the same physical lanes in meshes, AI, grading and tree exclusion."""
import json
import math
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

import numpy as np

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent),
                str(Path(__file__).resolve().parents[2] / "tools")]
import geodesy
import grading
import islands
import navgraph
import osm_enrich
import roadcontext
import roadmesh
import roadprofile
import roads
import vegetation
import furniture
from test_roads import features, flat, LAT, LON, M_LAT, M_LON, rules

FRAME = geodesy.EnuFrame(53.34, -1.8, 0.)


def uk(lines=None, classes=None, tags=None, widths=(), frame=FRAME):
    lines = lines or [[(0, 0), (200, 0)]]
    f = features(lines, classes or ["primary"] * len(lines), widths=widths)
    east = (f.lonlat[:, 0] - LON) * M_LON
    north = (f.lonlat[:, 1] - LAT) * M_LAT
    la, lo, _ = frame.enu_to_geodetic(east, north, 0.)
    f.lonlat = np.column_stack([lo, la])
    f.attrs["osm_tags"] = np.asarray([json.dumps(t) for t in (tags or [{}] * len(lines))])
    return f


class UKContext(unittest.TestCase):
    def test_rules_work_without_airports_in_all_four_nations(self):
        for lat, lon, name in [(51.507, -.128, "England"), (51.481, -3.18, "Wales"),
                               (55.953, -3.188, "Scotland"), (54.597, -5.93, "Northern Ireland"),
                               (53.34, -1.8, "England")]:
            self.assertEqual(roadcontext.region_at(lat, lon), name)
            self.assertEqual(navgraph.country_near(None, lat, lon), "GB")
        r = navgraph.road_rules(navgraph.country_near(None, 53.34, -1.8))
        self.assertTrue(r["rightHandDrive"] and r["mph"] and r["redYellow"])
        self.assertFalse(r["turnOnRed"])

    def test_not_a_british_isles_bounding_box(self):
        for lat, lon in [(53.349, -6.26), (54.0, -7.4), (48.857, 2.352), (39.29, -76.58), (54.15, -4.48)]:
            self.assertIsNone(roadcontext.region_at(lat, lon))


class PhysicalWidths(unittest.TestCase):
    def test_inferred_dual_directions_are_uk_even_for_physics_callers(self):
        f = uk(lines=[[(0, 0), (300, 0)], [(300, 16), (0, 16)]], classes=["primary", "primary"])
        f.attrs["name"] = np.array(["Dual road", "Dual road"])
        a = roads.road_specs(f)
        b = roads.road_specs(f, left_hand=True)
        self.assertEqual([s.dir for s in a], [s.dir for s in b])
        for sp in a:
            if roads.has_median(sp):
                self.assertIn(roads.median_side(sp), (-1, 1))

    def test_peak_district_defaults_do_not_add_us_shoulders_or_parking(self):
        for cls, width in [("primary", 6.5), ("secondary", 6.), ("tertiary", 5.5),
                           ("unclassified", 5.), ("residential", 5.3), ("service", 3.)]:
            sp = roads.road_specs(uk(classes=[cls]))[0]
            self.assertAlmostEqual(sp.width, width)
            self.assertEqual(sp.walk, 0.)
            town = roads.road_specs(uk(classes=[cls]), lambda la, lo: np.ones(np.shape(la), bool))[0]
            self.assertAlmostEqual(town.width, width)

    def test_mapped_width_and_asymmetric_lanes_survive_to_ai_and_paint(self):
        f = uk(tags=[{"width": "10.2", "lanes": "3", "lanes:forward": "2", "lanes:backward": "1"}])
        sp = roads.road_specs(f)[0]
        self.assertEqual(sp.width, 10.2)
        self.assertEqual((sp.profile.forward, sp.profile.backward), (2, 1))
        g = navgraph.build(FRAME, [f], flat, (0, 0), left_hand=True)
        self.assertTrue(all(e[3:5] == [2, 1] and e[7] == 5.1 for e in g["edges"]))
        marks = roads.extras(sp, np.array([[0., 0., 0.], [200., 0., 0.]]), -1.8, True)
        self.assertEqual(sum(m[0]["m"] == "uk_line_dashed" for m in marks), 2)

    def test_physical_width_never_comes_from_a_legal_maxwidth(self):
        sp = roads.road_specs(uk(tags=[{"maxwidth": "2.1", "width": "5.8 m"}]))[0]
        self.assertEqual(sp.width, 5.8)
        self.assertEqual(roads.road_specs(uk(tags=[{"maxwidth": "2.1"}]))[0].width, 6.5)
        self.assertAlmostEqual(roadprofile.metres("12' 6\""), 3.81)
        self.assertIsNone(roadprofile.metres("5;7"))

    def test_three_metre_two_way_road_is_shared_without_a_centre_line(self):
        f = uk(tags=[{"width": "3", "lanes": "1", "lane_markings": "no"}])
        sp = roads.road_specs(f)[0]
        self.assertTrue(sp.profile.shared)
        self.assertEqual(roads.extras(sp, np.array([[0., 0., 0.], [200., 0., 0.]]), -1.8, True), [])
        g = navgraph.build(FRAME, [f], flat, (0, 0), left_hand=True)
        self.assertTrue(all(e[7] == 1.5 and e[5] <= navgraph.NARROW_MS + .01 for e in g["edges"]))

    def test_mapped_two_narrow_lanes_are_not_silently_replaced_by_shared_space(self):
        sp = roads.road_specs(uk(tags=[{"width": "4.4", "lanes": "2", "lane_markings": "yes"}]))[0]
        self.assertFalse(sp.profile.shared)
        self.assertTrue(sp.profile.lane_markings)

    def test_per_lane_widths_control_marking_positions(self):
        sp = roads.road_specs(uk(tags=[{"lanes": "2", "width:lanes:forward": "3.1", "width:lanes:backward": "2.9"}]))[0]
        self.assertAlmostEqual(sp.width, 6.)
        self.assertEqual(sp.profile.lane_widths, (3.1, 2.9))
        marks = roads.extras(sp, np.array([[0., 0., 0.], [200., 0., 0.]]), -1.8, True)
        centre = next(pts for look, w, pts in marks if look["m"] == "uk_line_dashed")
        self.assertTrue(np.allclose(centre[:, 1], -.1))

    def test_pavements_are_independent_per_side_even_with_mapped_road_width(self):
        f = uk(tags=[{"width": "5.8", "sidewalk": "both", "sidewalk:left:width": "1.2", "sidewalk:right:width": "2.1"}])
        sp = roads.road_specs(f)[0]
        self.assertEqual((sp.profile.walk_left, sp.profile.walk_right), (1.2, 2.1))
        marks = roads.extras(sp, np.array([[0., 0., 0.], [200., 0., 0.]]), -1.8, True)
        walks = {look["side"]: w for look, w, pts in marks if look["m"] == roads.SIDEWALK["m"]}
        self.assertEqual(walks, {1: 1.2, -1: 2.1})
        no_walk = roads.road_specs(uk(tags=[{"sidewalk": "no"}]), lambda la, lo: np.ones(np.shape(la), bool))[0]
        self.assertFalse(roads.has_sidewalks(no_walk))

    def test_building_setbacks_never_expand_a_village_street(self):
        town = lambda la, lo: np.ones(np.shape(la), bool)
        sp = roads.road_specs(uk(), town, lambda fid, ll: (25., 4.))[0]
        self.assertEqual(sp.width, 6.5)
        narrow = roads.road_specs(uk(), town, lambda fid, ll: (3., .8))[0]
        self.assertLessEqual(narrow.width + narrow.profile.walk_left + narrow.profile.walk_right, 4.6 + 1e-6)

    def test_grading_does_not_reinflate_uk_roads(self):
        sp = roads.road_specs(uk(tags=[{"width": "3", "sidewalk": "no"}]))[0]
        plan = grading._plan(np.array([[0., 0.], [20., 0.], [40., 0.]]), np.zeros(3), sp)
        self.assertAlmostEqual(plan.half, 1.5 + grading.SIDEWALK_MARGIN_M)


class Motorways(unittest.TestCase):
    def test_hard_shoulder_is_outside_three_lanes_and_ai_is_offset_off_it(self):
        f = uk(classes=["motorway"], tags=[{"lanes": "3", "oneway": "yes"}])
        sp = roads.road_specs(f)[0]
        self.assertAlmostEqual(sp.width, 3 * 3.65 + 3.3 + .5)
        self.assertEqual((sp.profile.forward, sp.profile.backward), (3, 0))
        self.assertAlmostEqual(sp.profile.drive, 10.95)
        self.assertLess(sp.profile.offset, 0)
        g = navgraph.build(FRAME, [f], flat, (0, 0), left_hand=True)
        self.assertTrue(all(e[3:5] == [3, 0] and e[7] == 5.47 for e in g["edges"]))
        self.assertTrue(all(n[1] < -1. for n in g["nodes"].values()))

    def test_all_lane_running_does_not_invent_a_hard_shoulder(self):
        sp = roads.road_specs(uk(classes=["motorway"], tags=[{"lanes": "4", "shoulder": "no"}]))[0]
        self.assertAlmostEqual(sp.width, 14.6)
        self.assertEqual((sp.profile.left_space, sp.profile.right_space), (0., 0.))

    def test_motorway_link_stays_one_lane_not_three_plus_hard_shoulder(self):
        sp = roads.road_specs(uk(classes=["motorway"], tags=[{"highway": "motorway_link", "oneway": "yes"}]))[0]
        self.assertEqual(sp.profile.forward, 1)
        self.assertAlmostEqual(sp.width, 4.5)


class RoundaboutsAndTrees(unittest.TestCase):
    def test_mapped_mini_roundabout_has_clockwise_graph_and_painted_centre(self):
        f = uk(lines=[[(80, 80), (200, 80)], [(80, 80), (80, 200)], [(80, 80), (-80, 80)]])
        la, lo, _ = FRAME.enu_to_geodetic(80., 80., 0.)
        node = {"highway": "mini_roundabout", "lon": float(lo), "lat": float(la)}
        f.attrs["osm_tags"] = np.array([json.dumps({"_nodes": [node]})] * 3)
        f.rules["connectors"] = rules([(i, "J", 0, 0) for i in range(3)] + [(i, f"E{i}", 1, 1) for i in range(3)])
        g = navgraph.build(FRAME, [f], flat, (80, 80), left_hand=True)
        ring = [e for e in g["edges"] if all(n.startswith("mcJ_") for n in e[:2])]
        self.assertGreaterEqual(len(ring), 10)
        for e in ring:
            a, b = np.array(g["nodes"][e[0]][:2]) - 80, np.array(g["nodes"][e[1]][:2]) - 80
            self.assertLess(a[0] * b[1] - a[1] * b[0], 0.)
            self.assertEqual(e[2:5], [1, 1, 0])
        self.assertNotIn("cJ", g["nodes"])
        self.assertTrue(all(e[0] in g["nodes"] and e[1] in g["nodes"] for e in g["edges"]))
        chunks = roads.build_tile(FRAME, 0, 0, [f], flat, walks=[], left_hand=True)
        self.assertTrue(any(c.get("poly") and c["m"] == "line_white" for c in chunks))

    def test_give_way_lines_are_on_the_incoming_uk_half(self):
        f = uk(lines=[[(80, 80), (200, 80)], [(80, 80), (80, 200)], [(80, 80), (80, -80)]],
               classes=["residential", "primary", "primary"])
        specs = roads.road_specs(f)
        lines = [(str(i), sp, np.c_[np.array(xy, float), np.zeros(len(xy))], -1.8)
                 for i, (sp, xy) in enumerate(zip(specs, [[(80, 80), (200, 80)], [(80, 80), (80, 200)], [(80, 80), (80, -80)]]))]
        chunks = roads._uk_junction_markings(lines, (0, 0, 256, 256), {})
        giveways = [c for c in chunks if c["m"] == "uk_line_giveway"]
        self.assertEqual(len(giveways), 2)
        self.assertTrue(all(p[1] < 80 for c in giveways for p in c["n"]))

    def test_tagged_irregular_ring_does_not_depend_on_roundness_or_complete_tile(self):
        # A long, incomplete arc in one tile must still be identified from mapping.
        f = uk(lines=[[(0, 0), (40, 5), (100, 70)]], tags=[{"junction": "roundabout", "lanes": "2"}])
        sp = roads.road_specs(f)[0]
        pts = np.array([[0., 0., 0.], [40., 5., 0.], [100., 70., 0.]])
        self.assertEqual(islands.ring_directions([("ring", sp, pts, -1.8)], True), {"ring": 1})
        self.assertEqual(sp.profile.forward, 2)

    def test_uk_junctions_do_not_invent_signals_or_all_way_stops(self):
        sp = roads.road_specs(uk(classes=["residential"]))[0]
        arms = [(str(i), sp, np.array(u, float), np.zeros(3), True, 100.)
                for i, u in enumerate([(1, 0), (0, 1), (-1, 0), (0, -1)])]
        self.assertEqual(furniture.junction_controls(arms, None), [])

    def test_tree_mask_includes_mapped_pavements(self):
        from types import SimpleNamespace
        f = uk(tags=[{"width": "6", "sidewalk": "both", "sidewalk:both:width": "2"}])
        x, y = vegetation._to3857(-1.8, 53.34)
        chm = SimpleNamespace(x0=float(x - 100), y0=float(y + 100), dx=1., dy=1.)
        mask = np.zeros((200, 400), bool)
        vegetation._mask_roads(f, mask, chm)
        # 4.5 m from centre is on the 2 m pavement; a tree must be rejected there.
        ground_pixel = 1. / math.cos(math.radians(53.34))
        self.assertTrue(mask[int(100 - 4.5 * ground_pixel), 150])

    def test_no_hashed_pavement_trees_or_us_hydrants(self):
        sp = roads.road_specs(uk(tags=[{"sidewalk": "both"}]), lambda la, lo: np.ones(np.shape(la), bool))[0]
        line = np.array([[0., 0., 0.], [300., 0., 0.]])
        walk = {"fid": "village", "side": 1, "w": sp.walk,
                "pts": line + np.array([0., sp.width / 2 + sp.walk / 2, 0.])}
        props = furniture.place([("village", sp, line, -1.8)], [walk], (-100, -100, 400, 100), town=True, left_hand=True)
        self.assertFalse(any(r[0] in {furniture.G_STREET_TREE, furniture.G_HYDRANT} for r in props))


class OSMJoin(unittest.TestCase):
    def test_lane_change_splits_keep_original_junction_connectors(self):
        f = uk()
        f.rules["connectors"] = rules([(0, "start", 0, 0), (0, "middle", .500003, .500003), (0, "end", 1, 1)])
        parts = osm_enrich.split_features(f, {0: [(0., .5, {"lanes": "2"}), (.5, 1., {"lanes": "3", "lanes:forward": "2", "lanes:backward": "1"})]})
        self.assertEqual(len(parts), 2)
        sp = roads.road_specs(parts)
        self.assertEqual(sorted(s.profile.forward + s.profile.backward for s in sp), [2, 3])
        cons = parts.rules["connectors"]
        self.assertEqual(list(cons.value).count("middle"), 2)
        self.assertFalse(any(str(v).startswith("osm:") for v in cons.value))
        graph = navgraph.build(FRAME, [parts], flat, (0, 0), left_hand=True)
        self.assertIn("cmiddle", graph["nodes"])
        self.assertTrue(any(e[3:5] == [1, 1] for e in graph["edges"]))
        self.assertTrue(any(e[3:5] == [2, 1] for e in graph["edges"]))

    def test_merged_osm_ways_keep_common_tags_and_expose_width_changes(self):
        a = [[0., 0.], [.001, 0.], [.002, 0.]]
        left = osm_enrich.partial_alignment(a, [[0., 0.], [.001, 0.]])
        right = osm_enrich.partial_alignment(a, [[.001, 0.], [.002, 0.]])
        self.assertIsNotNone(left)
        self.assertIsNotNone(right)
        merged = osm_enrich.merge_matches([({"lanes": "2", "width": "5.5"}, left[1], left[2]),
                                            ({"lanes": "2", "width": "6.2"}, right[1], right[2])])
        self.assertEqual(merged["lanes"], "2")
        self.assertNotIn("width", merged)
        self.assertEqual(merged["_section_conflicts"], "width")

    def test_reversed_geometry_keeps_lanes_width_and_sides(self):
        t = {"oneway": "yes", "lanes:forward": "2", "sidewalk": "left", "sidewalk:left:width": "1.1"}
        r = osm_enrich.reverse_tags(t)
        self.assertEqual((r["oneway"], r["lanes:backward"], r["sidewalk"], r["sidewalk:right:width"]), ("-1", "2", "right", "1.1"))
        self.assertEqual(osm_enrich.alignment([[0., 0.], [.001, 0.]], [[.001, 0.], [0., 0.]]), -1)
        self.assertIsNone(osm_enrich.alignment([[0., 0.], [.001, 0.]], [[0., .01], [.001, .01]]))

    def test_xml_index_and_source_join_without_network(self):
        from prepare_uk_roads import build
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            f = uk()
            coords = f.lonlat
            (root / "sample.osm").write_text(f'<osm version="0.6"><node id="1" lat="{coords[0,1]}" lon="{coords[0,0]}"/>'
                f'<node id="2" lat="{coords[1,1]}" lon="{coords[1,0]}"/><way id="42" version="3"><nd ref="1"/><nd ref="2"/>'
                '<tag k="highway" v="primary"/><tag k="width" v="5.9"/><tag k="lanes" v="2"/></way></osm>')
            output = root / "roads/osm.sqlite"
            build([root / "sample.osm"], output)
            f.attrs["source_refs"] = np.array([json.dumps([{"dataset": "OpenStreetMap", "record_id": "w42@2"}])])
            enrich = osm_enrich.Enricher(root)
            # Use this test's local database irrespective of any installed national index.
            enrich.path, enrich.signature = output.resolve(), "test"
            enrich.apply(f)
            self.assertEqual(str(f.attrs["osm_match"][0]), "matched")
            self.assertEqual(roads.road_specs(f)[0].width, 5.9)
            enrich.local.db.close()


if __name__ == "__main__":
    unittest.main()
