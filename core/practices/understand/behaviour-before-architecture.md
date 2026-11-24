+++
id = "behaviour-before-architecture"
stages = ["understand"]
kinds = ["feature", "ux"]
run_cost = "medium"
gate = true
evidence = "approved journeys, sad paths and acceptance scenarios"
priority = 80
+++
Pin the behaviour before any design choice: no data model, endpoint or library yet.
- Write the user journeys that matter, one line each: who, starting state, action, outcome.
- For each journey list the sad paths: a third party failing, two actors at once, a repeated request,
  hostile or malformed input, an interrupted flow, partial success.
- Turn each into one Gherkin scenario with one behaviour.
- The developer approves the set; the gate evidence is that approval and where the set lives.
Why: architecture chosen before behaviour bends the behaviour to fit it.
