-- Mapped fixed cameras use the game's event-driven gameplay_speedTraps logic.
-- No vehicle polling, extra physics objects or projected flash lights.
local M = {}
local live = {}
local lights = {}
M.MAX_TRIGGERS = 32

function M.clear()
  for _, id in pairs(live) do
    local o = scenetree.findObjectById(id)
    if o then o:delete() end
  end
  live = {}
  for _, id in pairs(lights) do local o = scenetree.findObjectById(id) if o then o:delete() end end
  lights = {}
end

function M.sync(rows, box, anchor)
  local keep, count = {}, 0
  if extensions and not gameplay_speedTraps then pcall(extensions.load, 'gameplay_speedTraps') end
  for _, c in ipairs(rows or {}) do
    local p, d = c.point, c.dir
    if c.limit and c.limit > 0 and p and d and (not box or
      (p[1] > box[1] + 20 and p[1] < box[3] - 20 and p[2] > box[2] + 20 and p[2] < box[4] - 20)) and count < M.MAX_TRIGGERS then
      local key = tostring(anchor) .. ':' .. c.id
      count = count + 1
      keep[key] = true
      if not live[key] or not scenetree.findObjectById(live[key]) then
        local o = createObject('BeamNGTrigger')
        o.loadMode = 1 -- required for dynamically created triggers, as stock rectMarker
        o:setField('triggerType', 0, 'Box')
        o:setField('luaFunction', 0, 'onBeamNGTrigger')
        o:setField('speedTrapType', 0, 'speed')
        o:setField('speedLimit', 0, tostring(c.limit)) -- metres per second, as stock level triggers
        o:registerObject('bne_camera_' .. tostring(anchor) .. '_' .. c.id:gsub('[^%w]', '_'))
        local rot = quatFromDir(vec3(d[1], d[2], 0), vec3(0, 0, 1))
        o:setPosRot(p[1], p[2], p[3] + 2, rot.x, rot.y, rot.z, rot.w)
        o:setScale(vec3(math.min(22, c.width or 6), 6, 6))
        if c.pos then
          local lamp = createObject('PointLight')
          lamp:setField('color', 0, '1 1 0.95 1')
          lamp:setField('brightness', 0, '8')
          lamp:setField('radius', 0, '12')
          lamp:setField('castShadows', 0, '0')
          lamp.isEnabled = false
          local name = 'bne_camera_flash_' .. tostring(anchor) .. '_' .. c.id:gsub('[^%w]', '_')
          lamp:registerObject(name)
          lamp:setPosRot(c.pos[1], c.pos[2], c.pos[3] + (c.motorway and 6.5 or 3.5), 0,0,0,1)
          if scenetree.MissionGroup then scenetree.MissionGroup:addObject(lamp) end
          o:setField('speedTrapLightName', 0, name)
          lights[key] = lamp:getID()
        end
        if scenetree.MissionGroup then scenetree.MissionGroup:addObject(o) end
        live[key] = o:getID()
      end
    end
  end
  for key, id in pairs(live) do
    if not keep[key] then
      local o = scenetree.findObjectById(id)
      if o then o:delete() end
      local lamp = lights[key] and scenetree.findObjectById(lights[key])
      if lamp then lamp:delete() end
      lights[key] = nil
      live[key] = nil
    end
  end
end

return M
