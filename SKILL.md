---
name: visual-teach
description: Teach any topic over several sessions as a local course of short, visual, plain-English lessons that the learner reads in the browser, with live Claude answers on any passage they highlight. Self-contained - it bundles the teach method and diagram-design, its own clean minimal styles, quiz widgets, reading server and checks. Run /visual-teach <topic> to start a course, /visual-teach continue <course folder> to carry on, or /visual-teach open <course folder> just to read (in Codex, $visual-teach).
disable-model-invocation: true
argument-hint: "A topic to learn, or: continue <course folder>, or: open <course folder>"
---

# Visual teach

Teach a topic as a course of short, visual lessons the learner reads in the browser, highlights and questions live. Everything it needs is in this folder. Nothing else has to be installed except Python 3, and the `claude` command line for live answers. Playwright is needed only for the checks.

| In this folder | What it is |
|---|---|
| `vendor/teach/METHOD.md` and its `*-FORMAT.md` files | The teaching method (Matt Pocock's `teach`, bundled). It holds unless this file says otherwise. |
| `vendor/diagram-design/GUIDE.md` with its `references/`, `assets/`, `scripts/` | How to choose and draw every diagram (diagram-design, bundled). |
| `starter/` | The shared look: `assets/` (style.css, theme.js, quiz.js, ask.css, ask.js), the `index.html`, `lesson.html` and `reference.html` templates, `ask-prompt.md`, and `diagram-profile-learn.md`. |
| `scripts/` | `sync_course.py`, `open_course.py`, `serve.py`, `check_lessons.py`, and their tests. |

## How the learner starts it

- Claude Code: `/visual-teach <topic>` starts a course. `/visual-teach continue ~/learn/<course>` carries one on. It works from any folder.
- Codex: `$visual-teach <topic>`, or pick it from `/skills`.
- Just to read and ask, with no new lesson: `/visual-teach open ~/learn/<course>`. Run `python3 <this skill>/scripts/open_course.py <course>` with any page or flags the learner gave (on Windows, `python` or `py` in place of `python3`), pass on the link it prints, and stop: no teaching session. `--stop` stops the reading server. Point learners to this command rather than a script path: a plugin install moves the skill to a new folder with each update.
- From the course page itself: the course home page has a Teaching section, shown only on the computer running the server (section 8).

## Every session

1. **Find the course.** A topic starts a new course in `~/learn/<topic-slug>`, or in the current folder when it is empty or already a course. Never put a course in a code repository; lesson files must not land in a pull request. `continue <folder>` uses that course. If it is unclear, list `~/learn/*` and ask.
2. **Sync the look:** `python3 <this skill>/scripts/sync_course.py <course>`. It gives the course this skill's current shared files, makes every page load them, and installs the diagram profile. Every course then looks and works the same.
3. **Catch up.** Read `vendor/teach/METHOD.md` and its format files. Then read the course's `MISSION.md`, `NOTES.md`, `RESOURCES.md`, `learning-records/`, the questions asked while reading, and the quiz results in `quiz.jsonl` (section 6). For a new course, also read the carry-over sheets of other courses (`~/learn/*/reference/carry-over.html`) and build on any overlap (section 4).
4. **Teach.** Write or revise the next lesson, following sections 1 to 5, and update `index.html` and the reference sheets.
5. **Check:** section 7.
6. **Open it:** `python3 <this skill>/scripts/open_course.py <course> <lesson path>`. It brings the course's shared files up to date, starts the course's reading server or reuses it if already running, and opens the lesson. A server running older code or another copy of the skill is restarted, unless it is in the middle of a teaching job. The server runs on its own, so it keeps going after this session ends. The first time, pass `--code <folder>` when the course has a folder of source files to learn from (a codebase, or text such as markdown chapters, papers or notes), and `--web <domain>` for documentation sites Deep answers may fetch; these are saved in `course.json`. `--lan` adds a link for a phone on the same Wi-Fi, and `--no-lan` removes it. Tell the learner the link and how to stop it.

## 1. Course shape

- The course folder holds `index.html`, `lessons/`, `reference/`, `assets/`, and the method's files: `MISSION.md`, `RESOURCES.md`, `NOTES.md`, `learning-records/`.
- Write `index.html` from `starter/index.html` as soon as the mission and first resources exist. It lists the whole syllabus up front, with each lesson's status. Learners want the map before the close-ups.
- Lesson 1 is always the map: every core part of the topic in one diagram, each with a one-line definition and, when the learner has a real system, where it lives in that system. Close-ups come after.
- Lessons start from `starter/lesson.html`; reference sheets from `starter/reference.html`.
- When the course has a source folder, teach with it as the worked example. Cite it as `<p class="src">path:12-20</p>` under a quoted block, or inline as `<code class="src">path:12</code>`, with the path relative to the folder. With the server running, a citation opens the real file beside the lesson, scrolled to those lines. Check each line against the file before using it. Quote code, never data: no credentials, records, query results, logs or details about real people or customers in a lesson or a quiz; use a small made-up example instead. A course folder sits outside the learner's project and its rules, so nothing private may land there.
- `reference/carry-over.html` (from `starter/reference.html`) collects the course's portable rules (section 4, item 8).
- `NOTES.md` records that the course uses visual-teach, the analogy mapping (section 2), and how to open it again (`/visual-teach open <course>`).

## 2. Explain it like the learner is five

Every lesson, caption, quiz question and quiz answer is written in plain, simple English, the way you would explain it to a bright child. Simplify the words, never the facts.

- **Picture before term.** Introduce each idea with an everyday comparison the learner can picture, then give its real name, then where it lives in their system. "A function is like a recipe card: it lists what to bring and the steps to follow. Python writes one with `def`."
- **One analogy family per course.** Pick one world (an office, a kitchen, a post office) in lesson 1, write its mapping in `NOTES.md`, and reuse it in every lesson. Say plainly where the comparison stops being true.
- **Short and concrete.** Short sentences, one idea each, everyday words. A real example beats a definition.
- **Every technical word earns its place.** Define it in the same sentence the first time it appears. Code and file names come last, after the plain explanation.
- **No labels saying it's simple.** No "In plain English" boxes or "ELI5" headings; the whole page is plain.
- Quiz feedback explains why in one or two plain sentences.

## 3. Clean and minimal

- One column of text, generous white space, nothing competing with the words.
- One accent colour, used only for the thing being taught and for the learner's own marks (highlights, asked paragraphs).
- No decoration: no shadows, gradients, dot grids, background textures, icons, emoji, or boxes around boxes. Separate things with white space or a single thin rule.
- Every element earns its place. If removing a line, label, colour or box loses nothing, remove it. Diagrams follow the same rule (GUIDE.md: "the highest-quality move is usually deletion").
- Light and dark: every page has a switch at the top right (`theme.js`). It follows the system until the learner clicks it, then remembers the choice in that browser, which matters in built-in browsers that always report light. Colours live only in `style.css`'s `light-dark()` tokens.
- The same parts look the same in every course. Use the starter templates and the shared classes. The five shared files belong to the skill and `sync_course.py` replaces them; put anything course-specific in `assets/course.css`, which sync links when it exists.

## 4. What makes a lesson visual

1. **Picture first.** One hero diagram carries the lesson's core mechanism and sits before the prose, which then walks the diagram part by part. If the idea has no mechanism (a list, a definition, two options side by side), use a table instead.
2. **Pick the type from the content**, then follow `vendor/diagram-design/GUIDE.md` and its reference for that type:

   | The idea is | Diagram type |
   |---|---|
   | Parts of a system and how they connect | architecture, or nested for containment |
   | Steps over time between actors | sequence |
   | A decision with branches | flowchart |
   | One thing moving through states | state machine |
   | Layers that wrap each other | layer stack |
   | A hierarchy | tree |
   | A cycle that feeds itself | loop |

3. **One focal element:** the accent colour goes on the one thing this lesson teaches, two at most.
4. **Quiz on the picture.** At least one practice item per lesson uses the hero diagram: a `spot` question ("tap where X happens") or an `order` question built from its steps.
5. **Code with highlights.** When a lesson shows real code, highlight the lines that matter with `<span class="hl">` and name them in the diagram's words.
6. **Reference sheets** compress lessons into one printable page: short tables and numbered steps, no long prose. Keep a map of the learner's real system as a reference sheet when there is one.
7. **Trace one case end to end.** When the topic has a flow, give it at least one trace lesson: follow a single concrete case from start to finish (one request through a system, one bill through parliament, one molecule through a pathway). The hero is a sequence diagram or flowchart, and the prose is an `ol.turn` list with one step per stop, each citing its source.
8. **Portable, then yours.** Most of a lesson should be true of any similar system. When the learner has their own case (their codebase, company or project), put what is specific to it in `<div class="yours"><b>In your case</b>...</div>`. Each lesson adds its portable rules to `reference/carry-over.html`: one table, "Portable rule" and "How it showed up here". That sheet is what the learner carries to the next course on a similar topic.

## 5. Lesson diagrams: size and skin

Lessons are read on phones, and diagram-design's default canvas and type are too small there.

- The style guide is `starter/diagram-profile-learn.md` (sync installs it as diagram-design's `learn` profile and marks the course with it), so skip GUIDE.md's first-time style question.
- Canvas: GUIDE.md's `fit` canvas, at most 720 wide, with its `presentation` type ramp (node names 16, sublabels and arrow labels 12). At most 5 actors or 7 nodes; split into two diagrams beyond that. No dot grid or background pattern.
- Inline the `<svg class="dg">` in the lesson inside `<figure class="diagram" id="...">` with a `.scroll` wrapper and a `<figcaption>` that states the claim. On a phone the figure scrolls sideways instead of shrinking its labels.
- Colour with the stylesheet's classes, never hex, so light and dark both work: `box`, `box ext`, `box focal` for nodes; `t-ink`, `t-muted`, `t-acc` for text; `s-muted`, `s-acc`, `s-ink` for lines; `f-paper`, `f-soft`, `f-muted`, `f-acc` for fills; `mono` for technical labels.
- Keep GUIDE.md's accessible-SVG contract: `role="img"`, `<title>` first, a one-sentence `<desc>`, ids prefixed with the diagram's slug.
- Make parts tappable for spot quizzes: wrap each node in `<g data-spot="id">` around its `rect.box`, and each message or edge in `<g data-spot="id">` with a transparent `rect.hit` behind it. In a sequence diagram, put each actor's lifeline and activation bars inside that actor's group too, so a tap on its line counts as the actor.
- Word a spot question so exactly one part fits, then read every label as the learner would: an arrow from a tool labelled "add to history" makes the tool look like the part that writes the history, so a question about who writes it becomes a trap.

## 6. Quizzes, and asking while reading

**Quizzes.** `assets/quiz.js` holds every widget, and its header shows the markup: `mcq`, `recall` (write first, then compare), `predict` (guess first, then see the real outcome), `order`, `match`, and `spot` (clones the hero diagram and asks the learner to tap a part). Every answer option has the same number of words. A new widget goes into the starter assets, never inline in one lesson.
- Give every quiz a stable `id="q-<slug>"`; review links and results use it.
- Use `predict` before showing a real outcome: what the code prints, what the data shows, what happened next. Use the real thing as the outcome (run the code, quote the source), never an invented one.
- After a recall or predict reveal the learner marks themselves ("I got it" or "I missed it"), and with the server running can press "Check my answer" for Claude to mark what they wrote against the lesson.
- With the server running, every answer is saved to `quiz.jsonl`. A question answered wrong comes back in a Review list on the course index after 1, 3 and 7 days, until it is right three times in a row.

**Asking while reading.** With the course opened through `open_course.py`, the learner can highlight any passage and choose Explain, Simpler, More, Connect or Ask. In a code block or the source panel there are two more: Walk through (step by step) and, when the course has a source folder, Where else (where it is defined, used or mentioned in the folder). The answer streams into a card beside the paragraph (under it on a phone), with follow-ups in the same card. The bar at the bottom asks about the whole page; its answer lands beside the paragraph being read, so the learner keeps their place. Question boxes grow with the question; Enter sends and Shift+Enter starts a new line. "Hide answers" in the bar hides every card and mark for plain reading, and is remembered; asking anything shows them again. Quick answers use Sonnet and start in about 5 seconds; Deep answers use Opus, can read the course's `--code` folder, and take about 25.
- Claude runs read-only: it can read, search, and fetch the course's `--web` domains, nothing else. Answers follow `starter/ask-prompt.md` plus the course's `MISSION.md`, `NOTES.md` and `GLOSSARY.md`, so keep the analogy mapping in `NOTES.md` current. A course's own `ask-prompt.md` overrides the skill's.
- Citations (`.src`) and `path:line` references in answers open the source panel: the real file, read-only, with the cited lines tinted. The server only serves files inside the course's `--code` folder, never hidden files or files git ignores.
- A lesson opened as a plain file works as before and shows a one-line hint about the server.
- Every question and answer is appended to the course's `questions.jsonl`: one `user` and one `assistant` line per exchange, grouped by `thread`, with the passage's `anchor`. `meta` lines mark a thread `deleted` or `handled`. Never edit earlier lines.

**Use the questions.** At the start of every session, read the threads with no `handled` line. They are the best evidence of what the learner understands:
- Understanding shown, or a misconception corrected: write a learning record.
- A term asked about twice: a glossary candidate.
- Simpler asked on a passage: rewrite that passage, and note it in `NOTES.md`.
- A long Deep thread: a deep-dive lesson or a reference sheet, linked from the passage.
- Connect: see-also links in both lessons, or a syllabus item when the target has no lesson yet.
- Check my answer (kind `check`): the learner's own words against the right answer; write a learning record either way.
- `quiz.jsonl`: questions missed, and missed again, show what has not landed; reteach them before moving on.
- Weigh open threads when choosing the next lesson.
Then append `{"role":"meta","event":"handled","thread":"...","ref":"<what you made>"}` for each.

## 7. Check before handing over

1. Run `python3 <this skill>/scripts/check_lessons.py <course> <screenshot-dir>` with a Python that has Playwright. It checks every link; that no page scrolls sideways on a phone or desktop, and no code block hides long lines; that answering every quiz correctly scores full marks; that diagram labels render at 9.5px or more on a phone; that every page loads the reader and the course's shared files match the skill's; that no lesson sentence runs past 25 words; and that no script errors. It saves phone screenshots in light and dark.
2. Look at the screenshots yourself, light and dark: no label crossing a line, nothing clipped, nothing decorative, the accent only on the focal element.
3. Read each lesson as the learner would: would a bright ten-year-old follow every paragraph? Rewrite any that need a second read.
4. Check every claim has a citation, and every fact about the learner's own system against its source.

## 8. Teaching from the course page

The course home page has three buttons, so a learner rarely needs the terminal once the server is running:
- **Teach the next lesson** and **Update lessons from my questions** run one teaching session in the background, guided by this file. It can read the skill, the course and its source folder. It can edit only inside the course folder. It cannot edit `course.json`, `.serve.json`, `.claude/`, `CLAUDE.md`, `AGENTS.md` or the shared asset files. It can edit `assets/course.css`. It has no shell. The server syncs the shared files first and runs the course check afterwards. The page shows the latest steps, a Stop button, a closing summary and the check result. When the check fails, the fix button runs one more session with the problems.
- **Refresh the source copy** appears when `course.json` has a `refresh` key. This shell command brings a copied source folder up to date. Only a person writes it. It runs from the home folder. It must not run anything inside the course folder, which teaching sessions can edit. It should finish its work before it exits: on Windows, a background process it leaves running is not stopped with the job.
- One job runs at a time. The buttons only appear, and the server only accepts them, on the computer running the server, never through the phone link. Each teaching session takes about 5 to 15 minutes.

A session started this way follows sections 1 to 7 as usual, except that it runs no scripts and takes no screenshots.
Served course pages run only the skill's three shared scripts: `theme.js`, `quiz.js` and `ask.js`. A script written into a lesson never runs.

## Changing this skill

After changing `serve.py`, `open_course.py`, `ask.js`, `ask.css`, `quiz.js`, `theme.js` or `style.css`, run `scripts/test_serve.py`, `scripts/test_open_course.py`, `scripts/test_reader.py` and `scripts/test_quiz.py`; they use a fake Claude, so they cost nothing. Opening a course brings it up to date; `sync_course.py` does the same without opening it.

To release: raise the version in `.claude-plugin/plugin.json` (new features raise the middle number, fixes the last), add a matching `CHANGELOG.md` entry and link, run `scripts/test_release.py`, commit, push the commit to `main` (the plugin marketplace reads `main`), tag `v<version>`, push the tag, and publish a GitHub release with the entry as its notes. Plugin installs update only when the version changes.
