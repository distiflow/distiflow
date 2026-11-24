import json
import os
from pathlib import Path


def plugin_root() -> Path:
    env = os.environ.get("GOLDEN_ROOT")
    return Path(env) if env else Path(__file__).resolve().parents[2]


def version(root: Path) -> str:
    return json.loads((root / ".claude-plugin" / "plugin.json").read_text())["version"]
