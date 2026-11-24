import difflib
import tomllib
from pathlib import Path

from golden.practices import RUN_COSTS, STAGES, Practice

EFFORTS = ("low", "medium", "high", "xhigh", "max")
_DISABLE = [{"id": str, "reason": str}]
# "*" = any key; "*role" / "*stage" = key must be a known role / stage.
SCHEMA = {
    "project": {"name": str, "signals": [str], "deny_terms": [str]},
    "commands": {"*": str},
    "glossary": {"*": str},
    "practices": {"disable": _DISABLE},
    "gates": {"disable": _DISABLE},
    "models": {"*role": {"model": str, "effort": EFFORTS}},
    "cost": {"run_cap": RUN_COSTS, "budget": {"*stage": "posint"}},
    "git": {"worktrees": bool, "push": ("allowed", "forbidden"), "base": str, "branch": str},
}
GIT_DEFAULTS = {"worktrees": True, "push": "allowed", "base": "main", "branch": "{type}/{slug}_{id}"}
_TYPE_NAMES = {str: "string", bool: "boolean"}
COMMITTED, LOCAL = "profile.toml", "profile.local.toml"


class ProfileError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


def _validate(value, spec, dotted: str, errs: list, roles) -> None:
    if spec == "posint":
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            errs.append("%s: expected integer > 0" % dotted)
    elif isinstance(spec, tuple):
        if value not in spec:
            errs.append("%s: expected one of %s" % (dotted, ", ".join(spec)))
    elif isinstance(spec, type):
        if not isinstance(value, spec):
            errs.append("%s: expected %s" % (dotted, _TYPE_NAMES[spec]))
    elif isinstance(spec, list):
        if not isinstance(value, list):
            errs.append("%s: expected a list" % dotted)
            return
        for item in value:
            _validate(item, spec[0], dotted, errs, roles)
        if spec == _DISABLE:
            errs += ["%s: missing id" % dotted for item in value if isinstance(item, dict) and "id" not in item]
    elif not isinstance(value, dict):
        errs.append("%s: expected a table" % dotted)
    else:
        for key, v in value.items():
            sub = dotted + "." + key if dotted else key
            if "*" in spec:
                _validate(v, spec["*"], sub, errs, roles)
            elif "*role" in spec or "*stage" in spec:
                known, what = (roles, "role") if "*role" in spec else (STAGES, "key")
                if key in known:
                    _validate(v, spec["*role" if what == "role" else "*stage"], sub, errs, roles)
                else:
                    errs.append("%s: unknown %s (one of %s)" % (sub, what, ", ".join(known)))
            elif key in spec:
                _validate(v, spec[key], sub, errs, roles)
            else:
                hint = difflib.get_close_matches(key, list(spec), 1)
                errs.append("%s: unknown key%s" % (sub, " (did you mean %s?)" % hint[0] if hint else ""))


def _read(path: Path, roles) -> dict:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ProfileError(["%s: invalid TOML: %s" % (path.name, e)]) from None
    errs = []
    _validate(data, SCHEMA, "", errs, roles)
    if errs:
        raise ProfileError(["%s: %s" % (path.name, e) for e in errs])
    return data


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            out[k] = _merge(base[k], v)
        elif isinstance(v, list) and isinstance(base.get(k), list) and all(isinstance(x, dict) for x in v):
            out[k] = base[k] + v  # disable lists add up across files
        else:
            out[k] = v
    return out


def _disables(data: dict, table: str) -> list[dict]:
    return data.get(table, {}).get("disable", [])


def _gate_rules(committed: dict, local: dict, practices: list[Practice], upstream_gates, project: Path):
    errs, warns = [], []
    gates = {p.id for p in practices if p.gate} | set(upstream_gates)
    known = {p.id for p in practices} | set(upstream_gates)
    if "gates" in local:
        errs.append("%s: gates: gates change only in the committed profile" % LOCAL)
    for d in _disables(local, "practices"):
        if d.get("id") in gates:
            errs.append("%s: practices.disable: %s: gates change only in the committed profile" % (LOCAL, d["id"]))
    reasoned = set()
    for table in ("gates", "practices"):
        for d in _disables(committed, table):
            pid, reason = d.get("id"), d.get("reason", "").strip()
            if table == "gates" and not reason:
                errs.append("%s: gates.disable: %s: reason required" % (COMMITTED, pid))
            elif table == "practices" and pid in gates and not reason:
                errs.append("%s: practices.disable: %s is a gate: reason required" % (COMMITTED, pid))
            if reason and pid in gates:
                reasoned.add(pid)
    for table in ("gates", "practices"):
        for name, data in ((COMMITTED, committed), (LOCAL, local)):
            for d in _disables(data, table):
                if d.get("id") not in known:
                    warns.append("%s: %s.disable: %s: unknown practice" % (name, table, d.get("id")))
    for p in practices:
        if p.id in upstream_gates and p.source == "overridden" and not p.gate and p.id not in reasoned:
            errs.append("%s: override turns gate %s off: add [[gates.disable]] with a reason"
                        % (p.path.relative_to(project).as_posix(), p.id))
    return errs, warns


def load_profile(project: Path, practices: list[Practice], roles=(), upstream_gates=frozenset()) -> tuple[dict, list[str]]:
    golden = project / ".golden"
    if not (golden / COMMITTED).is_file():
        raise ProfileError(["no .golden/%s in %s (run /golden:init)" % (COMMITTED, project)])
    committed = _read(golden / COMMITTED, roles)
    local = _read(golden / LOCAL, roles) if (golden / LOCAL).is_file() else {}
    errs, warns = _gate_rules(committed, local, practices, upstream_gates, project)
    if errs:
        raise ProfileError(errs)
    merged = _merge(committed, local)
    gates = {p.id for p in practices if p.gate} | set(upstream_gates)
    # A gate disabled through practices.disable is a gate disable: keep one list for selection.
    moved = [d for d in _disables(merged, "practices") if d["id"] in gates]
    if moved:
        merged.setdefault("gates", {})["disable"] = _disables(merged, "gates") + moved
        merged["practices"]["disable"] = [d for d in _disables(merged, "practices") if d not in moved]
    merged["git"] = {**GIT_DEFAULTS, **merged.get("git", {})}
    return merged, warns


def gate_disables(profile: dict) -> dict[str, str]:
    return {d["id"]: d["reason"].strip() for d in _disables(profile, "gates")}


def load_for(root: Path, project: Path, practices: list[Practice]) -> tuple[dict, list[str]]:
    """load_profile with the roles and upstream gates read from the plugin root."""
    from golden import overlay
    upstream, _ = overlay.load_practices(root, None)
    models, _ = overlay.load_toml("models.toml", root, project)
    return load_profile(project, practices, roles=tuple(models.get("roles", {})),
                        upstream_gates=frozenset(p.id for p in upstream if p.gate))
