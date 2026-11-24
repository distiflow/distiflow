+++
id = "reproduce-before-fixing"
stages = ["understand"]
kinds = ["fix", "debug"]
run_cost = "cheap"
gate = true
evidence = "the reproduction command and its failing output"
priority = 80
+++
Build a feedback loop that shows the problem before changing any code.
- In order of preference: a failing test, a command or script, a request replayed, a recorded input.
- Make it fast and deterministic; shrink the input until every part matters.
- For a flaky problem, raise the rate (loops, load, fixed seeds) until it fails reliably.
- The gate evidence is the command and the decisive line of its failing output.
Why: a fix with no reproduction cannot be shown to work, and its regression test has nothing to pin.
