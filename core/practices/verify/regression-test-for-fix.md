+++
id = "regression-test-for-fix"
stages = ["verify"]
kinds = ["fix"]
run_cost = "cheap"
gate = true
evidence = "the test that failed before the fix and passes after"
priority = 80
+++
Prove the fix with the test that pins it.
- Show the regression test failing on the code before the fix and passing after it.
- It lives where the defect lives, at the layer where the failure was observable.
- Check the callers of the changed code: the same defect may hide in a sibling path.
Why: a fix without its regression test comes back.
