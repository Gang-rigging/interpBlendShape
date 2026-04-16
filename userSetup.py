import sys
import os

_scripts = os.path.join(os.path.dirname(__file__), "interpBlendShape", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
