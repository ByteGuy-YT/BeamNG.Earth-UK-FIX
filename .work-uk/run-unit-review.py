import sys,unittest,time
sys.path[:0]=['server','server/tests'];suite=unittest.defaultTestLoader.discover('server/tests')
def leaves(s):
 for t in s:
  if isinstance(t,unittest.TestSuite):yield from leaves(t)
  else:yield t
skip={'test_integration_drive','test_e2e','test_modsim'}
tests=unittest.TestSuite(t for t in leaves(suite) if t.__class__.__module__ not in skip)
with open('.work-uk/unit-review.log','w') as f:
 result=unittest.TextTestRunner(stream=f,verbosity=2).run(tests)
 print('tests',result.testsRun,'failures',len(result.failures),'errors',len(result.errors),'skipped',len(result.skipped),flush=True)
 for t,e in result.failures+result.errors:print(t.id(),e[-1800:],flush=True)
sys.exit(not result.wasSuccessful())
