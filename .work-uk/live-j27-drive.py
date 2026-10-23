import sys,json,time,math
from pathlib import Path
sys.path.insert(0,'tools');import mcp
out=Path('.work-uk/live-j27-drive');out.mkdir(exist_ok=True)
def lua(code):return mcp.call('run_lua',{'code':code})
def snap():
 return json.loads(lua('''local c=require("beamngEarth/core");local s=c._state();local v=getPlayerVehicle(0);local o=map.objects[v:getId()];return jsonEncode({player=s.player,guard=c.roadGuardState(),gps=require("beamngEarth/gps").status(),damage=o and o.damage,roads=require("beamngEarth/roads").status(),backlog=s.serverBacklog})'''))
before={'state':snap(),'camera':json.loads(mcp.call('get_camera_state'))}
(out/'before.json').write_text(json.dumps(before,indent=2))
rows=[]
try:
 lua('return jsonEncode(require("beamngEarth/settings").uiGpsAutodrive(true))')
 start=time.monotonic()
 with (out/'samples.jsonl').open('w') as f:
  while time.monotonic()-start<90:
   row=snap();row['seconds']=time.monotonic()-start
   if len(rows)%5==0:row['performance']=json.loads(mcp.call('get_performance_metrics'))
   rows.append(row);f.write(json.dumps(row)+'\n');f.flush()
   if len(rows)%10==0:print(json.dumps({'seconds':round(row['seconds']),'speed':row['player'].get('speed'),'guard':row['guard'],'remaining':(row.get('gps') or {}).get('remaining')}),flush=True)
   if row.get('damage',0)>2000:break
   time.sleep(1)
finally:
 lua('require("beamngEarth/settings").uiGpsAutodrive(false);getPlayerVehicle(0):queueLuaCommand([[ai.setMode("stop")]]);return "stopping"')
 time.sleep(4)
 mcp.call('set_ai',{'mode':'disabled'})
 lua('getPlayerVehicle(0):queueLuaCommand([[input.event("parkingbrake",1,1)]]);return "manual"')
 lua('require("beamngEarth/settings").uiMapGps(nil);return "cleared"')
dist=sum(math.hypot(a['player']['x']-b['player']['x'],a['player']['y']-b['player']['y']) for a,b in zip(rows,rows[1:]))
summary={'seconds':rows[-1]['seconds'] if rows else 0,'distance_m':dist,'max_speed_ms':max((r['player'].get('speed',0) for r in rows),default=0),'max_damage':max((r.get('damage',0) for r in rows),default=0),'guard_holds_before':before['state']['guard'].get('holds',0),'guard_holds_after':rows[-1]['guard'].get('holds',0) if rows else None,'paused_polls':sum(bool(r['guard'].get('pausedByUs')) for r in rows),'screenshot':mcp.call('screenshot')}
(out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
