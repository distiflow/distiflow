---
name: contribute
description: Turn a lesson from this project into a generic practice, or share one of your own skills, and send it upstream as a change request. Use for "/distiflow:contribute <idea>" or "/distiflow:contribute --skill <dir>".
---

# distiflow contribute

1. Start the draft.
   - A practice: run `distiflow contrib new <idea>`. It prints where to write the draft. Write
     `draft.md` there: `+++` TOML frontmatter (id, stages, kinds, signals, run_cost, gate,
     evidence, priority) and a body that says what to do and why, in generic words.
   - A skill: run `distiflow contrib new --skill <dir>` on a folder that holds a `SKILL.md`
     (for example `~/.claude/skills/<name>`). It copies the skill into the draft. Shared skills hold
     only `SKILL.md`; inline any other file first.
   - Either way: no project names, hosts, commands or ticket ids.
2. Run `distiflow contrib check <slug>` and show the developer its full output: classification, every
   check, replaced terms, the diff and the similar upstream practices or skills. Fix failures in
   `draft.md` and check again.
3. Propose a verdict with the top five similar entries: new, extends:<id> or duplicate:<id>.
   Ask the developer; then run `distiflow contrib confirm <slug> --verdict <verdict>`.
4. Send only after an explicit yes: `distiflow contrib send <slug>`. Show the link it prints. If it
   exits 2 about a similar open contribution, ask whether to `--update` that one or send `--new`.
   If it exits 3, show the message verbatim.
5. After a skill is merged, everyone who installs distiflow gets it as `/distiflow:<name>`. The
   developer may delete their personal copy.
