import sys,runpy
sys.path[:0]=['server'];import grading
grading.Grader._global_approaches=lambda *a:None
sys.argv=['validate_uk_motorways.py','--out','.work-uk/m1-without-global.json']
runpy.run_path('tools/validate_uk_motorways.py',run_name='__main__')
