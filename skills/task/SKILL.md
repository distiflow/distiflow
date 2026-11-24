---
name: task
description: Start, resume, list or abandon a golden task. Use for "/golden:task <kind?> <description>", "/golden:task resume <id>", "/golden:task list" or "/golden:task abandon <id>".
---

# golden task

Arguments: `<kind?> <description>` | `resume <id>` | `list` | `abandon <id>`.
Kinds: feature, fix, debug, perf, ux.

1. `list`: run `golden task list` and show its output as is.
2. `resume <id>`: run `golden task resume <id>`. If it exits 2, show the message and ask the developer
   before running the takeover it names. Then read the brief file it prints and follow it.
3. `abandon <id>`: run `golden task abandon <id>`, show what would be lost, and only after the
   developer says yes run it again with `--confirm`.
4. A new task without a kind: infer the kind from the description, then ask the developer with
   AskUserQuestion, the inferred kind first with a one-line reason. Only then run
   `golden task start <kind> <description>`.
5. After start or resume, follow the stage text in the brief. Record decisions with `golden note`.
   A gate passes only with real evidence. End each stage with the Exit steps the brief gives.
6. When a golden command exits 3, show its message verbatim; it names what is missing.
