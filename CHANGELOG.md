# Changelog

Notable changes to visual-teach. Versions follow [semantic versioning](https://semver.org): new features raise the middle number, fixes the last one. `.claude-plugin/plugin.json` carries the same version, and Claude Code installs with auto-update get a release when that number changes.

## [1.1.0] - 2026-10-20

### Added

- Install as a Claude Code plugin, with automatic updates once you turn them on in `/plugin`.
- `/visual-teach open <course>` opens a course to read and ask, with no teaching session, from whichever copy of the skill is installed.

### Changed

- Opening a course brings its shared reader files up to date, and restarts its reading server when the server runs older code or another copy of the skill. A running teaching job is not stopped for this, and its course files are left as they are; the update waits for the next open.
- When the server refuses to start a teaching job, the course page says why instead of showing a status number.

### Fixed

- The opener no longer reports a new server as started while the previous one is still shutting down.
- Teaching from the course page refuses to run once the skill folder its server started from has been removed, instead of running without its edit guard and checks.
- Syncing a course replaces a shared file that is a link to somewhere else, instead of overwriting the file it points to.
- With `--lan`, the link opened on this computer carries the token the server asks for, instead of getting a 401 error.

## [1.0.0] - 2026-10-19

First public release.

- Lessons built around one hero diagram, with quizzes: multiple choice, recall, predict, order, match and tap-the-diagram.
- Ask while reading: highlight text for Explain, Simpler, More, Connect or your own question; answers appear beside the paragraph, with follow-ups in the same card.
- A source panel for `path:line` citations, with Walk through and Where else on code.
- Check my answer, and spaced review of missed questions after 1, 3 and 7 days.
- Teaching sessions started from the course home page, with edits kept inside the course folder.
- Light and dark themes, a phone layout, and a phone link with `--lan`.
- Windows process and path handling.

[1.1.0]: https://github.com/drag88/visual-teach/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/drag88/visual-teach/releases/tag/v1.0.0
