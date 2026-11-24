+++
id = "ux-running-app-check"
stages = ["verify"]
kinds = ["ux"]
run_cost = "medium"
gate = true
evidence = "what was checked in the running app"
priority = 80
+++
Check the journeys in the running app, not only in tests.
- Walk each journey: every state (empty, loading, error, success), small and large screens.
- Use the keyboard alone once; check focus order, labels and contrast.
- Record what was checked and what was seen, with screenshots when they help.
Why: unit tests do not see layout, focus or a confusing step.
