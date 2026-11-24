### Purpose
Decide how the change will be made, in steps small enough to check one at a time.
The plan names files, interfaces and tests, so the next stage needs no design decisions.

### Do
1. Read `.golden/tasks/<id>/spec.md` and the decisions recorded so far.
2. Where a decision has more than one defensible answer (data model, where state lives, a library,
   whether to extend existing code), list two or three options with their cost, recommend one,
   and get the developer's pick.
3. List the risks: for each behaviour, what input or timing makes it go wrong. Give each risk a home:
   a test at the cheapest layer that can fail for that reason, a review check, or an accepted risk
   with its cost written down.
4. Cut the work into units of about 400 changed lines, at most about 1000. Keep the largest unit
   within about four times the smallest. Small related units can share one session.
5. Each step names its files, the interfaces it produces or consumes, its tests and its commit.
6. The developer approves the plan before implementation starts.

### Roles
- planner: drafts the risk table and the steps from the spec. Read-only.
Spawn it with the model and effort the brief's Models section names, within the sub-agent cap.

### Record
- The plan goes to `.golden/tasks/<id>/plan.md`.
- `golden note <id> decision <text>` for each option chosen, with the reason.

### Exit
1. For each gate in the brief: `golden gate pass <id> <gate> --evidence <text|@file>`.
2. `golden advance <id>`. This creates the working copy for implementation.
3. Tell the developer to start a fresh session and run `/golden:task resume <id>`.
