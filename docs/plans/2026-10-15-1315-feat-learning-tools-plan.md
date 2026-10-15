---
title: Learning tools for any topic - source panel, code actions, answer checks, review, predict
type: feat
date: 2026-10-15
task_folder: none (single-session build)
---

# Learning tools for any topic

**Need.** Learners understand a topic best by going to its real sources, explaining back and being re-tested. Today lessons only quote frozen snippets, recall answers are self-compared, and missed questions never return.

**Smallest thing that meets it.** Seven additions to the existing server, reader and quiz scripts, two teaching rules, no new dependency or asset file. Rough size: about 900 lines across 8 files plus SKILL.md, README and templates.

**Generic by design.** visual-teach is public and teaches any topic. Every feature works for a code repo and for a folder of text (markdown chapters, a legal corpus, notes), and quietly does not appear when a course has no source folder or no server.

A design review on 15 Oct 2026 (`reviews/2026-10-15-design-review.md`) is the basis of the contract below; the code review is `reviews/2026-10-15-code-review.md`.

## Decisions

- Keep the `--code` flag and `course.json` key. Document it as "a folder of source files, code or text". A rename touches every unit for no behaviour.
- `quiz.js` stays server-free. It dispatches a `quiz` DOM event; `ask.js` owns every fetch. This keeps the three build units on separate files.
- Predict is the recall widget with different strings, so it shares one code path and one `check` kind.
- Recall and predict get self-mark buttons ("I got it" / "I missed it") after reveal. That is what feeds spaced review without parsing Claude's verdict, and it works offline.
- Spaced review lives on the server (`quiz.jsonl` in the course), so the teaching session can read misses. No localStorage fallback.
- The "find uses" action is labelled "Where else", which reads right for code and for text.
- Trace lessons and the general-versus-specific split are teaching rules, plus one CSS class (`.yours`).

## Frozen contract

Build against this, not against another unit's code. If it is wrong, stop and report rather than change it.

### Server (`scripts/serve.py`)

`GET /api/source?path=P`. P is relative to the source folder (`--code`), or absolute inside it.
- 200 `{"path": "<relative path>", "text": "<whole file>"}` with `Cache-Control: no-store`.
- 404 for every refusal: no source folder; outside it after `resolve()` (covers `..` and symlinks); any path part starting with `.`; git-ignored; not a regular file. If `<folder>/.git` exists, `git -C <folder> check-ignore -q -- <rel>` exit 0 means refuse; if `.git` exists but `git` is not on PATH, refuse everything.
- 413 above 512,000 bytes. 415 if not strict UTF-8 or it contains a NUL byte.
- Gated by `allowed()` like every GET.

`POST /api/quiz`, body `{"lesson", "quiz", "type", "q", "right"}` (`right` is true, false or null). Appends `{"t", "lesson", "quiz", "type", "q", "right"}` to `<course>/quiz.jsonl`. 200 `{"ok": true}`. Same Origin and JSON checks as `/api/ask`. Rejects a missing `lesson` or `quiz` with 400.

`GET /api/review`. Folds `quiz.jsonl` per (lesson, quiz), in file order, ignoring `right: null`:
- `streak` = rights since the last wrong.
- In review when a wrong has ever been recorded and `streak < 3`.
- Due at the last record's `t` plus 1 day (streak 0), 3 days (streak 1) or 7 days (streak 2).
- Response `{"due": [{"lesson", "quiz", "q", "href": "<lesson>#<quiz>", "streak"}], "waiting": n}`. `due` holds items due now, soonest first; `waiting` counts items in review but not yet due.

New `KIND_TASK` kinds:
- `walk`: "Walk through the highlighted lines in order, one step per line or statement, saying what each does in plain words. At most eight steps."
- `uses`: "Search the source folder for where the highlighted name or phrase is defined and where else it is used or mentioned. List up to eight places as path:line, most important first, a few plain words each."
- `check`: "The learner answered from memory. Mark it against the right answer and the lesson: start with Right, Nearly or Not yet, then say what they got right, what they missed, and if wrong where their thinking went off. Under 120 words."

None of these is in `ALWAYS_QUICK`; they follow the learner's Quick or Deep choice. The tools list stays exactly Read, Grep, Glob (plus WebFetch for Deep, as today).

