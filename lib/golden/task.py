import os
from datetime import datetime, timezone
from pathlib import Path

from golden import brief, claim, fsutil, overlay, paths, profile, state
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

    try:
        state.mutate(d, session, apply)
    except state.StateError as e:
        raise TaskError(str(e)) from None


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
            out.append("  - %s: %s" % (g["id"], "pending (wants: %s)" % g["evidence_wanted"] if ev is None else
                                       "passed at %s by %s%s\n    %s" % (
                                           ev["at"], ev["session"],
                                           " (carried from run %s)" % ev["carried_from"] if ev.get("carried_from") else "",
                                           ev["text"].strip().replace("\n", "\n    "))))
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
    if not (project / rel).is_file():
        text, _ = brief.build_brief(root, project, st["stage"], st["kind"], task_id=st["id"])
        fsutil.atomic_write(project / rel, text)
        out.append("brief snapshot missing; regenerated")
    return "\n".join(out) + "\n"
