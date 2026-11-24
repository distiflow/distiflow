+++
id = "defect-classes"
stages = ["review"]
run_cost = "medium"
gate = true
evidence = "each defect class checked against the diff"
priority = 80
+++
Check the change against the defect classes that recur.
- Error handling: a failure swallowed, retried forever, or losing data.
- Trust boundary: input used before it is checked; a secret or personal data exposed.
- Shared state: two requests or tasks touching the same data at once.
- Resources: something opened and never closed; a cache that never shrinks.
- Growth: a query or loop whose cost grows with the data.
- Tests: a test that would pass with the bug present.
Record each class as checked, with file:line for every finding.
Why: these classes cause most escaped defects and are easy to miss in a line-by-line read.
