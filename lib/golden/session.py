import os
import re

VALID_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def extract_session_flag(argv: list[str]) -> tuple[list[str], str | None]:
    rest, sid, i = [], None, 0
    while i < len(argv):
        if argv[i] == "--session":
            sid = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
            continue
        rest.append(argv[i])
        i += 1
    return rest, sid


def current_session(flag: str | None) -> str | None:
    sid = flag if flag is not None else os.environ.get("GOLDEN_SESSION_ID")
    return sid if sid and VALID_ID.fullmatch(sid) else None
