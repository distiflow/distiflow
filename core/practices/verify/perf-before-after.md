+++
id = "perf-before-after"
stages = ["verify"]
kinds = ["perf"]
run_cost = "medium"
gate = true
evidence = "before/after numbers from the same command"
priority = 80
+++
Compare against the baseline with the same measurement.
- Rerun the baseline command on the same workload and environment; report both numbers and the spread.
- Check that nothing else regressed: memory, error rate, the other hot paths.
- A gain inside the noise is not a gain.
Why: performance claims without a like-for-like comparison are guesses.
