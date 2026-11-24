import json
from pathlib import Path


def holder(task_dir: Path) -> dict | None:
    try:
        data = json.loads((task_dir / "claim").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("session"), str) else None


def holds(task_dir: Path, session: str) -> bool:
    h = holder(task_dir)
    return h is not None and h["session"] == session
