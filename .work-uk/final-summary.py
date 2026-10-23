from pathlib import Path
import json
r=json.loads(Path('docs/world-geometry-validation.json').read_text())
print(json.dumps({'cases':len(r),'passed':sum(v['ok'] for v in r),'checked_road_clearances':sum(v.get('checked_road_clearances',0) for v in r),'connected_junctions':sum(v.get('connected_junctions',0) for v in r),'max_deck_grade':max(v.get('max_deck_grade',0) for v in r)},indent=2))
