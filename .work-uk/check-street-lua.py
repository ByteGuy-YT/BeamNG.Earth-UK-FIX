from pathlib import Path
import sys
sys.path.insert(0,'.work-uk/lua-runtime')
from lupa.luajit21 import LuaRuntime
for path in ['mod/beamng_earth/lua/ge/extensions/beamngEarth/cameras.lua','mod/beamng_earth/lua/ge/extensions/beamngEarth/navgraph.lua','mod/beamng_earth/lua/ge/extensions/beamngEarth/trees.lua','mod/beamng_earth/lua/ge/extensions/beamngEarth/roads.lua']:
 lua=LuaRuntime();lua.execute("assert(loadstring(...))",Path(path).read_text());print('Lua syntax OK',path)
for path in ['mod/tests/test_cameras.lua','mod/tests/test_navgraph.lua']:
 lua=LuaRuntime();lua.execute("arg={[0]=...};os.exit=function(n) assert(n==0,'test failed') end",path)
 lua.execute(Path(path).read_text())
