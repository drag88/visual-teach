---
reviewer: ce-code-review (correctness, security, testing, reliability, maintainability, agent-native) plus cross-model Codex adversarial pass
model: Claude Opus 5.5 (lead, correctness, security); Claude Sonnet 5.5 (testing, reliability, maintainability, agent-native); Codex requested gpt-6.1-sol at xhigh (served model unverified, independence verified)
date: 2026-10-26
reviewed: feat/choose-engine 9998a56..82c1489
---

# Code review: Choose Claude or Codex

Verdict: ready with fixes. Five findings, all fixed or removed in d55c69d.

| # | Severity | Finding | Outcome |
|---|---|---|---|
| 1 | P1 | A Codex Teach job published its final state before restoring protected files, so an overlapping job could reinstate a forbidden edit | Removed with the after-session restore (R11 dropped) |
| 2 | P1 | The restore followed planted symlinks and could overwrite a lesson or a file outside the course | Removed with the restore |
| 3 | P2 | `open_course.py --engine` during a Codex Teach run was reverted and blamed on Codex | Removed with the restore |
| 4 | P2 | A sandbox probe that timed out counted as a successful denial, so Codex could be offered unproven | Fixed: counts as failed, retried, not cached |
| 5 | P2 | The real-Codex probe accepted a prose refusal as proof the patch was blocked | Fixed: only a file_change on course.json counts; otherwise reported as not proven |

Also fixed from the agent-native review and residual risks:
- The Codex teaching prompt now says to run no scripts, and names the sandbox's limits.
- Non-fatal Codex error notices no longer discard an answer.
- Claude requests never wait on the Codex preflight.
- The decoy is placed outside every readable folder.
- Codex shows a plain "off on Windows" reason.
- SKILL.md documents `--engine` and the `engine` field in the question log.

Accepted, not fixed:
- `serve.py` is 300 lines larger, and the Codex code could move to its own module.
- `PROTECTED` and `teach_guard.py` keep separate lists, which differ on purpose (`.codex/` only matters on Codex).
- `run()` reads the model from the `-m` argument.
- A hung Codex can still delay page pings while the preflight holds its lock.
- An intermittent unit-test failure was seen twice in about 15 full runs, both under load, and never reproduced.

Verification after the fixes:
- Unit suites: 125 tests OK.
- `test_reader.py`: OK.
- `tests/verify_teach_guard.py` and `tests/test_release.py`: OK.
- `tests/probe_codex_sandbox.py`: all checks hold in 3 of 4 runs. The other run had two model-driven checks fail, most likely because the cheap model did not run the probe script. The `course.json` patch probe is reported as not proven when the model declines to try it.
- Live Teach next lesson on Codex: wrote `0003-tool-contracts.html`, and the course check passed after a re-sync.
