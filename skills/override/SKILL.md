---
name: override
description: Bend an upstream distiflow stage, practice or TOML file to this project by making a local override. Use for "/distiflow:override <path under core/>".
---

# distiflow override

1. Run `distiflow override <path under core/>`. It copies the upstream file into `.distiflow/overrides/`
   with a first line that records the upstream hash. `distiflow override list` shows overrides and drift.
2. Rewrite the body in this project's vocabulary. Keep line 1 exactly as written.
3. Run `distiflow check --local` and fix anything it reports.
4. Tell the developer to commit the override; later upstream changes to that file are reported as drift.
