---
name: task
description: Start, resume, list or abandon a distiflow task. Use for "/distiflow:task <kind?> <description>", "/distiflow:task resume <id>", "/distiflow:task list" or "/distiflow:task abandon <id>".
---

# distiflow task

Arguments: `<kind?> <description>` | `resume <id>` | `list` | `abandon <id>`.
Kinds: feature, fix, debug, perf, ux.

1. `list`: run `distiflow task list` and show its output as is.
2. `resume <id>`: run `distiflow task resume <id>`. If it exits 2, show the message and ask the developer
   before running the takeover it names. Then read the brief file it prints and follow it.
3. `abandon <id>`: run `distiflow task abandon <id>`, show what would be lost, and only after the
   developer says yes run it again with `--confirm`.
4. A new task without a kind: infer the kind from the description, then ask the developer with
   AskUserQuestion, the inferred kind first with a one-line reason. Only then run
   `distiflow task start <kind> <description>`.
5. After start or resume, follow the stage text in the brief. Record decisions with `distiflow note`.
   A gate passes only with real evidence. End each stage with the Exit steps the brief gives.
6. When a distiflow command exits 3, show its message verbatim; it names what is missing.
