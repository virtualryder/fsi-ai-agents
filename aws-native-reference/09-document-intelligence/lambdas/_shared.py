"""Shared import shim so each Lambda can load core/strands_agent.

In a packaged deployment core.py and strands_agent.py ship in the same artifact
(or a Lambda layer); locally we add the reference root to sys.path.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
