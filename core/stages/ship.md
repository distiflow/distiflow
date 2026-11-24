### Purpose
Hand the change over: branch up to date, checks green, a change request open or a hand-off written,
and the working copy cleaned up once the change is merged.

### Do
1. Commit everything in the working copy; ship refuses uncommitted changes.
2. Run `golden ship <id>`. It decides from the profile:
   - when the profile allows pushing, it pushes the branch and opens or updates the change request;
   - when the profile forbids pushing, it prints the hand-off commands for the developer.
3. Never push when the profile forbids it, by any other route. Never merge: merging is the
   developer's decision.
4. After the developer merges, run `golden ship <id>` again. It removes the working copy and marks
   the task done. If the merge is not visible to golden, the developer confirms it with `--merged`.
5. If cleanup fails, ship says so and leaves the task as cleanup pending; fix the cause and rerun.

### Roles
- gate-runner: runs the profile commands one last time when asked.
Spawn it with the model and effort the brief's Models section names, within the sub-agent cap.

### Record
- `golden note <id> decision <text>` for anything handed over by hand.

### Exit
1. `golden ship <id>`, then again after the merge.
2. Tell the developer the task is done, or what is waiting on them.
