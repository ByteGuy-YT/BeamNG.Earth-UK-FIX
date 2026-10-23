import sys,json
sys.path.insert(0,'tools');import mcp
pos=dict(x=180.,y=-180.,z=145.)
rot=json.loads(mcp.call('run_lua',{'code':"return jsonEncode(quatFromDir(vec3(-321,330,-45),vec3(0,0,1)))"}))
print(mcp.call('set_free_camera',{'pos':pos,'rot':rot,'fov':65}))
print(mcp.call('screenshot'))
