import faulthandler,runpy
faulthandler.dump_traceback_later(60,repeat=True)
runpy.run_path('tools/validate_world_geometry.py',run_name='__main__')
