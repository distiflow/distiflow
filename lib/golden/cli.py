import argparse
import sys
from pathlib import Path

from golden import brief, hooks, overlay, paths, profile, session
from golden.practices import STAGES


def _project() -> Path | None:
    proj = paths.project_root(Path.cwd())
    if proj is None:
        print("golden: not inside a git repository", file=sys.stderr)
    return proj


def cmd_profile_check(args) -> int:
    proj = _project()
    if proj is None:
        return 3
    try:
        root = paths.plugin_root()
        _, warnings = profile.load_for(root, proj, overlay.load_practices(root, proj)[0])
    except profile.ProfileError as e:
        for line in e.errors:
            print(line, file=sys.stderr)
        return 1
    print("profile ok")
    for line in warnings:
        print("warning: " + line)
    return 0


def cmd_override(args) -> int:
    proj = _project()
    if proj is None:
        return 3
    root = paths.plugin_root()
    if args.target == "list":
        rows = overlay.list_overrides(root, proj)
        for rel, status in rows:
            print("%s %s" % (rel, status))
        if not rows:
            print("no overrides")
        return 0
    try:
        target = overlay.make_override(args.target, root, proj)
    except overlay.OverrideError as e:
        print("golden: " + str(e), file=sys.stderr)
        return 1
    print("wrote %s; edit it, the header records the upstream it shadows" % target.relative_to(proj))
    return 0


def cmd_brief(args) -> int:
    proj = _project()
    if proj is None:
        return 3
    try:
        text, _ = brief.build_brief(paths.plugin_root(), proj, args.stage, args.kind)
    except profile.ProfileError as e:
        for line in e.errors:
            print(line, file=sys.stderr)
        return 1
    except brief.UnknownKind as e:
        print("golden: %s" % e, file=sys.stderr)
        return 2
    print(text, end="")
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
    br = sub.add_parser("brief", help="print the brief for one stage")
    br.add_argument("--stage", required=True, choices=STAGES)
    br.add_argument("--kind", required=True)
    ovr = sub.add_parser("override", help="copy an upstream file to .golden/overrides, or: override list")
    ovr.add_argument("target", help="path under core/, or 'list'")
    args = parser.parse_args(argv)

    if args.cmd == "profile":
        return cmd_profile_check(args)
    if args.cmd == "brief":
        return cmd_brief(args)
    if args.cmd == "override":
        return cmd_override(args)
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
