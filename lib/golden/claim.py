import json
import os
import secrets
import time
from pathlib import Path

from golden import fsutil
from golden.state import now


class Held(Exception):
    def __init__(self, session: str, since: str):
        super().__init__("held by %s since %s" % (session, since))
        self.session, self.since = session, since


class NotStale(Exception):
    pass


class LostRace(Exception):
    pass


def holder(task_dir: Path) -> dict | None:
    try:
        data = json.loads((task_dir / "claim").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("session"), str) else None


def holds(task_dir: Path, session: str) -> bool:
    h = holder(task_dir)
    return h is not None and h["session"] == session


def claim(task_dir: Path, session: str) -> None:
    body = json.dumps({"session": session, "nonce": secrets.token_hex(8), "since": now()})
    try:
        fsutil.create_exclusive(task_dir / "claim", body)
    except FileExistsError:
        h = holder(task_dir) or {"session": "unknown", "since": "unknown"}
        raise Held(h["session"], h.get("since", "unknown")) from None


def age(task_dir: Path) -> float:
    return time.time() - (task_dir / "claim").stat().st_mtime


def is_stale(task_dir: Path, stale_after: float) -> bool:
    # Whole seconds: a claim exactly at the limit is still held.
    return int(age(task_dir)) > stale_after


def takeover(task_dir: Path, session: str, stale_after: float) -> None:
    """Exactly one taker wins: the exclusive link of the old claim to its lost name is the decision."""
    path = task_dir / "claim"
    h = holder(task_dir)
    if h is None:
        try:
            return claim(task_dir, session)
        except Held:
            raise LostRace() from None
    if h["session"] == session:
        return
    if not is_stale(task_dir, stale_after):
        raise NotStale()
    lost = task_dir / ("claim.lost.%s.%s" % (h["session"], h.get("nonce", "x")))
    try:
        os.link(path, lost)
        if os.stat(path).st_ino != os.stat(lost).st_ino:
            raise LostRace()
    except (FileExistsError, FileNotFoundError):
        raise LostRace() from None
    os.unlink(path)
    try:
        claim(task_dir, session)
    except Held:
        raise LostRace() from None


def heartbeat(task_dir: Path, session: str) -> None:
    # Touch only, never rewrite: an old holder must not be able to recreate its claim.
    if holds(task_dir, session):
        os.utime(task_dir / "claim")


def release(task_dir: Path, session: str) -> None:
    if holds(task_dir, session):
        (task_dir / "claim").unlink(missing_ok=True)


def lost(task_dir: Path, session: str) -> bool:
    return any(task_dir.glob("claim.lost.%s.*" % session)) and not holds(task_dir, session)
