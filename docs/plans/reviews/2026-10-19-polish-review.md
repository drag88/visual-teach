---
reviewer: adversarial code review, read-only
date: 2026-10-19
reviewed: polish pass on the code changed since 798f8da (uncommitted working tree on 2ad669e)
---

# Review: polish pass

Goal: the same behaviour with less repetition. Three read-only passes (reuse, quality, efficiency) looked at the code changed since the import, then an adversarial review tried to prove the result changed behaviour.

Applied:

- `serve.py`: `read_dict` replaces two copies of "a JSON object from a file, else {}" (`claude_env`, `settings`); `claude_args` holds the flags every Claude run starts with, so answers and teaching cannot drift apart on `--restricted`, `--strict-mcp-config` or `dontAsk`. Old and new code were compared in memory: `command`, `teach_command`, `settings` and `claude_env` give identical results with and without `--code` and `--web`, for both tiers, new and resumed.
- `open_course.py`: `token_of` replaces three copies of the phone-token parse; `URLError` dropped from two `except` tuples, since it is an `OSError`.
- `check_lessons.py`: `SELF_MARKED` names the self-marked quiz selector used in two places that must agree; each page is read once for the script check.
- `ask.js`: `paraOf`, `getJSON` and `BLOCK` replace three, seven and four copies. The teaching poll timer is cleared before it is set again, so a start from the page cannot leave two polling loops running.
- Tests use `check_lessons.launch`, so they run where only the installed Chrome exists.

The adversarial review found three problems, all fixed:

1. A shared `tracked` context manager for `run` and `call` dropped a process from the live set without stopping it when writing the prompt failed (Windows raises `EINVAL` there), or when a stop failed, so a server shutdown could no longer end it. Reproduced against both versions. Fixed by restoring `run` and `call` exactly as they were; the six lines saved were not worth the lifecycle risk.
2. The same change registered the process after starting the stderr thread, so a failed thread start left an unregistered process. Fixed by the same revert.
3. `python3 -m scripts.test_quiz` could not import `check_lessons`. Fixed: the test puts its own folder on the path first, as `test_reader.py` does.

Skipped, with the reason:

- Removing the "stopped" checks inside the teaching jobs: `run` also returns `None` on a read error, and the inline check keeps a stopped job from showing "done" for a moment, which ends the page's polling.
- Parsing the question log once per follow-up, caching the log, and dropping the Playwright probe before the course check: unnoticeable next to a Claude run or a 5 to 15 minute teaching job.
- Polling instead of the fixed waits in the tests: each one proves that something did not happen, so it has to outlast the fake Claude's quiet stretch.
- One browser per test run, one source for the citation patterns, a shared host check, a shared protected-file list for the guard and the deny rules: more change than value, and the last two are safety layers whose different matching is deliberate.

Checks after the fixes: `test_serve.py` (45) and `test_open_course.py` (7) on the current Python and on 3.9, `test_quiz.py` (also as `python3 -m scripts.test_quiz`), `test_reader.py`, `ruff check --select F`, `node --check ask.js` and `git diff --check`. The final diff was not sent back for a second review; it is the reviewed diff minus the reverted hunks, plus the two-line import fix checked above.
