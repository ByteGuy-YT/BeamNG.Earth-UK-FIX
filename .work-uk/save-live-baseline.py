import sys,json
from pathlib import Path
sys.path.insert(0,'tools');import mcp
snap={'camera':json.loads(mcp.call('get_camera_state')),
      'state':json.loads(mcp.call('run_lua',{'code':'local s=require("beamngEarth/core")._state(); return jsonEncode({player=s.player,anchor=s.anchorId,session=s.sessionId})'})),
      'metrics':json.loads(mcp.call('get_performance_metrics'))}
Path('.work-uk/j27-before-live.json').write_text(json.dumps(snap,indent=2));print('saved live baseline')
