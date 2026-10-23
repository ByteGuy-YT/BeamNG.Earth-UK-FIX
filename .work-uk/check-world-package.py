import zipfile,hashlib,json
from pathlib import Path
p=Path('dist/world-geometry-review/BeamNG.Earth-1.5.4.zip')
with zipfile.ZipFile(p) as z:
 assert z.testzip() is None
 for f in ('server/roads.py','server/grading.py','server/terrain_surface.py','server/ukvertical.py','server/osm_enrich.py','docs/world-geometry-validation.json'):
  assert z.read('BeamNG.Earth-1.5.4/'+f)==Path(f).read_bytes(),f
print(json.dumps({'zip':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'integrity':'passed'},indent=2))
