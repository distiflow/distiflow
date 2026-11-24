+++
id = "debug-by-reading-errors"
stages = ["understand"]
kinds = ["fix", "debug"]
run_cost = "cheap"
gate = false
priority = 50
+++
Read the error before forming a theory.
- Read the full message, the stack and the first failing line; check the input that produced it.
- List hypotheses, each with the observation that would prove it wrong; test the cheapest first.
- Change one thing at a time and keep what each experiment showed.
- A symptom patched where it appears is not a fix; follow it to the root cause.
Why: guessing burns more time than reading, and the guess is usually wrong.
