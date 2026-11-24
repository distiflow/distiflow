import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from distiflow import fsutil

SCHEMA = 1
STATUSES = ("active", "awaiting-merge", "cleanup-pending", "done", "abandoned")
_DEFAULTS = {"schema": SCHEMA, "kind": None, "desc": "", "created": None, "status": "active",
             "stage": "understand", "mode": "worktree", "branch": None, "worktree": None, "base": None,
             "links": [], "decisions": [], "open_items": [], "runs": []}


class StateError(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run(stage: str, n: int, version: str, session: str, gates: list[dict]) -> dict:
    return {"stage": stage, "n": n, "version": version, "session": session, "started": now(), "ended": None,
            "gates": gates, "evidence": {}}


def new(task_id: str, kind: str, desc: str, version: str, session: str, gates: list[dict]) -> dict:
    st = copy.deepcopy(_DEFAULTS)
    st.update(id=task_id, kind=kind, desc=desc, created=now(),
              runs=[new_run("understand", 1, version, session, gates)])
    return st


def load(task_dir: Path) -> dict:
    data = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
    if data.get("schema", SCHEMA) > SCHEMA:
        raise StateError("task %s was written by a newer distiflow (schema %s); update distiflow"
                         % (data.get("id", task_dir.name), data["schema"]))
    return {**copy.deepcopy(_DEFAULTS), **data}


def save(task_dir: Path, st: dict) -> None:
    fsutil.atomic_write(task_dir / "state.json", json.dumps(st, indent=2, ensure_ascii=False) + "\n")


def mutate(task_dir: Path, session: str, fn) -> dict:
    from distiflow import claim  # claim imports state for timestamps
    with fsutil.locked(task_dir / "lock"):
        if not claim.holds(task_dir, session):
            raise StateError("you do not hold task %s" % task_dir.name)
        st = load(task_dir)
        fn(st)
        save(task_dir, st)
    return st
