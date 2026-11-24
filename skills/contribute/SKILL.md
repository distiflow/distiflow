---
name: contribute
description: Turn a lesson from this project into a generic practice and send it upstream as a change request. Use for "/golden:contribute <idea>".
---

# golden contribute

1. Run `golden contrib new <idea>`. It prints where to write the draft.
2. Write `draft.md` there: `+++` TOML frontmatter (id, stages, kinds, signals, run_cost, gate,
   evidence, priority) and a body that says what to do and why, in generic words. No project names,
   hosts, commands or ticket ids.
3. Run `golden contrib check <slug>` and show the developer its full output: classification, every
   check, replaced terms, the diff and the similar upstream practices. Fix failures in `draft.md`
   and check again.
4. Propose a verdict with the top five similar practices: new, extends:<id> or duplicate:<id>.
   Ask the developer; then run `golden contrib confirm <slug> --verdict <verdict>`.
5. Send only after an explicit yes: `golden contrib send <slug>`. Show the link it prints. If it
   exits 2 about a similar open contribution, ask whether to `--update` that one or send `--new`.
   If it exits 3, show the message verbatim.
