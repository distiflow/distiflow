import os
from datetime import datetime, timezone
from pathlib import Path

from golden import brief, claim, fsutil, overlay, paths, profile, state, worktree
from golden.practices import STAGES


class TaskError(Exception):
    """A refusal shown to the user; code is the exit code."""

    def __init__(self, msg: str, code: int = 1):
        super().__init__(msg)
        self.code = code


def tasks_dir(project: Path) -> Path:
    return project / ".golden" / "tasks"


def stale_after(root: Path, project: Path) -> float:
    return overlay.load_toml("limits.toml", root, project)[0]["claim"]["stale_after_seconds"]


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def task_dir(project: Path, task_id: str) -> Path:
    d = tasks_dir(project) / task_id
    if "/" in task_id or task_id.startswith(".") or not (d / "state.json").is_file():
        raise TaskError("no task %s" % task_id)
    return d


def _new_id(project: Path) -> Path:
    tasks_dir(project).mkdir(parents=True, exist_ok=True)
    day, n = datetime.now().strftime("%Y%m%d"), 1
    while True:
        d = tasks_dir(project) / ("T-%s-%d" % (day, n))
        try:
            os.mkdir(d)  # exclusive: parallel starts never share an id
            return d
        except FileExistsError:
            n += 1


def start(root: Path, project: Path, session: str, kind: str, desc: str, links: list[str]) -> tuple[Path, str]:
    if not (project / ".golden" / profile.COMMITTED).is_file():
        raise TaskError("no golden profile; run /golden:init")
    try:
        brief.build_brief(root, project, "understand", kind)
        prof, _ = profile.load_for(root, project, overlay.load_practices(root, project)[0])
    except brief.UnknownKind as e:
        raise TaskError(str(e), 2) from None
    if not desc:
        raise TaskError("a description is required: golden task start <kind> <description>", 2)
    d = _new_id(project)
    claim.claim(d, session)
    text, sel = brief.build_brief(root, project, "understand", kind, task_id=d.name)
    st = state.new(d.name, kind, desc, paths.version(root), session,
                   [{"id": g.id, "evidence_wanted": g.evidence} for g in sel.gates])
    st.update(links=links, mode="worktree" if prof["git"]["worktrees"] else "checkout", base=prof["git"]["base"])
    state.save(d, st)
    fsutil.atomic_write(d / "stage-1-brief.md", text)
    return d, text


def list_lines(root: Path, project: Path) -> list[str]:
    limit, lines = stale_after(root, project), []
    for d in sorted(tasks_dir(project).glob("T-*")) if tasks_dir(project).is_dir() else []:
        try:
            st = state.load(d)
        except (OSError, ValueError, state.StateError) as e:
            lines.append("%s  unreadable: %s" % (d.name, e))
            continue
        h = claim.holder(d)
        held = "free" if h is None else "held by %s since %s%s" % (
            h["session"], h.get("since", "?"), " (stale)" if claim.is_stale(d, limit) else "")
        lines.append("%s  %s  %s  %s" % (d.name, st["stage"], st["status"], held))
    return lines


def _readable(d: Path) -> None:
    try:
        state.load(d)
    except (ValueError, state.StateError) as e:
        raise TaskError(str(e)) from None


def resume(root: Path, project: Path, session: str, task_id: str) -> Path:
    d = task_dir(project, task_id)
    _readable(d)  # never claim a task this golden cannot read
    h = claim.holder(d)
    if h is not None and h["session"] != session:
        if claim.is_stale(d, stale_after(root, project)):
            raise TaskError("task %s is held by %s, silent since %s; take over with: golden task takeover %s --confirm"
                            % (task_id, h["session"], _iso(time_of(d)), task_id), 2)
        raise TaskError("task %s is held by %s since %s" % (task_id, h["session"], h.get("since", "?")))
    if h is None:
        try:
            claim.claim(d, session)
        except claim.Held as e:
            raise TaskError("task %s is held by %s since %s" % (task_id, e.session, e.since)) from None
    return d


def time_of(d: Path) -> float:
    return (d / "claim").stat().st_mtime


