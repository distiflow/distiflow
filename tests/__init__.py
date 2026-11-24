import sys
from pathlib import Path

# Unit-level tests import the package the CLI runs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
