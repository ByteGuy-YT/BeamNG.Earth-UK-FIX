import os,sys,unittest,json,time,faulthandler
from pathlib import Path
sys.path[:0]=['server/tests','server']
patterns=['test_roads.py','test_roadmesh.py','test_world_geometry.py','test_approaches.py','test_grading.py','test_uk_geometry_regressions.py','test_uk_round2.py','test_motorway_round3.py','test_navgraph.py','test_parking.py','test_mapdata.py','test_tunnels.py','test_cdae.py','test_blockworker.py','test_road_interfaces.py']
suite=unittest.TestSuite(unittest.defaultTestLoader.discover('server/tests',pattern=p) for p in patterns)
start=time.perf_counter();faulthandler.dump_traceback_later(90)
r=unittest.TextTestRunner(verbosity=1).run(suite);faulthandler.cancel_dump_traceback_later()
Path('docs/world-focused-tests.json').write_text(json.dumps({'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'skipped':len(r.skipped),'ok':r.wasSuccessful(),'patterns':patterns,'seconds':time.perf_counter()-start},indent=2)+'\n')
sys.exit(not r.wasSuccessful())
