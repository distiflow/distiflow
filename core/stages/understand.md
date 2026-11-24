### Purpose
Reach a shared understanding of what the task must change, and agree it with the developer.
Nothing is designed or built here: this stage settles what "done" means.

### Do
1. Read the task description, the linked items and the code it names. Facts you can look up are
   yours to find; decisions are the developer's.
2. Map the open decisions as a tree. Each round, ask every question whose prerequisites are settled,
   numbered, with your recommended answer first and its cost in one line. Wait for the answers.
3. Repeat until no branch is left silently assumed.
4. For new behaviour, write the user journeys, the sad paths (third-party failure, concurrency,
   repeats, hostile input, partial success) and acceptance scenarios in Gherkin, one behaviour each.
5. For a defect or an unknown cause, build a feedback loop that shows the problem: a failing test,
   a command, a script. Reproduce, then shrink the reproduction. Record the evidence, not a theory.
6. Show the result to the developer and get an explicit approval before the stage ends.

### Roles
- scout: read-only fact finding (where is X, what calls Y). One sub-agent takes the whole list of
  questions and returns one short report with file:line references.
- synth: turns the answers into journeys, scenarios or a reproduction summary.
Spawn each with the model and effort the brief's Models section names, within the sub-agent cap.

### Record
- `distiflow note <id> decision <text>` for every settled decision.
- `distiflow note <id> open <text>` for every question still open; `distiflow note <id> close <n>` when settled.
- The agreed behaviour or the reproduction goes to `.distiflow/tasks/<id>/spec.md`.

### Exit
1. For each gate in the brief: `distiflow gate pass <id> <gate> --evidence <text|@file>`.
2. `distiflow advance <id>`.
3. Tell the developer to start a fresh session and run `/distiflow:task resume <id>`.
