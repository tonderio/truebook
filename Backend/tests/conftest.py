"""Pytest configuration.

Adds the Backend/ directory to sys.path so tests can `from app.services …`
without a package install. Mirrors what scripts/ does.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
