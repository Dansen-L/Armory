"""Project-level pytest configuration.

Ensures the .venv site-packages are on sys.path so packages installed
there (textual, rapidfuzz, anthropic, pyperclip) are importable even
when pytest is invoked via the system Python rather than the venv
interpreter.  This lets the two TUI headless pilot tests run rather
than skip in any standard invocation.
"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent
_VENV = _PROJECT_ROOT / ".venv"

if _VENV.exists():
    for _sp in sorted(_VENV.glob("lib/python*/site-packages")):
        _sp_str = str(_sp)
        if _sp_str not in sys.path:
            sys.path.insert(0, _sp_str)
