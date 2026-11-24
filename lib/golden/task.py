import os
from datetime import datetime, timezone
from pathlib import Path

from golden import brief, claim, fsutil, overlay, paths, profile, state


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


def resume(root: Path, project: Path, session: str, task_id: str) -> Path:
    d = task_dir(project, task_id)
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
    try:
        claim.takeover(d, session, stale_after(root, project))
    except claim.NotStale:
        h = claim.holder(d) or {"session": "unknown"}
        raise TaskError("task %s is not stale: held by %s, last seen %s" % (task_id, h["session"], _iso(time_of(d))))
    except claim.LostRace:
        raise TaskError("another session took task %s first" % task_id) from None
    return d


def resume_view(d: Path, session: str) -> str:
    st = state.load(d)
    return "task %s · %s · held by %s\n" % (st["id"], st["stage"], session)
