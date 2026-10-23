import sys,json,time,math
from pathlib import Path
sys.path.insert(0,'tools');import mcp
out=Path('.work-uk/stutter-lean');out.mkdir(exist_ok=True)
def lua(code):return mcp.call('run_lua',{'code':code})
POLL='''local pm=beamngEarth_perfmon;pm.tagHarness();local c=require("beamngEarth/core");local s=c._state();local p=s.player;local r=require("beamngEarth/roads");local v=getPlayerVehicle(0);local o=map.objects[v:getId()];local speed=math.sqrt((p.vx or 0)^2+(p.vy or 0)^2);local hx,hy=0,1;if speed>1 then hx,hy=p.vx/speed,p.vy/speed end;local a=r.ahead(p.x,p.y,hx,hy,1400);return jsonEncode({perf=pm.snapshot(),hitches=c.hitches(),player=p,guard=c.roadGuardState(),roads=r.status(),ahead=a,damage=o and o.damage,backlog=s.serverBacklog})'''
rows=[]
lua('extensions.load("beamngEarth_perfmon");beamngEarth_perfmon.snapshot();return "sampling"')
try:
 for phase,seconds in [('stationary',20),('driving',90)]:
  if phase=='driving':
   lua('require("beamngEarth/settings").uiMapGps(53.074,-1.294,"streaming test");getPlayerVehicle(0):queueLuaCommand([[input.event("parkingbrake",0,1)]]);require("beamngEarth/settings").uiGpsAutodrive(true);return "driving"')
  start=time.monotonic()
  with (out/(phase+'.jsonl')).open('w') as f:
   while time.monotonic()-start<seconds:
    time.sleep(2)
    row=json.loads(lua(POLL));row.update(phase=phase,seconds=time.monotonic()-start);rows.append(row)
    f.write(json.dumps(row)+'\n');f.flush()
    if len(rows)%5==0:print(json.dumps({'phase':phase,'s':round(row['seconds']),'speed':row['player'].get('speed'),'p99':row['perf']['p99'],'max':row['perf']['maxMs'],'over50':row['perf']['over50'],'holds':row['guard'].get('holds')}),flush=True)
    if row.get('damage',0)>2000:break
finally:
 lua('require("beamngEarth/settings").uiGpsAutodrive(false);getPlayerVehicle(0):queueLuaCommand([[ai.setMode("stop")]]);return "stopping"')
 time.sleep(4);mcp.call('set_ai',{'mode':'disabled'})
 lua('getPlayerVehicle(0):queueLuaCommand([[input.event("parkingbrake",1,1)]]);require("beamngEarth/settings").uiMapGps(nil);return "manual"')
summary={}
for phase in ('stationary','driving'):
 rr=[r for r in rows if r['phase']==phase];p=[r['perf'] for r in rr];frames=sum(x['frames'] for x in p)
 summary[phase]={'frames':frames,'mean_ms':sum(x['avgMs']*x['frames'] for x in p)/max(frames,1),'max_ms':max((x['maxMs'] for x in p),default=0),'over33':sum(x['over33'] for x in p),'over50':sum(x['over50'] for x in p),'over100':sum(x['over100'] for x in p),'max_damage':max((r.get('damage',0) for r in rr),default=0),'holds_added':(rr[-1]['guard'].get('holds',0)-rr[0]['guard'].get('holds',0)) if rr else None,'paused_polls':sum(bool(r['guard'].get('pausedByUs')) for r in rr),'distance_m':sum(math.hypot(a['player']['x']-b['player']['x'],a['player']['y']-b['player']['y']) for a,b in zip(rr,rr[1:]))}
(out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)

