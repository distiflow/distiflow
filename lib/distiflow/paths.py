import json
import os
import subprocess
from pathlib import Path


def plugin_root() -> Path:
    env = os.environ.get("DISTIFLOW_ROOT")
    return Path(env) if env else Path(__file__).resolve().parents[2]


def version(root: Path) -> str:
    return json.loads((root / ".claude-plugin" / "plugin.json").read_text())["version"]


def find_project(cwd: Path) -> Path | None:
    """The project holding .distiflow/ around cwd; a task worktree dir <x>.distiflow/<id> maps back to <x>. No git."""
    cwd = Path(cwd).absolute()
    chain = (cwd, *cwd.parents)
    # Worktree mapping first: a worktree holds its own checked-out .distiflow/ with the committed profile.
    for d in chain[1:]:
        if d.name.endswith(".distiflow") and d.name != ".distiflow":
            main = d.with_name(d.name[: -len(".distiflow")])
            if (main / ".distiflow" / "tasks" / cwd.relative_to(d).parts[0]).is_dir():
                return main
    return next((d for d in chain if (d / ".distiflow").is_dir()), None)


def project_root(start: Path) -> Path | None:
    """The main checkout of the git repo around start, also when start is inside a linked worktree."""
    r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                       cwd=start, capture_output=True, text=True)
    if r.returncode != 0:
        return None
    common = Path(r.stdout.strip())
    return common.parent if common.name == ".git" else None
