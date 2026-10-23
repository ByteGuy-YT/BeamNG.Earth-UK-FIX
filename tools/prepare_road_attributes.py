"""Prepare an optional, offline OSM attribute index for any region.

The running tile builder never requests Overpass. Geometry and connector IDs
remain Overture's; only unambiguous source-way tag matches are used.
"""
import argparse,json,urllib.request,urllib.parse,hashlib
from pathlib import Path
from prepare_uk_roads import build

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bounds',nargs=4,type=float,metavar=('SOUTH','WEST','NORTH','EAST'),required=True)
    ap.add_argument('--output',default='.road-data/osm-extra.sqlite')
    args=ap.parse_args();s,w,n,e=args.bounds
    if not (-90<=s<n<=90 and -180<=w<e<=180) or (n-s)*(e-w)>.04:
        ap.error('Use a regional bounding box no larger than 0.04 square degrees.')
    out=Path(args.output).resolve();out.parent.mkdir(parents=True,exist_ok=True)
    query=f'[out:xml][timeout:90];way["highway"]({s},{w},{n},{e});(._;>;);out body;'
    body=urllib.parse.urlencode({'data':query}).encode()
    req=urllib.request.Request('https://overpass-api.de/api/interpreter',body,headers={'User-Agent':'BeamNG.Earth regional road attribute preparation'})
    with urllib.request.urlopen(req,timeout=120) as response:data=response.read()
    xml=out.with_suffix('.osm');xml.write_bytes(data);build([xml],out)
    manifest={'bounds':args.bounds,'url':'https://overpass-api.de/api/interpreter','query':query,
              'sha256':hashlib.sha256(data).hexdigest(),'licence':'ODbL 1.0','attribution':'© OpenStreetMap contributors'}
    out.with_suffix('.source.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':main()
