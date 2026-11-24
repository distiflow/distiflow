+++
id = "spec-review"
stages = ["review"]
kinds = ["feature"]
run_cost = "expensive"
gate = false
priority = 50
+++
Review on two axes, each on a fresh context.
- Spec: does the change do what the agreed behaviour says, no more and no less?
- Standards: does it follow the repository's own instruction files and conventions?
- Give each reviewer the diff as a file, the fixed point (base and head) and its source documents.
- Merge the two reports; grade each finding by what a user gets if it ships.
Why: one reviewer checking both axes tends to miss one of them.
