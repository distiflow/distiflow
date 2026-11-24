import json
import re
from pathlib import Path

from golden import overlay
from golden.worktree import git

COMMANDS = ("test", "lint", "build", "typecheck")


def _glob_re(pattern: str) -> re.Pattern:
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        else:
            out += {"*": "[^/]*", "?": "[^/]"}.get(pattern[i], re.escape(pattern[i]))
            i += 1
    return re.compile(out + r"\Z")


def detect_signals(project: Path, root: Path) -> list[str]:
    files = git("ls-files", "--cached", "--others", "--exclude-standard", cwd=project).stdout.splitlines()
    table = overlay.load_toml("signals.toml", root, project)[0].get("signals", {})
    found = []
    for name, spec in table.items():
        res = [_glob_re(g) for g in spec.get("files", [])]
        if any(r.match(f) for f in files for r in res):
            found.append(name)
    return sorted(found)


def detect_commands(project: Path) -> dict[str, str]:
    cmds = {}
    try:
        scripts = json.loads((project / "package.json").read_text(encoding="utf-8")).get("scripts", {})
    except (OSError, ValueError, AttributeError):
        scripts = None
    runner = "pnpm run" if (project / "pnpm-lock.yaml").exists() else "npm run"
    for name in COMMANDS:
        if isinstance(scripts, dict) and name in scripts:
            cmds[name] = "%s %s" % (runner, name)
    try:
        makefile = (project / "Makefile").read_text(encoding="utf-8")
    except OSError:
        makefile = None
    for name in COMMANDS:
        if makefile and name not in cmds and re.search(r"^%s\s*:" % name, makefile, re.M):
            cmds[name] = "make " + name
    if scripts is None and makefile is None and (project / "pyproject.toml").exists():
        cmds["test"] = "python3 -m unittest"
    return cmds


def detect_base(project: Path) -> str:
    head = git("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", cwd=project).stdout.strip()
    if head.startswith("origin/"):
        return head[len("origin/"):]
    return git("branch", "--show-current", cwd=project).stdout.strip() or "main"


def drift(saved: list[str], detected: list[str]) -> list[str]:
    return ["+" + s for s in detected if s not in saved] + ["-" + s for s in saved if s not in detected]