def takeover(root: Path, project: Path, session: str, task_id: str) -> Path:
    d = task_dir(project, task_id)
    _readable(d)
    try:
        claim.takeover(d, session, stale_after(root, project))
    except claim.NotStale:
        h = claim.holder(d) or {"session": "unknown"}
        raise TaskError("task %s is not stale: held by %s, last seen %s" % (task_id, h["session"], _iso(time_of(d))))
    except claim.LostRace:
        raise TaskError("another session took task %s first" % task_id) from None
    return d


def note(project: Path, session: str, task_id: str, what: str, text: str) -> None:
    d = task_dir(project, task_id)

    def apply(st):
        if what == "decision":
            st["decisions"].append({"text": text, "at": state.now()})
        elif what == "open":
            st["open_items"].append({"n": len(st["open_items"]) + 1, "text": text, "closed_at": None})
        else:
            item = next((i for i in st["open_items"] if str(i["n"]) == text and not i["closed_at"]), None)
            if item is None:
                raise TaskError("no open item %s in task %s" % (text, task_id))
            item["closed_at"] = state.now()

    _mutate(d, session, apply)


def _mutate(d: Path, session: str, fn) -> dict:
    try:
        return state.mutate(d, session, fn)
    except state.StateError as e:
        raise TaskError(str(e)) from None


EVIDENCE_MAX = 20000


def read_evidence(arg: str, cwd: Path) -> str:
    text = arg
    if arg.startswith("@"):
        try:
            text = (cwd / arg[1:]).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise TaskError("cannot read evidence file %s: %s" % (arg[1:], e)) from None
        if len(text) > EVIDENCE_MAX:
            raise TaskError("evidence file %s is over %d characters" % (arg[1:], EVIDENCE_MAX))
    if not text.strip():
        raise TaskError("evidence is empty", 2)
    return text


def pass_gate(project: Path, session: str, task_id: str, gate: str, text: str) -> None:
    def apply(st):
        run = st["runs"][-1]
        # Only the running stage's snapshot counts: no evidence for another stage or a gate added later.
        if gate not in [g["id"] for g in run["gates"]]:
            raise TaskError("gate %s is not a gate of stage %s" % (gate, st["stage"]))
        run["evidence"][gate] = {"text": text, "at": state.now(), "session": session, "carried_from": None}

    _mutate(task_dir(project, task_id), session, apply)


def _version_key(v: str) -> tuple:
    return tuple(int(x) for x in v.split("."))


def changelog_between(root: Path, old: str, new: str) -> str:
    """CHANGELOG.md sections for versions in (old, new]."""
    try:
        text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    keep, out = False, []
    for line in text.splitlines():
        if line.startswith("## ["):
            try:
                v = _version_key(line[4:line.index("]")])
                keep = _version_key(old) < v <= _version_key(new)
            except ValueError:
                keep = False
        if keep:
            out.append(line)
    return "\n".join(out).strip()


def _open_run(root: Path, project: Path, st: dict, stage: str, session: str, carry: bool) -> str:
    """Append a run of stage with a fresh gate snapshot and brief; returns the text to print."""
    text, sel = brief.build_brief(root, project, stage, st["kind"], task_id=st["id"])
    version, prev = paths.version(root), st["runs"][-1]["version"]
    gates = [{"id": g.id, "evidence_wanted": g.evidence} for g in sel.gates]
    run = state.new_run(stage, 1 + sum(r["stage"] == stage for r in st["runs"]), version, session, gates)
    earlier = next((r for r in reversed(st["runs"]) if r["stage"] == stage), None)
    if carry and earlier:
        for g in gates:
            ev = earlier["evidence"].get(g["id"])
            if ev:
                run["evidence"][g["id"]] = {**ev, "carried_from": ev.get("carried_from") or earlier["n"]}
    if st["runs"][-1]["ended"] is None:
        st["runs"][-1]["ended"] = state.now()
    st["runs"].append(run)
    st["stage"] = stage
    fsutil.atomic_write(task_dir(project, st["id"]) / ("stage-%d-brief.md" % (STAGES.index(stage) + 1)), text)
    if version != prev:
        text += "\ngolden %s → %s\n%s\n" % (prev, version, changelog_between(root, prev, version))
    return text