`/api/ask` request fields. Every kind keeps today's fields.
- `walk`, `uses`, `explain`, `simpler`, `more`, `ask` may add `source: {"path", "start", "end"}` (a selection in the source panel, or in a lesson `<pre>` whose next sibling is a `.src` citation). The prompt then says `Highlighted lines {start}-{end} of {path}: "<selection>"` instead of the paragraph line.
- `check` carries `quiz` (quiz id), `question` (the quiz prompt), `answer` (what the learner wrote), `model` (the right answer), `para` (the quiz block's anchor) and `lesson_text`. The prompt gets lines `Question:`, `Learner's answer:` and `Right answer:`.

`questions.jsonl`: the user record gains `source` (or null) and, for `check`, `quiz`. Its `text` is `q.get("answer") or q.get("question") or KIND_TASK[kind]`. Still exactly one user and one assistant record per exchange. Quiz results never go into `questions.jsonl`.

### Lesson markup

- **Citation:** any element with class `src` whose trimmed text matches `^(\S+?):(\d+)(?:-(\d+))?$`. Block form `<p class="src">path:12-20</p>` under a `<pre>` (already used), inline form `<code class="src">path:12</code>`. Never an `href` (the link checker would flag it). Without a server or source folder it stays plain text.
- **Quiz id:** `id="q-<slug>"` on every `.quiz`. When missing, quiz.js uses `"k-"` plus the first six words of `.q`, slugged. Either way it sets `data-quiz`, and on load it scrolls to and flashes the quiz named by `location.hash`.
- **Predict:** `<div class="quiz predict" id="q-x"><p class="q">What will this print?</p><pre><code>...</code></pre><div class="model">The real outcome</div></div>`.
- **Specific to the learner:** `<div class="yours"><b>In your case</b>...</div>`. Everything outside it is portable.

### DOM event (quiz.js to ask.js)

`quiz.dispatchEvent(new CustomEvent("quiz", {bubbles: true, detail}))` with detail `{quiz, type, event, right, q, answer, model}`:
- `event: "answered"` on the first check of mcq, order, match and spot (right true or false), and on a recall or predict self-mark.
- `event: "revealed"` on a recall or predict reveal, with `answer` (the learner's text) and `model` (the right answer's text), `right: null`.

### Answer links

In `ask.js` `inline()`, after URLs are held: `path:line[-line]` becomes `<a class="ask-pchip ask-src" href="#" data-path data-start data-end>`, only when ping reports a source folder. Built through `hold()` with escaped attributes; the server refuses anything outside the folder.

### localStorage

Nothing new. `vt-mode`, `vt-answers` and `vt-theme` stay as they are.

## Units

### U1. Server

Owns `scripts/serve.py` and `scripts/test_serve.py`. Everything in the server contract.

Tests: `test_source_is_confined` (inside gives 200; `../x`, a symlink out, `.env`, a git-ignored file in a `git init` temp folder, and no folder all give 404; binary 415; over the cap 413); `test_check_and_walk_prompts` (stdin carries the learner's answer and the right answer; the record has `kind: check`, `quiz`, and text equal to the answer; a walk with `source` names the path and lines); `test_quiz_and_review` (POST results, fold, due order, retirement after three rights, `waiting`, 400 on a missing id).

### U2. Reader

Owns `starter/assets/ask.js`, `starter/assets/ask.css` and `scripts/test_reader.py`.

- `start(info)` keeps ping's `code`.
- Clicking a `.src` citation or an `.ask-src` answer link opens the source panel: a non-modal `<dialog>`, right half of the screen on wide screens, bottom sheet at 720px and below, close button and Escape. Lines are numbered; cited lines tinted with the existing highlight token; the first cited line scrolled into view. A refused or missing file shows one plain line, never content.
- The selection bar works inside the panel and inside lesson `<pre>` blocks, and sets `pending.source`. "Walk through" shows for any selection in code or the panel; "Where else" shows only when there is a source folder.
- A card from the panel attaches to the lesson block that opened it (reuse `place`).
- Listens for the `quiz` event: posts every `answered` to `/api/quiz`; on `revealed`, adds a "Check my answer" button that sends a `check` ask and shows the card under the quiz block.
- On the course index, fetches `/api/review` and, when anything is due, inserts a short "Review" list after `ol.syllabus` linking to each due question.
- `restore` shows the learner's text for `check` threads, as it does for `ask`.

Tests in `test_reader.py`, with a temp source folder: citation opens the panel with the cited lines tinted; panel selection offers Walk through and Where else; a walk card attaches to the right block and the fake Claude's stdin names the path; an answer citation opens the panel; recall reveal then Check my answer creates a card with the answer and right answer posted; a seeded `quiz.jsonl` puts one review link on the index; a `.env:1` citation shows the refusal line and no content; works at 390px and desktop.

### U3. Quizzes

Owns `starter/assets/quiz.js`, `starter/assets/style.css`, `scripts/check_lessons.py` and a new `scripts/test_quiz.py`.

- Predict variant of recall; self-mark buttons after reveal for recall and predict; quiz ids and `data-quiz`; hash scroll and flash; the `quiz` event.
- `.yours` CSS: mirrors `.win`, no box.
- Panel-agnostic: no fetches.
- `check_lessons.py`: `answer_quizzes` handles predict; the graded count excludes recall and predict; self-marks do not change the score line.

Tests in `test_quiz.py` (Playwright on `file://`, no server): predict reveals; self-mark fires `answered` with `right`; mcq fires `answered`; a quiz without an id gets a `data-quiz` key and `#k-...` scrolls to it; the score line is unchanged by self-marks.

### U4. Integration (after U1 to U3)

- SKILL.md: the source folder in plain terms; citations; trace lessons; the general-versus-specific rule and `reference/carry-over.html`, and reading other courses' carry-over sheets when a course starts; predict; Check my answer; review; using `quiz.jsonl` at session start.
- README, `starter/lesson.html` (ids, one predict, one `.yours`), `starter/reference.html` note.
- Sync every course, add quiz ids to existing lessons, run all four test files and the course check, look at the screens light and dark, phone and desktop.

Ordering: U1 and U3 run in parallel. U2 codes against the contract in parallel; its browser test needs U1's endpoints.

## Risks

- **Serving files.** Traversal and symlinks: resolve, then check the parent, as `send_head` already does. Secrets: dotfile rule, git-ignore rule, `--` before the path, `no-store`. Claude's Read can already see the source folder, so the panel adds no new reach.
- **Model-written citations** are untrusted text: built through `hold()`, escaped, and refused by the server when outside the folder.
- **Existing tests:** tools list, two records per exchange, inert answer links and the graded-score arithmetic must all stay true.
- **Existing courses:** `.src` stays plain without the server; missing quiz ids fall back to keys; rewording a question resets its review history (accepted).
- **Phone:** the bottom-sheet panel and the docked selection bar must not cover each other; tested at 390px.
