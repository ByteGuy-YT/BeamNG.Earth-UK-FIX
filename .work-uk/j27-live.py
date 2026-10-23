import sys,json
from pathlib import Path
sys.path.insert(0,'tools');import mcp
code="""local out={signals={},edges={}}; local d=core_trafficSignals.getData(true); local ns=map.getMap().nodes
for _,s in pairs(d.instances or {}) do local a={name=s.name,pos=s.pos,dir=s.dir,heads={}} for _,id in ipairs(s.linkedObjects or {}) do local o=scenetree.findObjectById(id);if o then local m=o:getTransform();a.heads[#a.heads+1]={front=m:getColumn(1),pos=o:getPosition()} end end out.signals[#out.signals+1]=a end
for n,a in pairs(ns) do if a.pos.x*a.pos.x+a.pos.y*a.pos.y<40000 then for nb,e in pairs(a.links or {}) do if n<nb then out.edges[#out.edges+1]={a=n,b=nb,p=a.pos,q=ns[nb].pos,oneWay=e.oneWay,inNode=e.inNode,outNode=e.outNode} end end end end
return jsonEncode(out)"""
r=json.loads(mcp.call('run_lua',{'code':code}));Path('.work-uk/j27-live.json').write_text(json.dumps(r,indent=2))
for s in r['signals']:print(s)
print('graph edges',len(r['edges']))