def advance(root: Path, project: Path, session: str, task_id: str) -> str:
    out = []

    def apply(st):
        if st["stage"] == "ship":
            raise TaskError("ship is the last stage; run golden ship %s" % task_id)
        run = st["runs"][-1]
        failing = [g for g in run["gates"] if g["id"] not in run["evidence"]]
        if failing:
            raise TaskError("\n".join("failing gate: %s (%s)" % (g["id"], g["evidence_wanted"]) for g in failing))
        nxt = STAGES[STAGES.index(st["stage"]) + 1]
        note = ""
        if nxt == "implement":
            try:
                note = worktree.enter_implement(project, st, _git_conf(root, project), session)
            except (worktree.GitError, ValueError) as e:
                raise TaskError(str(e)) from None
        out.append(_open_run(root, project, st, nxt, session, carry=True) + note)

    _mutate(task_dir(project, task_id), session, apply)
    return out[0] + "\nstart a fresh session: /golden:task resume %s\n" % task_id


def _git_conf(root: Path, project: Path) -> dict:
    return profile.load_for(root, project, overlay.load_practices(root, project)[0])[0]["git"]


def _held(project: Path, session: str, task_id: str) -> tuple[Path, dict]:
    d = task_dir(project, task_id)
    _readable(d)
    if not claim.holds(d, session):
        raise TaskError("you do not hold task %s" % task_id)
    return d, state.load(d)


def _finish(d: Path, session: str, status: str) -> None:
    def apply(st):
        st["status"] = status
        if st["runs"][-1]["ended"] is None:
            st["runs"][-1]["ended"] = state.now()
    _mutate(d, session, apply)
    claim.release(d, session)


def _set_status(d: Path, session: str, status: str) -> None:
    _mutate(d, session, lambda st: st.update(status=status))


def ship(root: Path, project: Path, session: str, task_id: str, merged: bool) -> str:
    d = task_dir(project, task_id)
    _readable(d)
    if state.load(d)["status"] == "done":
        return "task %s is already done\n" % task_id
    d, st = _held(project, session, task_id)
    if st["stage"] != "ship":
        raise TaskError("task %s is at stage %s; ship comes after review" % (task_id, st["stage"]))
    conf, branch = _git_conf(root, project), st["branch"]
    wc = Path(st["worktree"]) if st["worktree"] else project
    try:
        # Uncommitted work blocks every path: an empty branch must not ship as done with work left behind.
        dirty = worktree.porcelain(wc)
        if dirty:
            raise TaskError("uncommitted changes in %s; commit them before ship:\n%s" % (wc, dirty))
        if not (st["status"] == "cleanup-pending" or worktree.is_merged(project, branch, conf["base"], merged)):
            handoff = ("git push -u origin %s\ngh pr create --head %s --base %s\n" % (branch, branch, conf["base"]))
            if conf["push"] == "forbidden":
                _set_status(d, session, "awaiting-merge")
                return "this project does not let golden push; hand off with:\n" + handoff
            url = worktree.push_and_request(project, branch, conf["base"])
            _set_status(d, session, "awaiting-merge")
            if url is None:
                raise TaskError("branch pushed; gh is missing or signed out. Open the request with:\n" + handoff, 3)
            return "%s\nawaiting merge; run golden ship %s again after it is merged\n" % (url, task_id)
        if st["mode"] == "worktree":
            try:
                worktree.remove(project, wc)
            except worktree.GitError as e:
                _set_status(d, session, "cleanup-pending")
                raise TaskError("cleanup pending: %s; retry with golden ship %s" % (e, task_id)) from None
        else:
            worktree.release_checkout(project, task_id)
    except worktree.GitError as e:
        raise TaskError(str(e)) from None
    _finish(d, session, "done")
    return "task %s shipped and cleaned up\n" % task_id


def abandon(root: Path, project: Path, session: str, task_id: str, confirm: bool) -> str:
    d, st = _held(project, session, task_id)
    wc = Path(st["worktree"]) if st["worktree"] else (project if st["branch"] else None)
    dirty = worktree.porcelain(wc) if wc else ""
    listing = "uncommitted changes in %s:\n%s\n" % (wc, dirty) if dirty else "no uncommitted changes\n"
    if not confirm:
        raise TaskError(listing + "nothing removed; abandon with: golden task abandon %s --confirm" % task_id, 2)
    out = listing
    if st["worktree"]:
        try:
            worktree.remove(project, Path(st["worktree"]), force=True)
        except worktree.GitError as e:
            raise TaskError(str(e)) from None
    elif st["branch"]:
        # The main checkout is shared: never delete work there, only let go of it.
        worktree.release_checkout(project, task_id)
        out += "changes left in the main checkout on %s\n" % st["branch"]
    _finish(d, session, "abandoned")
    return out + "task %s abandoned\n" % task_id


