### Purpose
Build the plan, step by step, in the task's working copy. Every change is proved by a test that was
seen failing first.

### Do
1. Work only in the working copy that `golden advance` created (the brief's task state names it).
2. Take the next plan step. Write its test first and run it: it must fail for the reason it names.
   Keep the decisive failing line; it is the step's evidence.
3. Write the smallest code that makes the test pass. Run the step's tests, then the full suite
   before each commit.
4. Test at the outermost layer that can fail for that reason and still runs in seconds. One
   behaviour, one layer; the same assertion with different inputs is one table.
5. Never assert that a mock was called. Test this repository, not its dependencies.
6. Commit as the plan says. When the plan is wrong, decide the smallest change that keeps the
   spec, record it, and continue.

### Roles
- worker: one sub-agent per plan step when the step is large and independent; give it the step's
  text, the files it touches and the commands to run. Never two workers on the same files.
Spawn each with the model and effort the brief's Models section names, within the sub-agent cap.

### Record
- `golden note <id> decision <text>` for every deviation from the plan, with its cost if wrong.
- Each new test's decisive failing line goes into `.golden/tasks/<id>/plan.md` next to its step.

### Exit
1. For each gate in the brief: `golden gate pass <id> <gate> --evidence <text|@file>`.
2. `golden advance <id>`.
3. Tell the developer to start a fresh session and run `/golden:task resume <id>`.
