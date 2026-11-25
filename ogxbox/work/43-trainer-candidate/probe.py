import importlib.util
import sys
print(sys.executable)
print({x: bool(importlib.util.find_spec(x)) for x in ('unicorn','elftools','capstone')})
