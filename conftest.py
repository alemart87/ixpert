"""Conftest a nivel root: garantiza que el directorio del proyecto esta en sys.path
para que `from iterum.X import Y` funcione desde cualquier test.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
