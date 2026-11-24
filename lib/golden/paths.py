import json
import os
import subprocess
from pathlib import Path


def plugin_root() -> Path:
    env = os.environ.get("GOLDEN_ROOT")
    return Path(env) if env else Path(__file__).resolve().parents[2]


def version(root: Path) -> str:
    return json.loads((root / ".claude-plugin" / "plugin.json").read_text())["version"]


def find_project(cwd: Path) -> Path | None:
    """The project holding .golden/ around cwd; a task worktree dir <x>.golden/<id> maps back to <x>. No git."""
    cwd = Path(cwd).absolute()
    for d in (cwd, *cwd.parents):
        if (d / ".golden").is_dir():
            return d
        if d.name.endswith(".golden") and d != cwd:
            main = d.with_name(d.name[: -len(".golden")])
            child = cwd.relative_to(d).parts[0]
            if (main / ".golden" / "tasks" / child).is_dir():
                return main
    return None


def project_root(start: Path) -> Path | None:
    """The main checkout of the git repo around start, also when start is inside a linked worktree."""
    r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                       cwd=start, capture_output=True, text=True)
    if r.returncode != 0:
        return None
    common = Path(r.stdout.strip())
    return common.parent if common.name == ".git" else None
