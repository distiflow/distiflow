# distiflow

A Claude Code plugin that runs every task through six stages — understand, plan, implement, verify,
review, ship — with practices selected by the task's kind and the project's signals, gates that need
recorded evidence, a project profile with personal and file-level overrides, claimed and resumable
task state, and a sanitizing flow to send a lesson back upstream.

## Install

```
/plugin marketplace add distiflow/distiflow
/plugin install distiflow@distiflow
```

Needs Python 3.11 or newer and git. `gh` is needed only to open change requests.

## Commands

| Slash command | What it does |
|---|---|
| `/distiflow:init` | Propose a project profile and write it after you confirm each part |
| `/distiflow:task <kind?> <description>` | Start a task (kinds: feature, fix, debug, perf, ux) |
| `/distiflow:task resume <id>` · `list` · `abandon <id>` | Continue, list or drop tasks |
| `/distiflow:override <path>` | Make a local override of an upstream stage, practice or TOML file |
| `/distiflow:contribute <idea>` | Send a generic practice upstream as a change request |
| `/distiflow:contribute --skill <dir>` | Share one of your skills; once merged, every install has it as `/distiflow:<name>` |

The CLI behind them is `distiflow` (`bin/distiflow`): `task`, `note`, `gate pass`, `advance`,
`stage reopen`, `ship`, `worktree restore`, `brief`, `profile check`, `override`, `init`, `contrib`,
`check`, `scan`. Exit codes: 0 ok, 1 refused, 2 needs confirmation, 3 environment missing.

## Project layout

```
.distiflow/
  profile.toml          committed project profile (signals, commands, git, glossary, gates)
  profile.local.toml    personal layer, ignored by git; cannot change gates
  overrides/            local copies of upstream files, each recording the upstream hash
  practices/            project-only practices
  tasks/<id>/           task state, claim, brief snapshots, spec, plan, reviews (ignored)
  contrib/<slug>/       contribution drafts (ignored)
<repo>.distiflow/<id>/     the working copy of a task in the implement stage
```

Distiflow writes only inside `.distiflow/`, `<repo>.distiflow/` and `~/.distiflow/upstream`.

## License

MIT
