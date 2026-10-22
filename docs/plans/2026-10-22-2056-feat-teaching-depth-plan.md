---
title: Teach any subject with depth, clarity and challenge - plain words, whole ideas
type: feat
date: 2026-10-22
task_folder: none (single-session change plus one bounded test)
---

# Plain words, whole ideas

**Need.** Some lessons the skill produces are thin: names, one-line definitions and a renaming analogy, with no reason, consequence or new case. Others from the same skill are strong. The skill must teach any subject with depth and plain language, and vary its shape with the subject.

**Smallest thing that meets it.** Replace the conflicting rules in `SKILL.md` section 2 and six one-line rules elsewhere, align the three templates and the live-answer prompt, one word in the checker, one line in `serve.py`. About 35 lines across 7 files, net growth near zero. Then one bounded before/after test on three subjects, and a 60-line library script.

## Evidence

Verified on 22 Oct 2026. `~/.claude/skills/visual-teach` and `~/.codex/skills/visual-teach` both resolve to `/Users/asreenivas/code/visual-teach`; repo clean on `main` at v1.3.1; no repo CLAUDE.md or AGENTS.md. Courses: `~/learn/codex-harness` (2 lessons, thin) and `~/learn/adk` (4 lessons, strong). Lesson 2 of codex-harness and the later edits to lesson 1 came from the Teach button, which runs Opus (`scripts/serve.py:41`, `:446`); nothing records who wrote lesson 1 first.

Learner evidence: codex-harness has one question thread, "what repair workshop and who is the owner here?". adk has about 27 threads with why, what-if and "how would an expert do this" questions, 12 quiz answers (6 missed first time), and 4 learning records that steered later lessons. A count of reasoning words per 100 words did not separate thin from strong (1.3 to 3.6, adk lesson 1 lowest), so no automated depth measure is proposed.

### Rules that encourage weak teaching

- `SKILL.md:47`, `:128` and `starter/ask-prompt.md:5` set a child audience. "Simplify the words, never the facts" protects facts, not reasons. Codex-harness lesson 1's seven walk paragraphs are each a name, a definition and a citation. The rule permits this; it is not proven to cause it, since adk under the same rule carries reasons.
- `SKILL.md:49-50`, `starter/reference.html:29` and `ask-prompt.md:6` make the analogy mandatory and first. Codex-harness lesson 1 opens with the workshop before naming anything real; its hero diagram carries 7 real names plus 7 workshop names, where adk lesson 1's diagram puts a job under each real name; its parts sheet has a column of pure renamings; its MISSION.md Constraints copy "one workshop analogy" as if it were the learner's constraint. Counter-evidence: adk learning record 0001 shows a comparison (checkpoint versus sticky note) resolving a confusion the learner had twice. So comparisons become optional and must explain a behaviour, not banned.
- `SKILL.md:39`, `:67`, `:81` and `starter/lesson.html:15` give one shape for every subject (map first, mechanism diagram, diagram quiz, fixed order). No harm shows in the two courses, both systems topics, and map-first was the learner's own ask on 13 Oct (adk NOTES.md). The risk is for subjects with no mechanism: `:67` allows a table, `:81` then demands a diagram quiz anyway.
- `SKILL.md:103` ("never an invented one") conflicts with labelled made-up examples; codex-harness lesson 2 already breaks it ("1 passed" from a made-up project).
- `scripts/serve.py:45` makes Simpler mean "more simply", which reads as fewer reasons as easily as plainer words.
- Kept: the 25-word sentence cap (`scripts/check_lessons.py:24`, `SKILL.md:126`). All six lessons pass it, strong and thin alike.

### Good rules not followed

- METHOD.md's tangible win tied to the mission (`vendor/teach/METHOD.md:53`, `:73`): codex-harness lesson 1's win is "name the job of each part"; the mission's success items are separate, trace and build.
- Knowledge then practice with feedback (`METHOD.md:93`): codex-harness lesson 1's four practice items re-ask its own sentences; adk lessons 2 to 4 ask about diffs the lesson never showed.
- Glossary (`METHOD.md:136`): adk has none, codex-harness's is empty.

