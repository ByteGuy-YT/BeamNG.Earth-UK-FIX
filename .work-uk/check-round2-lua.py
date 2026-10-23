from pathlib import Path
import sys
sys.path.insert(0,'.work-uk/lua-runtime')
from lupa.luajit21 import LuaRuntime
for name in ('cameras','navgraph','governor','trees','roads'):
    path='mod/tests/test_'+name+'.lua'
    lua=LuaRuntime()
    lua.execute('arg={[0]=...};os.exit=function(n) assert(n==0) end',path)
    lua.execute(Path(path).read_text())
