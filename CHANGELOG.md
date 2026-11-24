# Changelog

## [Unreleased]

### Added

- Shared skills: `distiflow contrib new --skill <dir>` sends a personal skill's `SKILL.md`
  upstream through the same check, confirm and send steps as practices. Merged skills live in
  `skills/<name>/` and every install gets them as `/distiflow:<name>`. `distiflow check` validates
  them (name, description, `[skill] max_tokens`, hostile text; leaks and aliases with `--ci`).

### Changed

- Renamed the plugin from `golden` to `distiflow`; the repository is now `distiflow/distiflow`.
  Commands are `/distiflow:*`, the CLI is `bin/distiflow`, and project state lives in `.distiflow/`,
  `<repo>.distiflow/` and `~/.distiflow/upstream`. Projects set up with the old name: rename
  `.golden/` to `.distiflow/` and `<repo>.golden/` to `<repo>.distiflow/`.
