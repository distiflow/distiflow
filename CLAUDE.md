# distiflow

Claude Code plugin `distiflow`: a six-stage pipeline per task, tag-selected practices, a project
profile with layered overrides, claimed and resumable task state, and a sanitizing `/contribute`
flow. One Python CLI (`bin/distiflow` → `lib/distiflow/`) owns every deterministic decision; skills
and hooks call it.

## Artifacts

Specs, plans, manifests and reviews live in `../.agent/` (sibling of this repo). Never commit them,
never copy them in.

## Git

- Branch `<type>/<what>_<ticket>`, e.g. `feat/profile-overlay_GW-1`.
- Commit message: one `-m`, one line `<type>(<scope>): <imperative summary>`, lower-case, no period,
  no body, no trailers.
- Never commit onto `main`.
- Never push, open or merge a PR unless the human's latest prompt ends with `!!`.
- RED evidence for every new test case is recorded in the ticket manifest before the test commit.

## Layout

```
.claude-plugin/{marketplace.json,plugin.json}
skills/            thin launchers only — every overridable text lives in core/
  task/  init/  contribute/  override/
agents/            scout · synth · planner · worker · gate-runner · reviewer
core/
  stages/<stage>.md          stage instructions (understand plan implement verify review ship)
  practices/<stage>/<id>.md  +++ TOML frontmatter +++ then body
  kinds.toml  signals.toml  glossary.toml  models.toml  limits.toml
bin/distiflow      python entry
lib/distiflow/     cli · paths · session · hooks · fsutil · overlay · profile · select · state ·
                   claim · worktree · scan · similar · glossary · toml_write
hooks/hooks.json   SessionStart session id · PostToolUse heartbeat · PreToolUse claim guard and Agent cap
tests/             stdlib unittest, integration over temp git repos
.github/workflows/check.yml   pull_request, no secrets
CHANGELOG.md  LICENSE (MIT)  README.md
```

## Gates

```
python3 -m unittest discover -s tests -t . -q
python3 bin/distiflow check --ci
```

## Constraints

- Python ≥3.11, standard library only. No packages, no `requirements.txt`, no dependencies.
- `lib/distiflow/fsutil.py` is the only module that opens files for writing.
- Distiflow writes only inside `<repo>/.distiflow/`, `<repo>/../<repo>.distiflow/<task-id>/` and
  `~/.distiflow/upstream`.
- Upstream content holds no project facts (names, domains, commands). Scan `core/`, `skills/`,
  `agents/` and `README.md` with the deny-list (`distiflow scan --deny-file …`) before committing
  them.
- Exit codes: `0` ok · `1` refused or check failed · `2` needs confirmation · `3` environment missing.

## Tests

- Every test traces to a risk or scenario named in its docstring or comment.
- Integration by default: real `bin/distiflow` subprocess, real git repos in temp dirs.
- Each new case is seen failing first; its decisive failing line goes in the manifest as
  `red_evidence`.