### Missing information or source access

`~/learn/codex-harness/RESOURCES.md` Gaps and NOTES.md Session 2 record that both doc sites failed with a certificate error, so lesson 2 reused only claims lesson 1 had made, and no Codex source checkout is attached. Obeying "never trust your parametric knowledge" (`METHOD.md:30`) with no reachable source yields fewer claims and thinner prose. The error matches a corporate proxy's certificate interception on this Mac; whether the Teach job's `claude` run received the certificate variables (`serve.py` `claude_env`) is unverified. Neither MISSION.md records the learner's starting knowledge.

### Unverified

Who wrote codex-harness lesson 1. Whether rules or source access produced the thinness (one course per condition; U3 separates them). That the learner's 13 Oct "ELI5" ask meant words only (this brief says so; the skill read it as audience level). Any retention effect: no spaced-review outcome observed yet.

## The standard

A lesson establishes the learner's purpose, starting knowledge and the capability they want; grounds every claim in material fit for the subject; explains each idea's reason, consequence and limit in plain words; names real terms as it explains them; picks its hero (diagram, table, worked example or passage) and its practice (explain, judge, choose, perform) from the subject and the mission; uses questions and misses to steer the next lesson; and records what was shown, not what was presented. None of these is a required section. A code block, experiment, mechanism diagram or Build / Break / Fix is never required by the subject's shape alone.

## Decisions (22 Oct 2026)

- Test subjects: the codex-harness lesson 1 brief as the systems control; interpretive: judge whether a company's profit is real from its cash-flow statement; practical: write a one-page decision memo for an executive.
- Every lesson has at least one practice item on a case the lesson did not show.
- Library: a static `~/learn/index.html` written by a stdlib script and refreshed by `open_course.py` on each open.
- How the work runs: U1, U2 and U4 are built by an Opus 5.5 subagent in a git worktree from this plan; Fable reviews the diff against the plan and the courses before U3 runs and before the Sol review in U5. The build starts only on the owner's go.
- Routine, decided here: comparisons optional with no cap on how many, recorded in NOTES.md when kept; map-first stays the default for systems topics; METHOD.md stays vendored and unchanged, overrides live in SKILL.md (`vendor/teach/UPSTREAM.md:9`); the ten-year-old line goes from the answer prompt entirely; one Sol xhigh review of the diff after the blind read, none before; release as 1.4.0.

### U1. SKILL.md rules

Replace section 2 (lines 45 to 54) with:

```markdown
## 2. Plain words, whole ideas

Every lesson, caption, quiz question and answer is in plain English: short sentences, one idea each, everyday words, each technical word explained the first time it appears. Simplify the words, never the facts and never the reasoning. The reader is an adult who wants to use this.

- **Explain, don't label.** Each idea the lesson teaches gets its reason, its consequence and its limit: why it is there or how it works, what goes wrong when it is missing or misread, and where it stops applying. A name with a one-line definition is a glossary entry, not teaching.
- **Real names first.** Give the real term in the same sentence as its plain meaning, so the learner can use it with the source and with other people. Code and file names come after the plain explanation.
- **Comparisons are optional.** Use an everyday comparison only after the real thing is named, only when it explains a behaviour the plain words did not, and say where it stops being true. Drop it when it only renames the parts, or when a learner asks what it means. Write any comparison the course keeps using in NOTES.md so live answers stay consistent.
- **Examples carry ideas.** Show the idea in one concrete case, then state the idea the case shows. Prefer real cases from the sources; a made-up case is fine when the lesson says it is made up and it would really work that way.
- **Short means few ideas, each whole.** METHOD.md's "short, completable very quickly" means two or three ideas explained fully in about ten minutes, not many ideas named once.
- **No labels saying it's simple.** No "In plain English" boxes or "ELI5" headings; the whole page is plain.
- Quiz feedback explains why in one or two plain sentences.
```

