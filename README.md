# visual-teach

Teach any topic as a course of short, visual, plain-English lessons you read in the browser, with live Claude answers on any passage you highlight. It starts life as an agent skill for Claude Code and Codex and is meant to grow into a full application.

## What it does

- Builds a course in its own folder (`~/learn/<topic>`): a syllabus, lessons, reference sheets, quizzes and diagrams, all in one clean, minimal look.
- Opens the course through a local reading server. Highlight any passage and pick Explain, Simpler, More, Connect or Ask; Claude streams an answer into a card beside it, read-only, with follow-ups. Highlighted code also gets Walk through and Where else.
- Learns from your own sources: give a course a folder (a codebase, or markdown chapters, papers, notes) and every citation opens the real file beside the lesson, scrolled to the cited lines.
- Tests you properly: predict-then-reveal questions, "Check my answer" on anything you write from memory, and missed questions that come back for review on later days.
- Saves every question and quiz result, so the next teaching session can rewrite what confused you and choose the next lesson.
- Light and dark, on any screen from a phone to a wide monitor.

## Use it

- Claude Code: `/visual-teach <topic>` starts a course; `/visual-teach continue ~/learn/<course>` carries one on.
- Codex: `$visual-teach <topic>`.
- Just reading: `python3 ~/code/visual-teach/scripts/open_course.py ~/learn/<course>` (add `--stop` to stop the server).

## Install on a Mac

```zsh
git clone https://github.com/drag88/visual-teach.git ~/code/visual-teach
ln -sfn ~/code/visual-teach ~/.claude/skills/visual-teach   # Claude Code
ln -sfn ~/code/visual-teach ~/.agents/skills/visual-teach   # Codex
```

Needs Python 3, and the `claude` command line for live answers. Python Playwright is needed only for the checks and the browser test. Run the server from your normal shell so Claude uses your login and network settings.

## Layout

| Path | What it is |
|---|---|
| `SKILL.md` | The instructions Claude Code and Codex follow. |
| `agents/openai.yaml` | Codex settings: called by name only. |
| `starter/` | The shared look: `assets/` (style.css, theme.js, quiz.js, ask.css, ask.js), the index, lesson and reference templates, the answer prompt, and the diagram profile. |
| `scripts/` | `serve.py` (reading server), `open_course.py` (start, reuse, stop), `sync_course.py` (keep a course on the shared look), `check_lessons.py` (course checks), and the tests. |
| `vendor/` | The bundled teach method (MIT, Matt Pocock) and diagram-design (MIT, Cathryn Lavery), each with an `UPSTREAM.md`. |

Courses are not part of this repo. They live in `~/learn/` and hold personal notes and questions.

## Develop

Because the folder is linked into both agents, an edit here is live in the next agent session.

The tests use a fake Claude, so they cost nothing:

```zsh
python3 scripts/test_serve.py
python3 scripts/test_open_course.py
python3 scripts/test_reader.py   # needs Playwright
python3 scripts/test_quiz.py     # needs Playwright
```

After changing anything in `starter/`, run `python3 scripts/sync_course.py ~/learn/<course>` for each course.
