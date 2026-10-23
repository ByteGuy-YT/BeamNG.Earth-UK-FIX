from pathlib import Path
p=Path('.work-uk/worker-seams.py');s=p.read_text();s=s.replace('import sys,json,time,numpy as np','import sys,json,time,argparse,numpy as np');s=s.replace("sys.path[:0]=['server'];", "ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'server')];")
s=s.replace("net=netfetch.Fetcher(offline=True);cache=str(Path.home()/'.cache/beamng-earth');md=mapdata.MapData(cache,net);dd=dem.Dem(cache+'/dem',fetcher=net)", "ap=argparse.ArgumentParser(description='Compare bridge edges built with independent tile height models.');ap.add_argument('--out',default=str(ROOT/'docs/world-seam-validation.json'));ap.add_argument('--case',action='append',default=[]);args=ap.parse_args()\nnet=netfetch.Fetcher(offline=True);cache=str(Path.home()/'.cache/beamng-earth');md=mapdata.MapData(cache,net);dd=dem.Dem(cache+'/dem',fetcher=net)\nimport seacarve\nsea=seacarve.SeaCarver(md,cache,dem=dd)")
s=s.replace('for name,lat,lon in cases:\n', 'for name,lat,lon in cases:\n if args.case and name not in args.case:continue\n')
s=s.replace('raw=lambda la,lo:dd.sample(la,lo,15)', 'raw=lambda la,lo:dd.sample(la,lo,15)\n shaped=lambda la,lo:sea.carve(la,lo,raw(la,lo))')
s=s.replace('g=grading.Grader(fr,md,raw);elev=lambda la,lo:g.apply(la,lo,raw(la,lo),.04)', 'g=grading.Grader(fr,md,raw,structure_elev=shaped);elev=lambda la,lo:g.apply(la,lo,shaped(la,lo),.04)')
s=s.replace('bp=g.bridge_model', 'bp=g.bridge_model;bp.wet=sea.depth')
s=s.replace("Path('.work-uk/worker-seams.json')", 'Path(args.out)')
Path('tools/validate_world_seams.py').write_text('"""Independent-worker bridge boundary audit. Test coordinates are not production overrides."""\n'+s)
