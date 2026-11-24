---
name: contribute
description: Turn a lesson from this project into a generic practice, share one of your own skills, or change an upstream stage, practice or skill (for example a better tool for a step), and send it upstream as a change request. Use for "/distiflow:contribute <idea>", "/distiflow:contribute --skill <dir>" or "/distiflow:contribute --edit <path>".
---

# distiflow contribute

1. Start the draft.
   - A practice: run `distiflow contrib new <idea>`. It prints where to write the draft. Write
     `draft.md` there: `+++` TOML frontmatter (id, stages, kinds, signals, run_cost, gate,
     evidence, priority) and a body that says what to do and why, in generic words.
   - A skill: run `distiflow contrib new --skill <dir>` on a folder that holds a `SKILL.md`
     (for example `~/.claude/skills/<name>`). It copies the skill into the draft. Shared skills hold
     only `SKILL.md`; inline any other file first.
   - A change to an upstream file: run `distiflow contrib new --edit <path>` with
     `core/stages/<stage>.md`, `core/practices/<stage>/<id>.md` or `skills/<name>/SKILL.md`. It
     copies this project's override of that file when there is one, else the upstream text. Edit
     `draft.md`; say why in the text when you change a tool or an order.
   - Every way: no project names, hosts, commands or ticket ids.
2. Run `distiflow contrib check <slug>` and show the developer its full output: classification, every
   check, replaced terms, the diff and the similar upstream practices or skills (for an edit: the
   change against upstream). Fix failures in
   `draft.md` and check again.
3. Propose a verdict with the top five similar entries: new, extends:<id> or duplicate:<id>; an
   edit is always `edit`.
   Ask the developer; then run `distiflow contrib confirm <slug> --verdict <verdict>`.
4. Send only after an explicit yes: `distiflow contrib send <slug>`. Show the link it prints. If it
   exits 2 about a similar open contribution, ask whether to `--update` that one or send `--new`.
   If it exits 3, show the message verbatim. If it says the file changed upstream, update distiflow,
   discard the draft and start the edit again.
5. After a skill is merged, everyone who installs distiflow gets it as `/distiflow:<name>`. The
   developer may delete their personal copy.
