---
name: visual-teach
description: Teach any topic over several sessions as a local course of short, visual, plain-English lessons that the learner reads in the browser, with live Claude answers on any passage they highlight. Self-contained - it bundles the teach method and diagram-design, its own clean minimal styles, quiz widgets, reading server and checks. Run /visual-teach <topic> to start a course or /visual-teach continue <course folder> to carry on (in Codex, $visual-teach).
disable-model-invocation: true
argument-hint: "A topic to learn, or: continue <course folder>"
---

# Visual teach

Teach a topic as a course of short, visual lessons the learner reads in the browser, highlights and questions live. Everything it needs is in this folder. Nothing else has to be installed except Python 3, and the `claude` command line for live answers. Playwright is needed only for the checks.

| In this folder | What it is |
|---|---|
| `vendor/teach/METHOD.md` and its `*-FORMAT.md` files | The teaching method (Matt Pocock's `teach`, bundled). It holds unless this file says otherwise. |
| `vendor/diagram-design/GUIDE.md` with its `references/`, `assets/`, `scripts/` | How to choose and draw every diagram (diagram-design, bundled). |
| `starter/` | The shared look: `assets/` (style.css, quiz.js, ask.css, ask.js), the `index.html`, `lesson.html` and `reference.html` templates, `ask-prompt.md`, and `diagram-profile-learn.md`. |
| `scripts/` | `sync_course.py`, `open_course.py`, `serve.py`, `check_lessons.py`, and their tests. |

## How the learner starts it

- Claude Code: `/visual-teach <topic>` starts a course. `/visual-teach continue ~/learn/<course>` carries one on. It works from any folder.
- Codex: `$visual-teach <topic>`, or pick it from `/skills`.
- Just to read and ask, with no new lesson: `python3 <this skill>/scripts/open_course.py ~/learn/<course>`. Add `--stop` to stop the reading server.

## Every session

1. **Find the course.** A topic starts a new course in `~/learn/<topic-slug>`, or in the current folder when it is empty or already a course. Never put a course in a code repository; lesson files must not land in a pull request. `continue <folder>` uses that course. If it is unclear, list `~/learn/*` and ask.
2. **Sync the look:** `python3 <this skill>/scripts/sync_course.py <course>`. It gives the course this skill's current shared files, makes every page load them, and installs the diagram profile. Every course then looks and works the same.
3. **Catch up.** Read `vendor/teach/METHOD.md` and its format files. Then read the course's `MISSION.md`, `NOTES.md`, `RESOURCES.md`, `learning-records/`, and the questions asked while reading (section 6).
4. **Teach.** Write or revise the next lesson, following sections 1 to 5, and update `index.html` and the reference sheets.
5. **Check:** section 7.
6. **Open it:** `python3 <this skill>/scripts/open_course.py <course> <lesson path>`. It starts the course's reading server, or reuses it if already running, and opens the lesson. The server runs on its own, so it keeps going after this session ends. The first time, pass `--code <repo>` when the course teaches a real codebase, and `--web <domain>` for documentation sites Deep answers may fetch; these are saved in `course.json`. `--lan` adds a link for a phone on the same Wi-Fi. Tell the learner the link and how to stop it.

## 1. Course shape

- The course folder holds `index.html`, `lessons/`, `reference/`, `assets/`, and the method's files: `MISSION.md`, `RESOURCES.md`, `NOTES.md`, `learning-records/`.
- Write `index.html` from `starter/index.html` as soon as the mission and first resources exist. It lists the whole syllabus up front, with each lesson's status. Learners want the map before the close-ups.
- Lesson 1 is always the map: every core part of the topic in one diagram, each with a one-line definition and, when the learner has a real system, where it lives in that system. Close-ups come after.
- Lessons start from `starter/lesson.html`; reference sheets from `starter/reference.html`.
- When the learner works on a real codebase, teach with its code as the worked example. Quote it by `path:line`, check each line against the file before using it, and never put credentials or private data in a lesson.
- `NOTES.md` records that the course uses visual-teach, the analogy mapping (section 2), and the course's `open_course.py` command.

## 2. Explain it like the learner is five

Every lesson, caption, quiz question and quiz answer is written in plain, simple English, the way you would explain it to a bright child. Simplify the words, never the facts.

- **Picture before term.** Introduce each idea with an everyday comparison the learner can picture, then give its real name, then where it lives in their system. "The runner is like an office manager who hands out each job and writes every step in a logbook. ADK calls it the Runner."
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
- The same parts look the same in every course. Use the starter templates and the shared classes. The four shared files belong to the skill and `sync_course.py` replaces them; put anything course-specific in `assets/course.css`, which sync links when it exists.

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

## 5. Lesson diagrams: size and skin

Lessons are read on phones, and diagram-design's default canvas and type are too small there.

- The style guide is `starter/diagram-profile-learn.md` (sync installs it as diagram-design's `learn` profile and marks the course with it), so skip GUIDE.md's first-time style question.
- Canvas: GUIDE.md's `fit` canvas, at most 720 wide, with its `presentation` type ramp (node names 16, sublabels and arrow labels 12). At most 5 actors or 7 nodes; split into two diagrams beyond that. No dot grid or background pattern.
- Inline the `<svg class="dg">` in the lesson inside `<figure class="diagram" id="...">` with a `.scroll` wrapper and a `<figcaption>` that states the claim. On a phone the figure scrolls sideways instead of shrinking its labels.
- Colour with the stylesheet's classes, never hex, so light and dark both work: `box`, `box ext`, `box focal` for nodes; `t-ink`, `t-muted`, `t-acc` for text; `s-muted`, `s-acc`, `s-ink` for lines; `f-paper`, `f-soft`, `f-muted`, `f-acc` for fills; `mono` for technical labels.
- Keep GUIDE.md's accessible-SVG contract: `role="img"`, `<title>` first, a one-sentence `<desc>`, ids prefixed with the diagram's slug.
- Make parts tappable for spot quizzes: wrap each node in `<g data-spot="id">` around its `rect.box`, and each message or edge in `<g data-spot="id">` with a transparent `rect.hit` behind it.

## 6. Quizzes, and asking while reading

**Quizzes.** `assets/quiz.js` holds every widget, and its header shows the markup: `mcq`, `recall` (write first, then compare), `order`, `match`, and `spot` (clones the hero diagram and asks the learner to tap a part). Every answer option has the same number of words. A new widget goes into the starter assets, never inline in one lesson.

**Asking while reading.** With the course opened through `open_course.py`, the learner can highlight any passage and choose Explain, Simpler, More, Connect or Ask. The answer streams into a card beside the paragraph (under it on a phone), with follow-ups in the same card. The bar at the bottom asks about the whole page. Quick answers use Sonnet and start in about 5 seconds; Deep answers use Opus, can read the course's `--code` folder, and take about 25.
- Claude runs read-only: it can read, search, and fetch the course's `--web` domains, nothing else. Answers follow `starter/ask-prompt.md` plus the course's `MISSION.md`, `NOTES.md` and `GLOSSARY.md`, so keep the analogy mapping in `NOTES.md` current. A course's own `ask-prompt.md` overrides the skill's.
- A lesson opened as a plain file works as before and shows a one-line hint about the server.
- Every question and answer is appended to the course's `questions.jsonl`: one `user` and one `assistant` line per exchange, grouped by `thread`, with the passage's `anchor`. `meta` lines mark a thread `deleted` or `handled`. Never edit earlier lines.

**Use the questions.** At the start of every session, read the threads with no `handled` line. They are the best evidence of what the learner understands:
- Understanding shown, or a misconception corrected: write a learning record.
- A term asked about twice: a glossary candidate.
- Simpler asked on a passage: rewrite that passage, and note it in `NOTES.md`.
- A long Deep thread: a deep-dive lesson or a reference sheet, linked from the passage.
- Connect: see-also links in both lessons, or a syllabus item when the target has no lesson yet.
- Weigh open threads when choosing the next lesson.
Then append `{"role":"meta","event":"handled","thread":"...","ref":"<what you made>"}` for each.

## 7. Check before handing over

1. Run `python3 <this skill>/scripts/check_lessons.py <course> <screenshot-dir>` with a Python that has Playwright. It checks every link; that no page scrolls sideways on a phone or desktop; that answering every quiz correctly scores full marks; that diagram labels render at 9.5px or more on a phone; that every page loads the reader and the course's shared files match the skill's; that no lesson sentence runs past 25 words; and that no script errors. It saves phone screenshots in light and dark.
2. Look at the screenshots yourself, light and dark: no label crossing a line, nothing clipped, nothing decorative, the accent only on the focal element.
3. Read each lesson as the learner would: would a bright ten-year-old follow every paragraph? Rewrite any that need a second read.
4. Check every claim has a citation, and every fact about the learner's own system against its source.

## Changing this skill

After changing `serve.py`, `open_course.py`, `ask.js` or `ask.css`, run `scripts/test_serve.py`, `scripts/test_open_course.py` and `scripts/test_reader.py`; they use a fake Claude, so they cost nothing. Then run `sync_course.py` on each course in `~/learn/`.
