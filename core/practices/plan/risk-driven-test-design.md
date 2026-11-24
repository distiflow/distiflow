+++
id = "risk-driven-test-design"
stages = ["plan"]
kinds = ["feature", "fix", "perf"]
run_cost = "medium"
gate = true
evidence = "the risk table with a home for every risk"
priority = 80
+++
Decide what to test from the risks, not from the code.
- For each behaviour, list what input, timing or dependency makes it go wrong.
- Give every risk one home: a test at the cheapest layer that can fail for that reason,
  a review check, or an accepted risk with its cost written down.
- Integration over real dependencies is the default; unit tests for pure branchy logic only.
- Same assertion with different inputs is one table, not many tests.
Why: tests written from code cover what the code does, not what can break.
