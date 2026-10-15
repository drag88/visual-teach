---
reviewer: design review, read-only
date: 2026-10-15
reviewed: docs/plans/2026-10-15-1315-feat-learning-tools-plan.md, before it was written, against the uncommitted working tree on 1f24715
---

# Design review: learning tools batch

The plan's "Frozen contract" is this review's contract with three changes made when the plan was written: the "find uses" action is labelled "Where else"; the build split ran without a commit first (the owner had not approved commits); and later, the git-ignore rule was widened to parent folders after the server builder flagged the gap.

## Verdicts

1. **Open the source.** Build it, smallest form: one GET returning a whole size-capped file, a non-modal `<dialog>` panel with numbered lines, the cited ones tinted with the existing highlight token, and the selection bar working inside it. Keep `--code` rather than renaming it: the key is in every `course.json` and wired through `open_course.py` and ping. For a markdown corpus it behaves the same; with no folder, citations stay plain text.
2. **Source-aware actions.** Two `KIND_TASK` entries and two buttons. "Walk through" for any selection in `<pre>` or the panel; the uses action only when there is a source folder. Do not force Deep: Grep is available to both tiers.
3. **Trace lessons.** A rule only: a sequence or flowchart hero, `ol.turn` prose, one stop per step, each citing its source. Works for a bill through parliament or a molecule through glycolysis.
4. **General vs specific.** A rule plus a `.yours` block; everything else is portable. A `reference/carry-over.html` sheet ("Portable rule | How it showed up here"); a new course reads other courses' carry-over sheets. No cross-course code.
5. and 7. **Check my answer, Predict.** Merge: predict is the recall widget with different strings. Add self-mark buttons after reveal, which feed review without parsing Claude's verdict and work offline. "Check my answer" is an `ask.js` button after reveal when the server is up.
6. **Spaced review.** Thin version: quiz.js emits a DOM event, ask.js posts it, the server folds `quiz.jsonl`, the index shows due links. Enter on a miss, leave after three rights in a row, intervals 1, 3, 7 days. No localStorage fallback.

Keep quiz.js server-free (it dispatches a `quiz` CustomEvent, ask.js owns every fetch), so the three build units share no file.

## Risks raised

- File serving: resolve then check the parent; dotfile and git-ignore rules; `--` before the path; `no-store`. Claude's Read already sees the source folder, so the panel adds no new reach.
- Model-written citations are untrusted: built through `hold()`, escaped, refused by the server outside the folder.
- Existing tests to keep true: the exact tools list, two records per exchange, inert answer links, the graded-score arithmetic.
- Existing courses: `.src` stays plain without the server; missing quiz ids fall back to keys; rewording a question resets its review history (accepted).
- Phone: the bottom-sheet panel against the docked selection bar.
- `walk` on Quick may be thin for long blocks; watch the first real course before forcing Deep.
