"""
Make `backend` importable however pytest was invoked.

Without this the suite only collects when pytest runs from
cta-delay-predictor/, which is a trap: running it from the repo root gives a
collection error that reads like a broken test rather than a wrong directory.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
