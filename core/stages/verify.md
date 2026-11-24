### Purpose
Prove the change works, with evidence rather than assertion.

### Do
1. Run every command in the profile's `[commands]` table (tests, lint, type checks, build) in the
   working copy, and keep their output.
2. Walk every acceptance scenario or reproduction from `.distiflow/tasks/<id>/spec.md` and record how
   each one was shown to hold.
   For a change to the UI, walk them in the running app.
   Browser, in this order: 1) Claude in Chrome (`mcp__claude-in-chrome__*`): cheaper and faster,
   it reads only what you ask for. 2) Playwright MCP, only when the Chrome extension is not
   connected; say so first.
3. A failure goes back to the developer with the output; it is fixed in the implement stage
   (`distiflow stage reopen <id> implement`), not patched here.
4. A gate passes only with its evidence recorded.

### Roles
- gate-runner: runs the commands and returns only the result lines and failures.
Spawn it with the model and effort the brief's Models section names, within the sub-agent cap.

### Record
- Command output that a gate needs goes to `.distiflow/tasks/<id>/` as a file and is passed with
  `--evidence @<file>`.
- `distiflow note <id> open <text>` for anything left unproven.

### Exit
1. For each gate in the brief: `distiflow gate pass <id> <gate> --evidence <text|@file>`.
2. `distiflow advance <id>`.
3. Tell the developer to start a fresh session and run `/distiflow:task resume <id>`.
