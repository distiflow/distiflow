import json
import os
import sys
from pathlib import Path

from golden import fsutil
from golden.session import VALID_ID


def session_start(payload: dict) -> None:
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    sid = payload.get("session_id") or ""
    # The env file is sourced by a shell: only a strictly valid id may reach it.
    if env_file and VALID_ID.fullmatch(sid):
        fsutil.append_text(Path(env_file), "export GOLDEN_SESSION_ID=%s\n" % sid)


HOOKS = {"session-start": session_start}


def run(name: str) -> int:
    # A hook must never block or disturb a session, whatever goes wrong.
    try:
        handler = HOOKS.get(name)
        if handler:
            handler(json.loads(sys.stdin.read() or "{}"))
    except Exception:
        pass
    return 0
