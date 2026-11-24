import argparse
import sys
from pathlib import Path

from golden import hooks, overlay, paths, profile, session


def _project() -> Path | None:
    proj = paths.project_root(Path.cwd())
    if proj is None:
        print("golden: not inside a git repository", file=sys.stderr)
    return proj


def load_profile_for(root: Path, project: Path):
    practices, _ = overlay.load_practices(root, project)
    upstream, _ = overlay.load_practices(root, None)
    models, _ = overlay.load_toml("models.toml", root, project)
    return profile.load_profile(project, practices, roles=tuple(models.get("roles", {})),
                                upstream_gates=frozenset(p.id for p in upstream if p.gate))


def cmd_profile_check(args) -> int:
    proj = _project()
    if proj is None:
        return 3
    try:
        _, warnings = load_profile_for(paths.plugin_root(), proj)
    except profile.ProfileError as e:
        for line in e.errors:
            print(line, file=sys.stderr)
        return 1
    print("profile ok")
    for line in warnings:
        print("warning: " + line)
    return 0


def main(argv: list[str]) -> int:
    argv, flag = session.extract_session_flag(argv)
    parser = argparse.ArgumentParser(prog="golden")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("whoami", help="print the session id golden sees")
    hook = sub.add_parser("hook", help="run a Claude Code hook")
    hook.add_argument("name")
    prof = sub.add_parser("profile", help="profile commands").add_subparsers(dest="sub", required=True)
    prof.add_parser("check", help="validate .golden/profile.toml and profile.local.toml")
    args = parser.parse_args(argv)

    if args.cmd == "profile":
        return cmd_profile_check(args)
    if args.cmd == "hook":
        return hooks.run(args.name)
    if args.cmd == "whoami":
        sid = session.current_session(flag)
        if not sid:
            print("golden: no session id", file=sys.stderr)
            return 3
        print("session=%s source=%s" % (sid, "flag" if flag is not None else "env"))
        return 0
    return 2
