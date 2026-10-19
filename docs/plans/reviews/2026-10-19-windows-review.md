---
reviewer: adversarial code review, read-only
date: 2026-10-19
reviewed: Windows support, restricted Claude runs and data rule (uncommitted working tree on d154097)
---

# Review: Windows support and isolated Claude runs

Trigger: a report from a Windows machine (stop and shutdown crash on `os.killpg`, `os.kill(pid, 0)` ends a process on Windows, `python3` may be a Store placeholder, the check needs Playwright's own Chromium, the learner's own Claude hooks and plugins ran inside every answer, lesson data rules too thin, the Teach button hard to find).

Fixed in this change: process trees end with `taskkill /T` on Windows and process groups elsewhere; the opener checks liveness with `tasklist`, detaches the server, and prints the real interpreter; Claude runs use `--restricted` with only the learner's settings `env` passed through; the system prompt and settings travel in files; permission rules use Claude Code's path form (`//c/Users/...`) and Edit rules only; the guard hook runs in exec form; text is read and written as UTF-8; the check falls back to the installed Chrome; the Teaching section sits under the lesson list and each lesson links to it; answers and lessons quote code, never data.

The adversarial review then found nine issues; eight were fixed with tests that failed first:

1. A stale `.serve.json` could make `--stop` end an unrelated process with a reused number. Fixed: stop only a server that answers on its port as this course, ask it to shut down cleanly first, force only after that.
2. The guard failed open if it could not start. Fixed: `"onFailure": "block"`, verified against the real CLI, plus deny rules for the protected files.
3. A non-ASCII course path could crash a Windows server at startup. Fixed: `-X utf8`.
4. `--stop` reported success while the server still ran. Fixed: it says so and keeps the record.
5. `SO_REUSEADDR` on Windows can let two programs share a port. Fixed: exclusive bind there.
6. Accepted: a Windows refresh command that leaves a background process behind is not stopped with the job (needs job objects). Documented in SKILL.md.
7. A failed launch left prompt files behind. Fixed.
8. `CLAUDE_CONFIG_DIR` was ignored. Fixed.
9. A course's own prompt file could drop the data rule. Fixed: the server appends it.

Found while verifying on a live course: a server started by the previous version gives no process number, so `--stop` treated it as stale and left it running. Fixed and tested.

Not verified: a run on native Windows. The Windows paths are covered by unit tests with the platform switched, by the documented behaviour of Claude Code, and by review.
