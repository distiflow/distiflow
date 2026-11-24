+++
id = "grill-the-request"
stages = ["understand"]
kinds = ["feature", "ux"]
run_cost = "medium"
gate = false
priority = 50
+++
Interview the developer until the task is understood the same way by both of you.
- Map the open decisions as a tree. Each round, ask every question whose prerequisites are settled,
  numbered, with your recommended answer first and its cost in one line.
- Look facts up yourself (files, tools, history); only decisions go to the developer.
- A question that depends on another open question waits for the next round.
- Stop when no branch is left silently assumed, and say so before moving on.
Why: most rework comes from a decision nobody made out loud.
