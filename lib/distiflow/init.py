import tomllib
from pathlib import Path

from distiflow import fsutil, profile, signals, toml_write

GITIGNORE = "tasks/\ncontrib/\nprofile.local.toml\n"


class InitError(Exception):
    pass


def proposal(root: Path, project: Path) -> dict:
    return {"project": {"name": project.name, "signals": signals.detect_signals(project, root), "deny_terms": []},
            "commands": signals.detect_commands(project),
            "git": {"worktrees": True, "push": "allowed", "base": signals.detect_base(project)},
            "glossary": {}}


def _saved_path(project: Path) -> Path:
    return project / ".distiflow" / profile.COMMITTED


def propose(root: Path, project: Path) -> str:
    """Never writes. Without a profile: a proposal; with one: the saved file and what detection sees differently."""
    new = proposal(root, project)
    if not _saved_path(project).is_file():
        return toml_write.dumps(new)
    text = _saved_path(project).read_text(encoding="utf-8")
    saved = tomllib.loads(text)
    lines = ["- signal " + d for d in signals.drift(saved.get("project", {}).get("signals", []),
                                                     new["project"]["signals"])]
    old_cmds, new_cmds = saved.get("commands", {}), new["commands"]
    q = lambda v: '"%s"' % v if v is not None else "none"
    for name in sorted(set(old_cmds) | set(new_cmds)):
        if old_cmds.get(name) != new_cmds.get(name):
            lines.append("- command %s: saved %s detected %s" % (name, q(old_cmds.get(name)), q(new_cmds.get(name))))
    return text + ("" if text.endswith("\n") else "\n") + "\n## Differences\n" + ("\n".join(lines) or "- none") + "\n"


def _leaves(d: dict, prefix: str = "") -> set[str]:
    out = set()
    for k, v in d.items():
        path = prefix + k
        if isinstance(v, dict) and v:
            out |= _leaves(v, path + ".")
        else:
            # A list item that disappears is a removal too: deny_terms must never shrink silently.
            out |= {path} | ({"%s=%s" % (path, x) for x in v if isinstance(x, str)} if isinstance(v, list) else set())
    return out


def write(root: Path, project: Path, text: str, allow_removal: bool) -> str:
    profile.check_text(text, root, project)
    saved = _saved_path(project)
    if saved.is_file():
        gone = sorted(_leaves(tomllib.loads(saved.read_text(encoding="utf-8"))) - _leaves(tomllib.loads(text)))
        if gone and not allow_removal:
            raise InitError("this would remove %s from the saved profile; rerun with --allow-removal to drop them"
                            % ", ".join(gone))
    saved.parent.mkdir(exist_ok=True)
    fsutil.atomic_write(saved, text)
    try:
        fsutil.create_exclusive(saved.parent / ".gitignore", GITIGNORE)
    except FileExistsError:
        pass
    return "wrote .distiflow/profile.toml\nif .distiflow is not committed, add .distiflow/ to .git/info/exclude\n"
