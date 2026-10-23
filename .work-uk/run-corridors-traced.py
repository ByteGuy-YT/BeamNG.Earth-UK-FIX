import faulthandler,sys,runpy
faulthandler.dump_traceback_later(60,repeat=True)
sys.argv=['tools/validate_road_corridors.py',*sys.argv[1:]]
runpy.run_path(sys.argv[0],run_name='__main__')
