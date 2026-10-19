---
reviewer: independent code review, read-only
date: 2026-10-19
reviewed: teaching from the course page (uncommitted working tree on b2d0329)
---

# Code review: teaching from the course page

Nine findings; all fixed the same day, each with a test that failed first, except where noted.

1. A file a teaching session wrote in the course (`playwright.py`) would be imported by the check's Playwright probe. Fixed: checks run with `python -I` from the skill folder; the uv fallback uses `--no-project --no-config`.
2. A user's own Claude settings can allow Edit and Write everywhere, which widens a session's reach past the course. Fixed: a PreToolUse hook (`scripts/teach_guard.py`) checks every edit's resolved path and fails closed; sessions load user settings only, never settings planted in the course. Verified once against the real CLI: an edit outside the course was blocked.
3. The course path went into permission patterns unescaped. Fixed: glob characters are escaped.
4. A script written into a lesson could start paid jobs from the page. Fixed: served course pages carry a Content-Security-Policy that runs only the three shared scripts; the guard keeps sessions out of `assets/`.
5. In phone-link mode, a token plus a rebinding Host could reach teaching. Fixed: teaching also requires a local Host name.
6. A refresh command that runs a file inside the course could be rewritten by a session. Mitigated: the command runs from the home folder, and SKILL.md says it must not run anything inside the course.
7. Sync could follow a symlink out of the course. Fixed: a linked `assets/` stops the sync; pages outside the course are skipped.
8. Stop and server shutdown missed the refresh and check processes. Fixed: every job step runs in its own process group, tracked and stopped with the job.
9. A second tab stayed idle after a 409. Fixed: a failed start shows the running job.

Found during review of the fixes: the guard compared names case-sensitively, which a case-insensitive disk defeats; fixed with casefolded comparisons. Also fixed: the course home page listed every lesson's question threads.
