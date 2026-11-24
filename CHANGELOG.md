# Changelog

## [Unreleased]

### Added

- `distiflow contrib new --edit <path>` proposes a change to an upstream stage, practice or shared
  skill, starting from the project's override when there is one. `check` shows the change against
  upstream; `confirm --verdict edit`; `send` changes exactly that file.
- Verify and review stages: for a change to the UI, check the running app with Claude in Chrome
  first; the Playwright MCP only when the Chrome extension is not connected.
- Shared skills: `distiflow contrib new --skill <dir>` sends a personal skill's `SKILL.md`
  upstream through the same check, confirm and send steps as practices. Merged skills live in
  `skills/<name>/` and every install gets them as `/distiflow:<name>`. `distiflow check` validates
  them (name, description, `[skill] max_tokens`, hostile text; leaks and aliases with `--ci`).

### Changed

- `contrib send` refuses an `extends:` or `edit` change when the upstream file moved since the
  draft's base, instead of overwriting the newer upstream text.
- Renamed the plugin from `golden` to `distiflow`; the repository is now `distiflow/distiflow`.
  Commands are `/distiflow:*`, the CLI is `bin/distiflow`, and project state lives in `.distiflow/`,
  `<repo>.distiflow/` and `~/.distiflow/upstream`. Projects set up with the old name: rename
  `.golden/` to `.distiflow/` and `<repo>.golden/` to `<repo>.distiflow/`.
