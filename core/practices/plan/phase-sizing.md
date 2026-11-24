+++
id = "phase-sizing"
stages = ["plan"]
kinds = ["feature"]
run_cost = "cheap"
gate = false
priority = 50
+++
Cut the work into units a reviewer can hold.
- Aim for about 400 changed lines per unit; about 1000 is the ceiling.
- Keep the largest unit within about four times the smallest; a wider spread means the cuts follow
  an accident instead of review risk.
- A unit that is too small for its own session joins the next related unit.
Why: oversized changes get shallow reviews; tiny ones pay the fixed cost of a session for little.
