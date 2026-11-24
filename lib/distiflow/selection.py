from dataclasses import dataclass, field

from distiflow.practices import RUN_COSTS, Issue, Practice
from distiflow.profile import gate_disables

GATE_OVER_CAP = "over cost cap, kept: gate"


@dataclass(frozen=True)
class Selection:
    kept: list = field(default_factory=list)     # (Practice, note)
    dropped: list = field(default_factory=list)  # (id or path, reason)
    gates: list = field(default_factory=list)    # Practice
    notes: list = field(default_factory=list)


def _matches(p: Practice, stage: str, kind: str, signals) -> bool:
    return (stage in p.stages and (p.kinds is None or kind in p.kinds)
            and (p.signals is None or all(s in signals for s in p.signals)))


def select(stage: str, kind: str, profile: dict, practices: list[Practice], issues: list[Issue],
           limits: dict) -> Selection:
    dropped = [(i.ref, "%s: %s" % (i.kind, i.reason)) for i in sorted(issues, key=lambda i: (i.kind, i.ref))
               if i.kind in ("malformed", "clash")]
    disabled = {d["id"]: d.get("reason", "").strip() for d in profile.get("practices", {}).get("disable", [])}
    gates_off = gate_disables(profile)
    signals = profile.get("project", {}).get("signals", [])
    cost = profile.get("cost", {})
    cap = cost.get("run_cap", RUN_COSTS[-1])
    budget = cost.get("budget", {}).get(stage) or limits["budget"][stage]

    candidates = []
    for p in sorted(practices, key=lambda p: (-p.priority, p.id)):
        if not _matches(p, stage, kind, signals):
            continue
        if p.gate and p.id in gates_off:
            dropped.append((p.id, "gate disabled by profile: " + gates_off[p.id]))
        elif not p.gate and p.id in disabled:
            dropped.append((p.id, "disabled by profile: " + (disabled[p.id] or "no reason given")))
        elif not p.gate and RUN_COSTS.index(p.run_cost) > RUN_COSTS.index(cap):
            dropped.append((p.id, "excluded by cost cap " + cap))
        else:
            candidates.append(p)

    gates = [p for p in candidates if p.gate]
    used = sum(p.tokens for p in gates)
    notes = ["gates alone use %d of %d tokens" % (used, budget)] if used > budget else []
    admitted, full = set(), False
    for p in candidates:
        if p.gate:
            continue
        # Stop at the first practice that does not fit, so a lower priority never jumps the queue.
        if not full and used + p.tokens <= budget:
            used += p.tokens
            admitted.add(p.id)
        else:
            full = True
            dropped.append((p.id, "over token budget (%d/%d)" % (used, budget)))
    over_cap = lambda p: RUN_COSTS.index(p.run_cost) > RUN_COSTS.index(cap)
    kept = [(p, GATE_OVER_CAP if p.gate and over_cap(p) else "") for p in candidates
            if p.gate or p.id in admitted]
    return Selection(kept=kept, dropped=dropped, gates=gates, notes=notes)
