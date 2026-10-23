local c=require('beamngEarth/core')
local s=c._state()
local simple={}
for k,v in pairs(s) do if type(v)=='number' or type(v)=='string' or type(v)=='boolean' then simple[k]=v end end
simple.anchor=s.anchor
local p=be:getPlayerVehicle(0)
return jsonEncode({status=c.status(),state=simple,camera=core_camera.getPosition(),player=p and p:getPosition()})
