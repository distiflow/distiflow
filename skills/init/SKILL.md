---
name: init
description: Set up golden in a repository by proposing a project profile and writing it after the developer confirms each part. Use for "/golden:init" or when golden says to run it.
---

# golden init

1. Run `golden init --propose`. It writes nothing.
2. Propose a `[glossary]` map: words in this project's code and docs that should read differently in
   shared practices (project names, product words), each mapped to a generic word.
3. Confirm with the developer, one AskUserQuestion round per group: signals, commands, git settings
   (worktrees, push, base), deny terms, glossary entries. Their answers win over the proposal.
4. Pipe the final TOML to `golden init --write -`. If it lists keys it would remove, show them and
   rerun with `--allow-removal` only after the developer agrees.
5. Tell the developer to commit `.golden/profile.toml` and `.golden/.gitignore`, or to add `.golden/`
   to `.git/info/exclude` if the profile stays local.
