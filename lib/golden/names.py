import re
import subprocess
import unicodedata

TYPE_BY_KIND = {"feature": "feat", "fix": "fix", "debug": "fix", "perf": "perf", "ux": "feat"}


def slug(text: str, max_len: int = 40) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")[:max_len].strip("-")
    return s or "task"


def branch_name(pattern: str, kind: str, text: str, task_id: str) -> str:
    """Fill the profile branch pattern; ValueError when git would not accept the result as a branch."""
    name = pattern
    for key, value in (("{type}", TYPE_BY_KIND[kind]), ("{slug}", slug(text)), ("{id}", task_id), ("{kind}", kind)):
        name = name.replace(key, value)
    # git refuses a leading "-" here too, so user text never reaches a later git call as an option.
    if subprocess.run(["git", "check-ref-format", "--branch", name], capture_output=True).returncode != 0:
        raise ValueError("branch pattern %r gives an invalid branch name %r" % (pattern, name))
    return name