def restore(root: Path, project: Path, session: str, task_id: str) -> str:
    d, st = _held(project, session, task_id)
    if not st["worktree"]:
        raise TaskError("task %s has no working copy to restore" % task_id)
    path = Path(st["worktree"])
    try:
        worktree.restore(project, path, st["branch"])
    except worktree.GitError as e:
        raise TaskError(str(e)) from None
    return "restored %s on %s; uncommitted work in the old copy is gone\n" % (path, st["branch"])


def reopen(root: Path, project: Path, session: str, task_id: str, stage: str, recheck: bool) -> str:
    out = []

    def apply(st):
        if STAGES.index(stage) > STAGES.index(st["stage"]):
            raise TaskError("stage %s is not reached yet (task is at %s)" % (stage, st["stage"]))
        out.append(_open_run(root, project, st, stage, session, carry=not recheck))

    _mutate(task_dir(project, task_id), session, apply)
    return out[0]


def _first_line(text: str) -> str:
    return (text.strip().splitlines() or [""])[0]


def _open(st: dict) -> list[str]:
    return ["#%d %s" % (i["n"], i["text"]) for i in st["open_items"] if not i["closed_at"]]


def show(project: Path, task_id: str) -> str:
    st = state.load(task_dir(project, task_id))
    out = ["task %s · %s · %s · %s" % (st["id"], st["kind"], st["desc"], st["status"]), "decisions:"]
    out += ["- " + x["text"] for x in st["decisions"]] or ["- none"]
    out += ["open items:"] + (["- " + x for x in _open(st)] or ["- none"])
    for run in st["runs"]:
        out.append("run %s %d · golden %s · %s · %s → %s" % (run["stage"], run["n"], run["version"], run["session"],
                                                         run["started"], run["ended"] or "open"))
        for g in run["gates"]:
            ev = run["evidence"].get(g["id"])
            if ev is None:
                out.append("  - %s: pending (wants: %s)" % (g["id"], g["evidence_wanted"]))
                continue
            first, _, rest = ev["text"].strip().partition("\n")
            carried = " (carried from run %s)" % ev["carried_from"] if ev.get("carried_from") else ""
            out.append("  - %s: %s%s · %s by %s" % (g["id"], first, carried, ev["at"], ev["session"]))
            out += ["      " + line for line in rest.splitlines()]
    return "\n".join(out) + "\n"


def resume_view(root: Path, project: Path, d: Path, session: str) -> str:
    st = state.load(d)
    run = st["runs"][-1]
    n = STAGES.index(st["stage"]) + 1
    status = "interrupted" if run["ended"] is None and run["session"] != session else st["status"]
    passed = sorted((ev["at"], gid, ev["text"]) for r in st["runs"] for gid, ev in r["evidence"].items())
    last = "%s (%s)" % (passed[-1][1], _first_line(passed[-1][2])) if passed else "none"
    pending = [g["id"] for g in run["gates"] if g["id"] not in run["evidence"]]
    rel = Path(".golden", "tasks", d.name, "stage-%d-brief.md" % n)
    out = ["stage %d/6 %s (%s)" % (n, st["stage"], status),
           "last passed gate: " + last,
           "pending gates: " + (", ".join(pending) or "none"),
           "open items: " + (" · ".join(_open(st)) or "none"),
           "decisions: " + (" · ".join(x["text"] for x in st["decisions"]) or "none"),
           "brief: " + rel.as_posix()]
    if st["worktree"] and not Path(st["worktree"]).exists():
        out.append("working copy missing: %s; restore with golden worktree restore %s" % (st["worktree"], st["id"]))
    if not (project / rel).is_file():
        text, _ = brief.build_brief(root, project, st["stage"], st["kind"], task_id=st["id"])
        fsutil.atomic_write(project / rel, text)
        out.append("brief snapshot missing; regenerated")
    return "\n".join(out) + "\n"
