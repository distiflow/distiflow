+++
id = "choose-an-approach"
stages = ["plan"]
kinds = ["feature", "perf"]
run_cost = "medium"
gate = false
priority = 50
+++
When a decision has more than one defensible answer, compare before choosing.
- Typical cases: a data model, where state lives, a caching or retry strategy, a library,
  extending existing code versus adding new code.
- List two or three options; for each give what it costs, what it risks and what it rules out later.
- Recommend one, and let the developer decide.
- Record the choice and the reason with a task note.
Why: an unexamined first idea is expensive to undo once code depends on it.
