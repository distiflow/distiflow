import json
import os
import sys
from pathlib import Path

from distiflow import claim, fsutil, overlay, paths, state
from distiflow.session import VALID_ID


def session_start(payload: dict) -> None:
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    sid = payload.get("session_id") or ""
    # The env file is sourced by a shell: only a strictly valid id may reach it.
    if env_file and VALID_ID.fullmatch(sid):
        fsutil.append_text(Path(env_file), "export DISTIFLOW_SESSION_ID=%s\n" % sid)


def heartbeat(payload: dict) -> None:
    sid = payload.get("session_id") or ""
    proj = paths.find_project(Path(payload.get("cwd") or os.getcwd()))
    if proj is None or not VALID_ID.fullmatch(sid):
        return
    for d in (proj / ".distiflow" / "tasks").glob("T-*"):
        claim.heartbeat(d, sid)


def _deny(msg: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": msg}}


def _inside(target: Path, base) -> bool:
    return bool(base) and target.is_relative_to(os.path.realpath(base))


def _tasks(proj: Path):
    for d in sorted((proj / ".distiflow" / "tasks").glob("T-*")):
        try:
            yield d, state.load(d)
        except Exception:
            continue  # one corrupt task never blocks or unguards the others


def guard(payload: dict) -> dict | None:
    sid, cwd, tool_input = payload.get("session_id") or "", Path(payload.get("cwd") or os.getcwd()), payload.get("tool_input") or {}
    raw = cwd if payload.get("tool_name") == "Bash" else tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw or not VALID_ID.fullmatch(sid):
        return None
    target = Path(os.path.realpath(cwd / raw))  # one spelling for symlinked dirs such as /var
    proj = paths.find_project(target)
    if proj is None:
        return None
    try:
        held = json.loads((proj / ".distiflow" / "tasks" / "checkout.claim").read_text()).get("task")
    except Exception:
        held = None
    for d, st in _tasks(proj):
        # Deny only on positive evidence: a lost marker and another session holding the task now.
        if not claim.lost(d, sid) or claim.holder(d) is None:
            continue
        if _inside(target, st.get("worktree")) or (held == d.name and _inside(target, proj)):
            return _deny("you no longer hold task %s; resume it with /distiflow:task resume %s" % (d.name, d.name))
    return None


def agent_cap(payload: dict) -> dict | None:
    sid = payload.get("session_id") or ""
    if "budget-approved:" in str((payload.get("tool_input") or {}).get("prompt", "")) or not VALID_ID.fullmatch(sid):
        return None
    proj = paths.find_project(Path(payload.get("cwd") or os.getcwd()))
    if proj is None:
        return None
    mine = [(d, st) for d, st in _tasks(proj) if claim.holds(d, sid)]
    if not mine:
        return None
    d, st = mine[0]
    run = st["runs"][-1]
    cap = overlay.load_toml("limits.toml", paths.plugin_root(), proj)[0]["subagents"]["per_stage"]
    slots = d / "agents" / ("%s-%d" % (run["stage"], run["n"]))
    for k in range(cap):
        try:
            fsutil.create_exclusive(slots / ("%d.slot" % k), "")
            return None
        except FileExistsError:
            continue
    return _deny("sub-agent cap reached for stage %s (%d). Ask the developer; if they approve, "
                 "put 'budget-approved: <their words>' in the prompt." % (run["stage"], cap))


HOOKS = {"session-start": session_start, "heartbeat": heartbeat, "guard": guard, "agent-cap": agent_cap}


def run(name: str) -> int:
    # A hook must never block or disturb a session, whatever goes wrong.
    try:
        handler = HOOKS.get(name)
        out = handler(json.loads(sys.stdin.read() or "{}")) if handler else None
        if out:
            sys.stdout.write(json.dumps(out) + "\n")
    except Exception:
        pass
    return 0
