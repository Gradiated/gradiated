"""Put the gradctl source on sys.path for `python3 -m unittest discover -s tools/gradctl/tests`."""
import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[1] / 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)
