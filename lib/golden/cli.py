import argparse
import sys
from pathlib import Path

from golden import brief, check, contrib, hooks, init, overlay, paths, profile, scan, session, state, task
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


def cmd_init(args) -> int:
    proj = _project()
    if proj is None:
        return 3
    root = paths.plugin_root()
    if args.propose:
        print(init.propose(root, proj), end="")
        return 0
    try:
        print(init.write(root, proj, sys.stdin.read(), args.allow_removal), end="")
    except profile.ProfileError as e:
        for line in e.errors:
            print(line, file=sys.stderr)
        return 1
    except init.InitError as e:
        print("golden: %s" % e, file=sys.stderr)
        return 1
    return 0


def cmd_contrib(args) -> int:
    proj = _project()
    if proj is None:
        return 3
    root = paths.plugin_root()
    try:
        if args.sub == "new":
            print(contrib.new(proj, " ".join(args.idea)), end="")
        elif args.sub == "check":
            text, passed = contrib.check(root, proj, args.slug)
            print(text, end="")
            return 0 if passed else 1
        elif args.sub == "confirm":
            print(contrib.confirm(root, proj, args.slug, args.verdict), end="")
        elif args.sub == "discard":
            print(contrib.discard(proj, args.slug, args.confirm), end="")
    except contrib.ContribError as e:
        print("golden: %s" % e, file=sys.stderr)
        return e.code
    except profile.ProfileError as e:
        for line in e.errors:
            print(line, file=sys.stderr)
        return 1
    return 0


def cmd_check(args) -> int:
    root, warns, report = paths.plugin_root(), [], ""
    if args.release:
        errs = check.check_release(root, args.release)
    elif args.local:
        proj = _project()
        if proj is None:
            return 3
        errs = check.check_local(root, proj)
    elif args.ci:
        errs, warns, report = check.check_ci(root, args.base)
    else:
        errs = check.check_core(root)[0]
    for line in errs + warns:
        print(line)
    if report:
        print(report, end="")
        check.summary(report)
    if not errs:
        print("check ok")
    return 1 if errs else 0


def cmd_scan(args) -> int:
    terms = scan.read_deny_file(Path(args.deny_file)) if args.deny_file else []
    missing = [p for p in args.paths if not Path(p).exists()]
    for p in missing:
        print("golden: no such path %s (skipped)" % p, file=sys.stderr)
    hits = scan.scan_paths([Path(p) for p in args.paths if p not in missing], terms)
    for path, f in hits:
        print("%s:%d: %s: %s" % (path, f.line, f.rule, f.match))
    return 1 if hits else 0


def _session(flag) -> str | None:
    sid = session.current_session(flag)
    if not sid:
        print("golden: no session id", file=sys.stderr)
    return sid


def cmd_task(args, flag) -> int:
    proj = _project()
    if proj is None:
        return 3
    root = paths.plugin_root()
    if args.sub == "list":
        print("\n".join(task.list_lines(root, proj)) or "no tasks")
        return 0
    if args.sub == "show":
        try:
            print(task.show(proj, args.id), end="")
        except (task.TaskError, state.StateError) as e:
            print("golden: %s" % e, file=sys.stderr)
            return 1
        return 0
    sid = _session(flag)
    if not sid:
        return 3
    try:
        if args.sub == "start":
            _, text = task.start(root, proj, sid, args.kind, " ".join(args.desc), args.link or [])
            print(text, end="")
            return 0
        if args.sub == "abandon":
            text = task.abandon(root, proj, sid, args.id, args.confirm)
            print(text, end="")
            return 0
        if args.sub == "takeover" and not args.confirm:
            print("golden: taking over needs --confirm: golden task takeover %s --confirm" % args.id, file=sys.stderr)
            return 2
        d = (task.resume if args.sub == "resume" else task.takeover)(root, proj, sid, args.id)
        print(task.resume_view(root, proj, d, sid), end="")
        return 0
    except (task.TaskError, state.StateError, ValueError) as e:
        for line in str(e).splitlines():
            print("golden: " + line, file=sys.stderr)
        return getattr(e, "code", 1)
    except profile.ProfileError as e:
        for line in e.errors:
            print(line, file=sys.stderr)
        return 1


def _holder_cmd(flag, fn) -> int:
    """Run fn(root, project, session) -> text for a command that writes task state."""
    proj = _project()
    if proj is None:
        return 3
    sid = _session(flag)
    if not sid:
        return 3
    try:
        print(fn(paths.plugin_root(), proj, sid), end="")
    except (task.TaskError, state.StateError, ValueError) as e:
        for line in str(e).splitlines():
            print("golden: " + line, file=sys.stderr)
        return getattr(e, "code", 1)
    except profile.ProfileError as e:
        for line in e.errors:
            print(line, file=sys.stderr)
        return 1
    return 0


def cmd_note(args, flag) -> int:
    def run(root, proj, sid):
        task.note(proj, sid, args.id, args.what, " ".join(args.text))
        return "noted\n"
    return _holder_cmd(flag, run)


def cmd_gate(args, flag) -> int:
    def run(root, proj, sid):
        text = task.read_evidence(" ".join(args.evidence), Path.cwd())
        task.pass_gate(proj, sid, args.id, args.gate, text)
        return "gate %s passed\n" % args.gate
    return _holder_cmd(flag, run)


