local T = dofile((arg[0]:match('^(.*)[/\\]') or '.') .. '/testlib.lua')
local objects, made, removed, nextId = {}, 0, 0, 1
function vec3(x,y,z) return {x=x,y=y,z=z} end
function quatFromDir(d,up) return {x=0,y=0,z=0,w=1} end
scenetree = {findObjectById=function(id) return objects[id] end, MissionGroup={addObject=function() end}}
gameplay_speedTraps = {}
function createObject(cls)
  T.check(cls=='BeamNGTrigger' or cls=='PointLight','use stock engine classes')
  local o={fields={},id=nextId,cls=cls};nextId=nextId+1;made=made+1
  function o:setField(k,_,v) self.fields[k]=v end
  function o:registerObject(name) self.name=name;objects[self.id]=self end
  function o:getID() return self.id end
  function o:setPosRot(x,y,z,...) self.pos={x,y,z} end
  function o:setScale(v) self.scale=v end
  function o:delete() objects[self.id]=nil;removed=removed+1 end
  return o
end
local C=require('beamngEarth/cameras')
local a={id='n123',point={50,50,10},dir={1,0},limit=13.4112,width=6.5}
local unknown={id='n124',point={60,50,10},dir={1,0},width=6.5}
C.sync({a,unknown},{0,0,200,200},1)
T.check(made==1,'unknown direction/limit creates no enforcement')
local o=objects[1]
T.check(o.loadMode==1,'dynamic trigger uses the stock load mode before registration')
T.check(o.fields.luaFunction=='onBeamNGTrigger' and o.fields.speedTrapType=='speed','stock speed-trap hook')
T.check(tonumber(o.fields.speedLimit)==13.4112,'speed is metres per second')
T.check(o.scale.x==6.5 and o.scale.y==6,'bounded trigger over the driving width')
C.sync({a},{0,0,200,200},1)
T.check(made==1 and removed==0,'unchanged graph reuses its trigger')
C.sync({a},{0,0,200,200},2)
T.check(made==2 and removed==1,'new anchor drops old-world triggers')
C.sync({a},{100,100,300,300},2)
T.check(removed==2,'outside the physics block is removed')
local many={}
for i=1,60 do many[i]={id='n'..i,point={50,50,10},dir={1,0},limit=10,width=6} end
C.sync(many,{0,0,200,200},3)
local n=0;for _ in pairs(objects) do n=n+1 end
T.check(n==C.MAX_TRIGGERS,'live triggers are capped')
C.clear()
T.check(next(objects)==nil,'teleport/reset removes every trigger')
a.pos={50,60,10}
C.sync({a},{0,0,200,200},4)
local trigger,lamp
for _,obj in pairs(objects) do if obj.cls=='BeamNGTrigger' then trigger=obj else lamp=obj end end
T.check(trigger and lamp and trigger.fields.speedTrapLightName==lamp.name,'stock callback owns flash light')
T.check(lamp and lamp.isEnabled==false and lamp.fields.castShadows=='0','flash has no idle light or shadow cost')
C.clear()
T.check(next(objects)==nil,'flash light also cleaned up')
T.done('test_cameras')
