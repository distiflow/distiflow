+++
id = "perf-baseline-first"
stages = ["understand"]
kinds = ["perf"]
run_cost = "medium"
gate = true
evidence = "baseline numbers with the command that produced them"
priority = 80
+++
Measure before touching anything.
- Name the metric (latency at a percentile, throughput, memory, startup time) and the workload.
- Write the command that produces the number and run it several times; record the spread.
- Fix the environment: same data size, same machine class, warm or cold stated.
- The gate evidence is the numbers with the exact command.
Why: without a baseline, a change cannot be shown to help, and noise looks like progress.
