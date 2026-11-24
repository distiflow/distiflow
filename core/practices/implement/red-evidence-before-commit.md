+++
id = "red-evidence-before-commit"
stages = ["implement"]
run_cost = "cheap"
gate = true
evidence = "the failing line of each new test before its fix"
priority = 80
+++
Every new test is seen failing for the bug it names before it counts.
- Test first: run it before the code exists and keep its decisive failing line.
- Test after: remove the guard it pins, run it, record the failure, restore the guard.
- A test that still passes with its guard removed pins nothing; fix it or delete it.
- Never assert that a mock was called; assert the behaviour the user would see.
Why: a test that cannot fail gives confidence it has not earned.
