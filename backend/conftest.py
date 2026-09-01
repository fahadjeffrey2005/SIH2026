"""Puts backend/ itself on sys.path so `from app.main import app` resolves
regardless of where pytest is invoked from -- mirrors pipeline/conftest.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
