import json,sys
from pathlib import Path
root=Path.cwd()
before=json.loads((root/'.work-uk/street-benchmark-round2-before.json').read_text())
after=json.loads((root/'.work-uk/street-benchmark-round2-after.json').read_text())
rows=[]
for a,b in zip(before,after):
    assert a['site']==b['site']
    rows.append({'site':a['site'],'before':a,'after':b,
                 'generation_change_percent':round(100*(b['warm_median_ms']/a['warm_median_ms']-1),2)})
result={'date':'2026-10-21','kind':'CPU road-tile generation, flat elevation; NOT FPS',
        'method':'6 measured warm repeats after 2 warmups per site, previous source snapshot then current source, same machine, road/context data and current width configuration. No running-game renderer or physics included.',
        'engine_frame_times_measured':False,
        'limits':['Single local run; small changes may be measurement noise.',
                  'Geometry and detail content differ between versions.',
                  'Actual DEM grading and cold neighbouring-profile preparation cost is reported separately in uk-round2-validation.json.'],
        'streaming_changes':{'driving_target_ms':[4,2],'engine_free_ms':[5,2],
                             'forest_items_per_active_batch':[750,300],'shape_population_budget':[4000,2000]},
        'sites':rows}
(root/'docs/uk-round2-performance.json').write_text(json.dumps(result,indent=2)+'\n')
doc=(root/'docs/UK_ROUND2_FIXES.md').read_text(encoding='utf-8')
names=[p.name for p in Path('C:/Users/topge/Downloads/compressedImages(2)').glob('*.png')]
missing=[n for n in names if n not in doc]
assert not missing,missing
assert len(names)==14,len(names)
sys.path.insert(0,str(root/'tools'))
import package
paths=package.collect()
assert 'server/ukvertical.py' in paths and 'docs/UK_ROUND2_FIXES.md' in paths
audit=json.loads((root/'docs/uk-round2-validation.json').read_text())
assert len(audit)==6
assert next(s for s in audit if s['site']=='J27')['roundabout_reverse_lanes']==0
print('All 14 image filenames covered; six real-data sites passed; package includes new code/assets/reports.')
print(json.dumps([{k:r[k] for k in ('site','generation_change_percent')} for r in rows]))
