import math
import tomllib
from dataclasses import dataclass
from pathlib import Path

STAGES = ("understand", "plan", "implement", "verify", "review", "ship")
RUN_COSTS = ("cheap", "medium", "expensive")
_HEADER_PREFIXES = ("<!-- distiflow-override ", "# distiflow-override ")
_REQUIRED = ("id", "stages", "run_cost")
_TYPES = {"id": str, "stages": list, "kinds": list, "signals": list, "run_cost": str,
          "gate": bool, "evidence": str, "priority": int}


class Malformed(Exception):
    def __init__(self, path: Path, reason: str):
        super().__init__("%s: %s" % (path, reason))
        self.path, self.reason = path, reason


@dataclass(frozen=True)
class Practice:
    id: str
    stages: tuple
    kinds: tuple | None
    signals: tuple | None
    run_cost: str
    gate: bool
    evidence: str
    priority: int
    body: str
    path: Path
    source: str
    tokens: int


@dataclass(frozen=True)
class Issue:
    kind: str  # malformed | clash | drift | orphan | stale-key
    ref: str
    reason: str


def kinds(root: Path) -> tuple[str, ...]:
    return tuple(tomllib.loads((root / "core" / "kinds.toml").read_text())["kinds"])


def strip_header(text: str) -> str:
    first, _, rest = text.partition("\n")
    return rest if first.startswith(_HEADER_PREFIXES) else text


def split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("+++\n"):
        raise ValueError("missing +++ frontmatter")
    end = text.find("\n+++", 3)
    if end < 0 or text[end + 4:end + 5] not in ("", "\n"):
        raise ValueError("unclosed +++ frontmatter")
    return text[4:end + 1], text[end + 5:]


def _check(meta: dict, path: Path, known_kinds) -> None:
    for key in meta:
        if key not in _TYPES:
            raise ValueError("unknown key %s" % key)
    for key in _REQUIRED:
        if key not in meta:
            raise ValueError("missing key %s" % key)
    for key, typ in _TYPES.items():
        v = meta.get(key)
        # bool is an int subclass, so priority = true must not pass as a number.
        if v is not None and (not isinstance(v, typ) or (typ is int and isinstance(v, bool))):
            raise ValueError("%s: expected %s" % (key, typ.__name__))
    for key, allowed in (("stages", STAGES), ("kinds", known_kinds)):
        for v in meta.get(key) or ():
            if v not in allowed:
                raise ValueError("%s: unknown %s (one of %s)" % (key, v, ", ".join(allowed)))
    if not meta["stages"]:
        raise ValueError("stages: empty")
    if meta["run_cost"] not in RUN_COSTS:
        raise ValueError("run_cost: expected one of %s" % ", ".join(RUN_COSTS))
    if meta["id"] != path.stem:
        raise ValueError("id %s does not match file name %s" % (meta["id"], path.name))
    if meta.get("gate") and not meta.get("evidence", "").strip():
        raise ValueError("gate needs evidence")


def parse_practice(path: Path, source: str, known_kinds) -> Practice:
    text = path.read_text(encoding="utf-8")
    try:
        front, body = split_frontmatter(strip_header(text))
        meta = tomllib.loads(front)
        _check(meta, path, known_kinds)
    except (ValueError, tomllib.TOMLDecodeError) as e:
        raise Malformed(path, str(e)) from None
    opt = lambda k: tuple(meta[k]) if k in meta else None
    return Practice(id=meta["id"], stages=tuple(meta["stages"]), kinds=opt("kinds"),
                    signals=opt("signals"), run_cost=meta["run_cost"], gate=meta.get("gate", False),
                    evidence=meta.get("evidence", ""), priority=meta.get("priority", 50), body=body,
                    path=path, source=source, tokens=math.ceil(len(text) / 4))