One-line edits:

| Where | New wording |
|---|---|
| `SKILL.md:30` (Catch up) | Add: "For a new course the mission interview also asks what the learner already knows and what they must be able to do; both go in MISSION.md. Its Constraints hold the learner's limits (time, device, prior knowledge), never this skill's format rules." |
| `SKILL.md:39` | "Lesson 1 is the map when the topic is a system of parts: every core part in one diagram, each with a one-line definition and, when the learner has a real system, where it lives there. For a skill or a topic to interpret, lesson 1 is the first case the learner must handle, and the map becomes a reference sheet. Close-ups come after." |
| `SKILL.md:43` | "the analogy mapping (section 2)" becomes "any comparison in use (section 2)". |
| `SKILL.md:67` | "One hero. One picture, table, worked example or quoted passage carries the lesson's core idea and sits before the prose, which walks it part by part. A mechanism gets a diagram, a list or a comparison a table, a skill a worked example, a text the passage." |
| `SKILL.md:81` | "Quiz on the picture. When the hero is a diagram, at least one practice item uses it: a spot question, or an order question built from its steps." |
| `SKILL.md:101` (Quizzes) | Add: "Match practice to the mission: explain back for understanding, read and judge a case for review, choose and justify for a decision, do and check for a skill. At least one item per lesson is a case the lesson did not show; repeating the lesson's own example shows reading, not understanding." |
| `SKILL.md:103` | "Use the real outcome when there is one (run the code, quote the source). A made-up case is fine when the lesson says so and the outcome is what would really happen." |
| `SKILL.md:128` | "Read each lesson as the learner would. Is every paragraph plain on one read? Does each idea come with its reason and what follows from it? Does a practice item ask about a case the lesson did not show? Rewrite what fails." |

Check: `git diff --stat` shows SKILL.md only; read the file once end to end for a rule that now contradicts section 2.

### U2. Templates, prompts, checker

| Where | Change |
|---|---|
| `starter/lesson.html:15` | Comment: "Usual order: win, hero (diagram, table, worked example or passage), prose that walks it with each idea's reason and consequence, practice with at least one new case, read next. Drop what the subject does not need; keep nav, win, practice and read next." |
| `starter/lesson.html:25` | Win placeholder: "What the learner can do after this lesson, on a case it did not show." |
| `starter/lesson.html:49` | Walk placeholder: "Prose that walks the hero part by part: what each part is, why it is there, what follows from it, with a citation for each claim." |
| `starter/index.html:19` | Placeholder: "First lesson: the map for a system, or the first case to handle". |
| `starter/reference.html:29-30` | Column "Picture it as" becomes "In plain words"; cell "The course's comparison, in a few words" becomes "What it is, in a few words". |
| `starter/ask-prompt.md:5` | "Plain, simple English: short sentences, one idea each, everyday words, each technical word explained in the same sentence. Keep the reasoning: say why and what follows, not only what." |
| `starter/ask-prompt.md:6` | "If NOTES.md records a comparison the course uses and it helps this answer, use that one and say where it stops. Otherwise answer in real terms, and never add a new comparison. When the learner asks what a comparison means, answer in real terms." |
| `scripts/serve.py:45` | `"simpler": "Explain the highlighted passage again in plainer words and smaller steps, in about three sentences, keeping the reason."` |
| `scripts/check_lessons.py:41` | `!el.closest("pre, nav, footer, .read, blockquote")` so a quoted source sentence over 25 words does not fail a lesson that quotes its text. |

