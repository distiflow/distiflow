+++
id = "session-grouping"
stages = ["implement"]
kinds = ["feature"]
run_cost = "cheap"
gate = false
priority = 50
+++
Group work into sessions by context, not by count.
- Continue into the next unit while the session is still small, the unit is in the same repository,
  and it builds on files already read.
- Stop at the first of these that fails and say which.
- Starting fresh costs only the reload; a very long session costs more per step and works worse.
Why: context is the main cost of agent work and the main cause of late mistakes.
