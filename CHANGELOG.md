# Changelog

Notable changes to visual-teach. Versions follow [semantic versioning](https://semver.org): new features raise the middle number, fixes the last one. `.claude-plugin/plugin.json` carries the same version, and Claude Code installs with auto-update get a release when that number changes.

## [1.3.1] - 2026-10-20

### Fixed

- After an update, a browser could keep old copies of the course's scripts with the new styles, which put the light/dark switch at the top left and hid Teach. The server now tells browsers to check each course file before reusing it.

## [1.3.0] - 2026-10-20

### Changed

- Teach moves from a section on the course home page to the top right of every page, beside the light/dark switch. While a teaching job runs, it shows how long the job has been going, on every page.
- The teaching panel shows the current step on one line, with earlier steps folded away, then the summary and whether the course check passed. A refresh, or a job that failed, shows its last lines of output.
- Step lines are short: course and source files by their path in the course or source folder, the skill's files by name, and long search patterns cut.

## [1.2.1] - 2026-10-20

### Fixed

- A missed tap-the-diagram question names the right part even when that part's line and bars are a separate group, instead of showing its id.
- The lesson rule for sequence diagrams now puts each actor's line and bars in a second group drawn under the arrows, so an arrow that crosses the line still takes its own tap. The 1.2.0 wording moved them into the box's group, which covers those arrows.

## [1.2.0] - 2026-10-20

### Added

- Try again after a missed multiple-choice or tap-the-diagram question. A retry is practice: the score still counts first tries, and review keeps the miss.
- A missed multiple-choice or tap-the-diagram question names the right answer in words at the start of its feedback, as well as marking it.
- The course home page says when missed questions are waiting to come back for review.
- `--no-lan` turns a course's phone link off again.

### Fixed

- The course check reports a quiz it cannot answer in one line, instead of crashing with a long error that "Ask Claude to fix these" would then send on.
- A Connect card brought back after a reload shows the topic asked about, not the instruction sent to Claude.
- A question whose answer never arrived comes back saying so, instead of as an empty card, and a follow-up to it carries the original question, the highlighted passage and, for Connect, the topic.
- A stopped answer or teaching job says it was stopped, instead of showing an exit code.
- Teaching sessions started from the page know they cannot search the web, and say so instead of writing facts they could not check.
- Syncing a course reads each page's tags as HTML, so it no longer adds a second copy of a tag written another way, which made the theme switch appear twice, and no longer counts a comment, a `data-src` or a preload link as loading a file.
- A port already in use by another course's phone link no longer stops a second course from starting.
- The follow-up box waits until the first answer has started.
- Diagram parts show clear keyboard focus.
- Lesson writing rules: in a sequence diagram, a tap on an actor's line counts as the actor, and no label may point a tap-the-diagram question at the wrong part.
- The server says "On this computer" instead of "On this Mac".

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
- Syncing a course replaces a shared file that is a link to somewhere else, even one with the same contents, instead of overwriting the file it points to.
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

[1.3.1]: https://github.com/drag88/visual-teach/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/drag88/visual-teach/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/drag88/visual-teach/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/drag88/visual-teach/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/drag88/visual-teach/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/drag88/visual-teach/releases/tag/v1.0.0