Unchanged: `vendor/teach/METHOD.md` and the format files (vendored); SKILL.md sections 3, 5, 8, the trace and carry-over rules (`:84-85`, strongest material in adk), quiz widgets and review; `teach_prompt` (already "read SKILL.md and follow it"); every other `KIND_TASK` line; the sentence cap. No test pins the changed strings (`scripts/test_serve.py:75`, `scripts/test_reader.py:50` only write a NOTES.md fixture).

Check: `python3 scripts/test_serve.py`, `test_reader.py`, `test_quiz.py`, `test_open_course.py` pass; `check_lessons.py` on `~/learn/adk` passes as before.

### U3. Before/after test

Same brief, same sources, two versions. Three empty course folders per version, each with identical MISSION.md, RESOURCES.md and a local `--code` folder of the primary texts (so source access is identical and the proxy is out of the picture). Lesson 1 only, through the Teach button (fixed model and no-shell path): "before" from a `git worktree` at v1.3.1, "after" from the edited checkout. Six Opus sessions of 5 to 15 minutes; this costs money and runs only after the owner says go.

Subjects: the codex-harness lesson 1 brief (control, systems); the cash-flow statement (interpretive); the one-page decision memo (practical).

Blind read by the learner, six pages shuffled, seven questions per page: plain on one read; each idea has its reason and consequence; five claims spot-checked against the source folder all hold; terms named and explained; at least one practice item is a new case; word count within 25% of the other version; the interpretive and practical lessons differ in hero and practice from the systems lesson. Short excerpts go in the test record, never whole courses.

Disproof: claims that don't match sources; reasons still missing; the same shape on all three subjects; "after" longer without a new-case item; the learner can repeat the example but not the new case. Source accuracy is the spot check; teaching quality is the blind read; immediate performance is the learner's first-try result on the new-case items if he takes one lesson; retention is the 1, 3 and 7 day review, which this test does not claim. Record the result in `docs/plans/reviews/<date>-teaching-depth-test.md`.

Stop conditions: any "after" lesson fails the source spot check, or all three "after" lessons share one shape. Then revisit the wording before release.

### U4. Library page

`scripts/library.py <learn-root>` (stdlib, about 60 lines): scans folders holding both `MISSION.md` and `index.html`, and writes `<learn-root>/index.html` from the starter styles. Per course: title (`h1`), the mission's Why line, lessons with status from the course index's `ol.syllabus` (`li` ready, `li.soon` planned), reference sheets, every carry-over rule linked to its sheet, glossary terms, learning-record titles with dates, and the review state from `quiz.jsonl` (due, and retired after three rights) linking to the course index. Two columns per course: available (lessons, sheets, rules) and shown (learning records, retired questions). `open_course.py` calls it once per open. Browser find on the page is the concept search; a rule row opens its sheet, the sheet's "How it showed up here" names the lesson, the lesson's citation opens the source through that course's server when running, and `lessons/<file>#q-<id>` scrolls to the quiz (`starter/assets/quiz.js` header). No database, server route, conversation mining or sync. Gap: adk has no glossary and codex-harness's is empty, so finding a concept leans on rules and sheet headings until glossaries fill.

Check: one test, `scripts/test_library.py`, on the risky path: a fixture course with a syllabus, a carry-over table and a `quiz.jsonl` renders the expected rows; a folder without MISSION.md is skipped.

### U5. Review and release

One Sol xhigh Codex review of the diff after U3's blind read, with the test record as evidence (`.compound-engineering/config.local.yaml` copied into the worktree). Then 1.4.0: `.claude-plugin/plugin.json`, CHANGELOG entry, `scripts/test_release.py`, commit, push, tag and GitHub release, each with the owner's go.

## Risks

- The thin course's main cause may be source access, not rules; U3 holds sources constant so the wording change is judged on its own.
- "Require a new case" can produce contrived cases on a pure-understanding lesson; the blind read's question 5 catches a forced one.
- Existing courses are not rewritten; their next lesson follows the new rules, and NOTES.md's "analogy" wording stays valid as "comparison in use".
