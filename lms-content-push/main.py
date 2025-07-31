import sys
from pathlib import Path

# Ensure parent directory is on the import path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from main import app
