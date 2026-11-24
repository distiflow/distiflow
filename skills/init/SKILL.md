---
name: init
description: Set up distiflow in a repository by proposing a project profile and writing it after the developer confirms each part. Use for "/distiflow:init" or when distiflow says to run it.
---

# distiflow init

1. Run `distiflow init --propose`. It writes nothing.
2. Propose a `[glossary]` map: words in this project's code and docs that should read differently in
   shared practices (project names, product words), each mapped to a generic word.
3. Confirm with the developer, one AskUserQuestion round per group: signals, commands, git settings
   (worktrees, push, base), deny terms, glossary entries. Their answers win over the proposal.
4. Pipe the final TOML to `distiflow init --write -`. If it lists keys it would remove, show them and
   rerun with `--allow-removal` only after the developer agrees.
5. Tell the developer to commit `.distiflow/profile.toml` and `.distiflow/.gitignore`, or to add `.distiflow/`
   to `.git/info/exclude` if the profile stays local.
