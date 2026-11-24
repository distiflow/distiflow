+++
id = "subagent-budget"
stages = ["understand", "plan", "implement", "verify", "review", "ship"]
run_cost = "cheap"
gate = false
priority = 30
+++
Spawn sub-agents sparingly; each starts cold and rediscovers context.
- Never one per item: one sub-agent takes the whole list and returns one report.
- Give it exactly what it needs: the question, the files, the commands.
- Cap reports at a few hundred words, findings only, with file:line.
- Prefer a search command over a sub-agent for anything mechanical.
Why: every sub-agent pays the full reading cost again, and its report lands back in your context.
