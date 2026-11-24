from pathlib import Path

from distiflow import overlay, paths, profile, signals
from distiflow.overlay import Resolved
from distiflow.practices import STAGES, kinds, strip_header
from distiflow.selection import Selection, select

_WARN_KINDS = ("drift", "orphan", "stale-key")


def model_plan(stage: str, prof: dict, models: dict) -> tuple[list[tuple[str, str, str, bool]], str]:
    rows = []
    for role in models["stages"][stage]["roles"]:
        base, over = models["roles"][role], prof.get("models", {}).get(role, {})
        rows.append((role, over.get("model", base["model"]), over.get("effort", base["effort"]), bool(over)))
    return rows, models["stages"][stage]["session"]


def _list(lines: list[str]) -> str:
    return "\n".join(lines) if lines else "- none"


def render_brief(*, task_id: str | None, kind: str, stage: str, version: str, stage_text: Resolved,
                 selection: Selection, plan, warnings: list[str], kinds_toml: dict) -> str:
    emphasis = kinds_toml["kinds"][kind].get("emphasis", {})
    stages = ["- %d. %s%s — %s" % (i + 1, s, " (this stage)" if s == stage else "", emphasis.get(s, ""))
              for i, s in enumerate(STAGES)]
    text = strip_header(stage_text.path.read_text(encoding="utf-8")).strip()
    loaded = []
    for p, note in selection.kept:
        loaded.append("- %s · %s · %d tok · %s%s" % (p.id, p.run_cost, p.tokens, p.source, " · " + note if note else ""))
        loaded.append("\n".join("  " + line if line else "" for line in p.body.strip().splitlines()))
    roles, session = plan
    models = ["- %s: %s/%s%s" % (r, m, e, " (profile override)" if o else "") for r, m, e, o in roles]
    models.append("- session: %s (recommended)" % session)
    parts = [
        "# %s · %s · stage %d/6 %s · distiflow %s" % (task_id or "ad-hoc", kind, STAGES.index(stage) + 1, stage, version),
        "## Stages\n" + "\n".join(stages),
        "## Stage\n%s%s" % ("(overridden locally)\n\n" if stage_text.source == "overridden" else "", text),
        "## Practices loaded\n" + _list(loaded),
        "## Not loaded\n" + _list(["- %s: %s" % d for d in selection.dropped]),
        "## Gates\n" + _list(["- %s: %s" % (g.id, g.evidence) for g in selection.gates]),
        "## Models\n" + "\n".join(models),
        "## Warnings\n" + _list(["- " + w for w in warnings]),
    ]
    return "\n\n".join(parts) + "\n"


class UnknownKind(Exception):
    pass


def build_brief(root: Path, project: Path, stage: str, kind: str, task_id: str | None = None) -> tuple[str, Selection]:
    """Raises profile.ProfileError or UnknownKind."""
    if kind not in kinds(root):
        raise UnknownKind("unknown kind %s (one of %s)" % (kind, ", ".join(kinds(root))))
    practices, issues = overlay.load_practices(root, project)
    prof, warnings = profile.load_for(root, project, practices)
    tomls = {}
    for name in ("limits", "models", "kinds"):
        tomls[name], extra = overlay.load_toml(name + ".toml", root, project)
        issues += extra
    stage_text = overlay.resolve("stages/%s.md" % stage, root, project)
    issues += stage_text.issues
    selection = select(stage, kind, prof, practices, issues, tomls["limits"])
    warnings = warnings + [i.reason for i in issues if i.kind in _WARN_KINDS] + selection.notes
    if "signals" in prof.get("project", {}):
        diff = signals.drift(prof["project"]["signals"], signals.detect_signals(project, root))
        if diff:
            warnings.append("signals differ from profile: %s; update with /distiflow:init" % " ".join(diff))
    text = render_brief(task_id=task_id, kind=kind, stage=stage, version=paths.version(root), stage_text=stage_text,
                        selection=selection, plan=model_plan(stage, prof, tomls["models"]), warnings=warnings,
                        kinds_toml=tomls["kinds"])
    return text, selection
