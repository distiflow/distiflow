import math
import re
from pathlib import Path

# The plugin's own commands; a shared skill may not take their names.
LAUNCHERS = ("task", "init", "contribute", "override")
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")


def parse(text: str) -> dict:
    """The `key: value` lines between the leading `---` fences; raises ValueError naming what is wrong."""
    lines = text.split("\n")
    if lines[0].strip() != "---" or "---" not in (l.strip() for l in lines[1:]):
        raise ValueError("no --- frontmatter with name and description")
    end = [l.strip() for l in lines].index("---", 1)
    meta = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if sep and not line[:1].isspace():
            meta[key.strip()] = value.strip()
    if not NAME.fullmatch(meta.get("name", "")):
        raise ValueError("frontmatter name %r: use lower-case words and hyphens" % meta.get("name", ""))
    if not meta.get("description"):
        raise ValueError("frontmatter description is missing")
    return meta


def problems(text: str, name: str | None, limit: int) -> list[str]:
    """Format and size problems of one shared skill; name is its folder, when it has one."""
    try:
        meta = parse(text)
    except ValueError as e:
        return [str(e)]
    out = []
    if meta["name"] in LAUNCHERS:
        out.append("name %s is reserved for a distiflow command" % meta["name"])
    if name is not None and meta["name"] != name:
        out.append("name %s does not match folder %s" % (meta["name"], name))
    tokens = math.ceil(len(text) / 4)
    if tokens > limit:
        out.append("size %d > limit %d" % (tokens, limit))
    return out


def shared(root: Path) -> dict[str, Path]:
    """Shared skills upstream, by folder name; launchers excluded."""
    base = root / "skills"
    dirs = sorted(d for d in base.iterdir() if d.is_dir()) if base.is_dir() else []
    return {d.name: d / "SKILL.md" for d in dirs if d.name not in LAUNCHERS}