def cmd_advance(args, flag) -> int:
    return _holder_cmd(flag, lambda root, proj, sid: task.advance(root, proj, sid, args.id))


def cmd_ship(args, flag) -> int:
    return _holder_cmd(flag, lambda root, proj, sid: task.ship(root, proj, sid, args.id, args.merged))


def cmd_restore(args, flag) -> int:
    return _holder_cmd(flag, lambda root, proj, sid: task.restore(root, proj, sid, args.id))


def cmd_reopen(args, flag) -> int:
    return _holder_cmd(flag, lambda root, proj, sid: task.reopen(root, proj, sid, args.id, args.stage, args.recheck))


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
    tk = sub.add_parser("task", help="start, list, resume or take over tasks").add_subparsers(dest="sub", required=True)
    st = tk.add_parser("start", help="start a task: golden task start <kind> <description>")
    st.add_argument("kind")
    st.add_argument("desc", nargs="*")
    st.add_argument("--link", action="append", help="display-only reference to a related task")
    tk.add_parser("list", help="list tasks and who holds them")
    for name in ("resume", "takeover", "show", "abandon"):
        p = tk.add_parser(name)
        p.add_argument("id")
        if name in ("takeover", "abandon"):
            p.add_argument("--confirm", action="store_true")
    nt = sub.add_parser("note", help="record a decision, open an item or close one")
    nt.add_argument("id")
    nt.add_argument("what", choices=("decision", "open", "close"))
    nt.add_argument("text", nargs="+")
    gp = sub.add_parser("gate", help="record gate evidence").add_subparsers(dest="sub", required=True)
    gpp = gp.add_parser("pass", help="golden gate pass <id> <gate> --evidence <text|@file>")
    gpp.add_argument("id")
    gpp.add_argument("gate")
    gpp.add_argument("--evidence", nargs="+", required=True)
    adv = sub.add_parser("advance", help="move a task to its next stage once every gate has evidence")
    adv.add_argument("id")
    stg = sub.add_parser("stage", help="stage commands").add_subparsers(dest="sub", required=True)
    ro = stg.add_parser("reopen", help="run an earlier stage again")
    ro.add_argument("id")
    ro.add_argument("stage", choices=STAGES)
    ro.add_argument("--recheck", action="store_true", help="start the run without earlier evidence")
    cb = sub.add_parser("contrib", help="send a practice upstream").add_subparsers(dest="sub", required=True)
    cb.add_parser("new", help="start a contribution from an idea").add_argument("idea", nargs="+")
    cb.add_parser("check", help="sanitize and check the draft").add_argument("slug")
    cf = cb.add_parser("confirm", help="confirm the checked draft for sending")
    cf.add_argument("slug")
    cf.add_argument("--verdict", required=True, help="new | extends:<id> | duplicate:<id>")
    dc = cb.add_parser("discard", help="delete a contribution draft")
    dc.add_argument("slug")
    dc.add_argument("--confirm", action="store_true")
    ck = sub.add_parser("check", help="check upstream content (default), for CI, a project's own files, or a release")
    ckm = ck.add_mutually_exclusive_group()
    ckm.add_argument("--ci", action="store_true", help="also leaks, glossary aliases, unknown terms, similarity")
    ckm.add_argument("--local", action="store_true", help="format checks over .golden/overrides and .golden/practices")
    ckm.add_argument("--release", metavar="TAG", help="tag must match plugin.json, marketplace.json and CHANGELOG.md")
    ck.add_argument("--base", help="similarity report covers practices changed since this ref")
    sc = sub.add_parser("scan", help="scan files for leaks, project terms and hostile instructions")
    sc.add_argument("--deny-file", help="one project term per line, # comments")
    sc.add_argument("paths", nargs="+")
    ini = sub.add_parser("init", help="propose a project profile, or write the confirmed one from stdin")
    mode = ini.add_mutually_exclusive_group(required=True)
    mode.add_argument("--propose", action="store_true", help="print a proposal; writes nothing")
    mode.add_argument("--write", choices=["-"], help="write the profile read from stdin")
    ini.add_argument("--allow-removal", action="store_true", help="let --write drop keys the saved profile has")
    sh = sub.add_parser("ship", help="hand off or finish a task in the ship stage")
    sh.add_argument("id")
    sh.add_argument("--merged", action="store_true", help="confirm the merge when golden cannot see it")
    wt = sub.add_parser("worktree", help="working copy commands").add_subparsers(dest="sub", required=True)
    wt.add_parser("restore", help="re-add a deleted task working copy from its branch").add_argument("id")
    args = parser.parse_args(argv)

    if args.cmd == "profile":
        return cmd_profile_check(args)
    if args.cmd == "brief":
        return cmd_brief(args)
    if args.cmd == "override":
        return cmd_override(args)
    if args.cmd == "task":
        return cmd_task(args, flag)
    if args.cmd == "contrib":
        return cmd_contrib(args)
    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "scan":
        return cmd_scan(args)
    if args.cmd == "init":
        return cmd_init(args)
    if args.cmd == "note":
        return cmd_note(args, flag)
    if args.cmd in ("gate", "advance", "stage", "ship", "worktree"):
        return {"gate": cmd_gate, "advance": cmd_advance, "stage": cmd_reopen, "ship": cmd_ship,
                "worktree": cmd_restore}[args.cmd](args, flag)
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
