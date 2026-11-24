### Purpose
Review the whole change with fresh eyes, against the agreed behaviour and the project's standards.

### Do
1. Pin the fixed point: the base and head of the change.
2. Check the change against the spec: missing behaviour, extra behaviour, misunderstood behaviour.
3. Check it against the standards: the repository's own instruction files and conventions.
4. Check each defect class against the diff: error handling that loses data, a missing check at a
   trust boundary, state shared across concurrent work, a resource that is opened and never closed,
   a query or loop that grows with the data, a test that would pass with the bug present.
5. Grade each finding by what a person using the software gets if it ships. Fix the serious ones in
   the implement stage (`distiflow stage reopen <id> implement`); record the rest.

### Roles
- reviewer: one read-only reviewer per axis (spec, standards) on a fresh context, given the diff
  as a file and this list. Findings come back with file:line, severity and the failing scenario.
Spawn each with the model and effort the brief's Models section names, within the sub-agent cap.

### Record
- The review goes to `.distiflow/tasks/<id>/reviews/`.
- `distiflow note <id> decision <text>` for each finding you decide not to fix, with why.

### Exit
1. For each gate in the brief: `distiflow gate pass <id> <gate> --evidence <text|@file>`.
2. `distiflow advance <id>`.
3. Tell the developer to start a fresh session and run `/distiflow:task resume <id>`.
