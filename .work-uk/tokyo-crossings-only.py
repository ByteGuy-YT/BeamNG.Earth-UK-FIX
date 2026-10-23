import sys,runpy
sys.path[:0]=['server'];import roads
roads._deck_stacks=lambda *a,**k:[]
sys.argv=['validate_world_geometry.py','--offline','--water','--case','tokyo','--out','.work-uk/tokyo-crossings-only.json']
runpy.run_path('tools/validate_world_geometry.py',run_name='__main__')
