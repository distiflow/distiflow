+++
id = "run-the-gates"
stages = ["verify"]
run_cost = "cheap"
gate = true
evidence = "output of every profile command"
priority = 80
+++
Run every check the project defines and keep the output.
- Run each command in the profile's commands table in the working copy: tests, lint, type checks, build.
- Record the result lines; a failure is fixed in the implement stage, then everything runs again.
- Never edit a check to make it pass.
Why: a change that passes only the checks someone remembered to run is not verified.
