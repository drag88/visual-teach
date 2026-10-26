---
reviewer: ce-doc-review (coherence, feasibility, security-lens, adversarial, design-lens, scope-guardian) plus cross-model Codex peers (security-lens, adversarial, whole-doc)
model: Claude Opus 5.5 (lead, feasibility, security-lens, adversarial); Claude Haiku 5.5 (coherence); Claude Sonnet 5.5 (design-lens, scope-guardian); Codex peers requested gpt-6.1-sol at xhigh (served model unverified, independence verified)
date: 2026-10-26
reviewed: docs/plans/2026-10-26-1427-feat-choose-answer-engine-plan.md (uncommitted draft, parent commit 9998a56)
---

# Document review: Choose Claude or Codex for answers and teaching

Non-interactive review. The plan's author authorised corrections to its implementation and verification sections that are needed to satisfy its Product Contract, preserving the three session-settled decisions. 17 corrections were applied, 4 observations are left as FYI, and no decision is left for the user.

## Applied

| # | Finding | Raised by | Change |
|---|---|---|---|
| 1 | The server would still run Codex after a failed preflight if the course default, a remembered choice or a handmade request named it (P1) | security-lens, Codex security-lens, Codex whole-doc | New R15: the server runs only engines that passed preflight and refuses requests naming an unusable one; U2 step 4 defines engine resolution; tests for both endpoints |
| 2 | If the sandbox ever wrongly allowed it, the preflight's `course.json` write probe would overwrite the learner's real settings (P1) | adversarial, feasibility, Codex whole-doc | The probe opens `course.json` for append and writes nothing; the lesson probe uses a scratch file it removes (KTD4, R9); test with a permissive fake sandbox |
| 3 | The after-check snapshot was taken before `sync_course`, so a skill update's asset sync would be reverted and blamed on Codex | adversarial, feasibility, security-lens | Snapshot after sync and right before the run (KTD3, U4, diagram); test with drifted assets |
| 4 | The after-check only ran on a successful Teach run | feasibility, security-lens | Compare-and-restore runs in `finally` on every exit (KTD3, U4); stop and failure tests |
| 5 | Restore had no meaning for created or deleted protected files | coherence, adversarial | Snapshot holds bytes plus file lists; restore edited and deleted files and remove new ones (U4) |
| 6 | Preflight did not prove the no-network, no-temp-write, outside-write and ask-write limits the plan promises | coherence, security-lens, Codex whole-doc | R9 and the preflight diagram cover all of them |
| 7 | The preflight ran once per server lifetime, so a Codex update mid-session ran untested and broke the executable grant | adversarial | Rerun when the resolved executable's path or mtime changes (KTD4); test |
| 8 | Preflight proved `codex sandbox` only, not `codex exec`, `exec resume` or `apply_patch` | adversarial, security-lens | The manual probe script adds model-driven exec, resume and apply_patch probes (U2, Verification Contract) |
| 9 | Codex shell commands would inherit the server's environment, secrets included | security-lens, Codex security-lens | KTD8: environment allowlist; sentinel-variable test |
| 10 | Pointing Codex at a server-owned config home would lose sign-in and sessions | feasibility | Ruled out in KTD8; new stop condition if no flag blocks course-level `.codex/` config and hooks |
| 11 | U1 and U2 depended on each other | coherence, scope-guardian | U1 reports engines on PATH; preflight filtering, `codex_unavailable` and their tests moved to U2 |
| 12 | The Goal Capsule protected KTD5 to KTD7 instead of the three settled decisions | coherence | Authority line names the three Product Contract Key Decisions |
| 13 | The ask profile could read the skill folder, wider than Claude answers | coherence | Skill folder read moved to the teach profile only (KTD2) |
| 14 | No page state when no engine is usable | design-lens, coherence, Codex whole-doc | R4 and U5: the page stays readable, the ask bar and Teach are disabled, and a reason line shows; tests |
| 15 | A remembered `vt-engine` could select an unavailable engine, and the reason hint was underspecified | design-lens, Codex whole-doc | U5: stale choices are ignored; the reason is a persistent `aria-live` line; test |
| 16 | Codex's Teach prompt would keep Claude's "no shell" and web-fetch lines | adversarial, feasibility | Assumptions and U4 vary the prompt by engine; test |
| 17 | Commentary messages would run into the answer and be logged as it | adversarial, Codex adversarial (+1 anchor, independence verified) | KTD7: only the last message of a turn is the answer; test |

Also folded in: the Teach panel's failure line names the reverted file and says lesson edits were kept (design-lens, with 4); ping reads the default engine live, so `--engine` needs no restart (feasibility, with 11).

## FYI observations

- The manual probe script now calls the server's own preflight, which removes the risk of two probe implementations drifting apart (scope-guardian; addressed by 8).
- A course-level Codex hook test would show R12 covers the riskiest config item (security-lens). Covered by the new stop condition in 10, and the build should add the test when it confirms the flag.
- Under the teach profile, editing or creating `assets/course.css` through a temp-file-and-rename tool was not probed (feasibility). Worth adding to the probe script.
- Real Codex may put shell commands in their own process groups, so Stop should be confirmed once against real Codex, not only the fake (feasibility).

## Residual concerns

- Hard links created inside the writable course by Codex's shell, pointing at an outside or protected file, were not probed (security-lens). The after-check covers protected files inside the course only.

## Coverage

| Reviewer | Status | Findings |
|---|---|---|
| coherence | done | 6 |
| feasibility | done | 6 |
| security-lens | done | 6 |
| adversarial | done | 6 |
| design-lens | done | 3 |
| scope-guardian | done | 2 |
| Codex security-lens (gpt-6.1-sol requested, xhigh) | done | 2 |
| Codex adversarial (gpt-6.1-sol requested, xhigh) | done | 1 |
| Codex whole-doc (gpt-6.1-sol requested, xhigh) | done | 3 |

Cross-model route `codex`, served model unverified, `independence_verified: true`. No reviewer failed.
