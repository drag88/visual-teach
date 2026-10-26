---
name: verify-teach-guard
description: Check that a teaching session started from the course page can only edit unprotected files inside the course. Use when a change touches skills/visual-teach/scripts/teach_guard.py, the Teach command in skills/visual-teach/scripts/serve.py (Course.teach_command), the list of protected course files, or adds another engine (such as Codex) that runs Teach.
metadata:
  internal: true
---

# Verify the teaching edit guard

**The promise:** an edit that a Teach session (next lesson, update from my questions, fix the check) is allowed to make never changes a protected course file or any file outside the course.

**The harm if it breaks:** an agent running with edit rights could overwrite `course.json` (whose `refresh` command the server runs in a shell), the shared scripts every served page runs (`assets/*.js`), its own permission settings under `.claude/`, or files outside the course entirely.

Protected: `course.json`, `.serve.json`, `CLAUDE.md`, `AGENTS.md`, everything under `.claude/`, and every file under `assets/` except `assets/course.css`. Names are matched without regard to case.

## Does your change touch it?

Run this check when the diff changes any of:

| Covered code | What it does for the promise |
|---|---|
| `skills/visual-teach/scripts/teach_guard.py`, `main()` | Decides, for one edit request, allow (exit 0) or block (exit 2). The checker runs this function. |
| `skills/visual-teach/scripts/serve.py`, `Course.teach_command` | Wires the guard in: a `PreToolUse` hook on `Edit\|Write\|MultiEdit\|NotebookEdit`, run as `python -I teach_guard.py <course>`, with `onFailure: block`. The checker does not cover this wiring; `test_teach_edits_only_inside_the_course` in `skills/visual-teach/scripts/test_serve.py` does. |
| The protected-file list | Lives in both `teach_guard.py` and the `--disallowedTools` rules in `Course.teach_command`. The checker's `harmed()` in `tests/verify_teach_guard.py` encodes the same list as the oracle; change it there too when the list changes on purpose. |

**Sync commit:** `47804ce` (2026-10-26). At this commit the checker was confirmed to describe the covered code. If `git log 47804ce..HEAD -- skills/visual-teach/scripts/teach_guard.py skills/visual-teach/scripts/serve.py` shows changes to the covered code, run the check and reread the table above before trusting it. Move the sync commit forward only after you have confirmed that the checker still describes the code at the new commit.

## Run it

From the repo root, with Python 3.9 or later and nothing else installed:

```sh
python3 tests/verify_teach_guard.py
```

About 20 to 30 seconds. `--depth 2` runs in about a second for a quick look; use the default depth 3 before you commit.

**Pass:** `OK: 57696 edit requests (depth 3, 24 segments, 4 forms); ... allowed, none touched a protected or outside file.` Exit 0.

**Fail:** exit 1 and a counterexample as three steps: the edit a session asked for, the guard allowing it, and the protected or outside file the write landed on. `<course>` is the course folder and `<parent>` the folder holding it.

## What the check does

It builds a real course folder in a temp directory with every protected file, some ordinary course files, a folder outside the course, and planted links: `link_out` (a folder link leading out of the course), `link_cfg` (a file link onto `course.json`), `link_assets`, `link_dotclaude`, and `lessons/link_up` (a link two levels up). Then it asks the real guard about every path made of up to 3 pieces from 24 tricky pieces (`..`, protected names in two casings, `.claude`, `assets`, the links, ordinary names), in 4 forms: absolute in the course, relative to the course (Claude's working folder), relative to `lessons/`, and absolute from the course's parent folder.

For every edit the guard allows, it does what Claude's Write does (create parent folders, write to the file), then finds where every created or grown file really is on disk, links resolved. It judges by that effect, not by re-deriving the guard's rules, so a rule the guard gets wrong shows up as harm. Each write is undone before the next case. The guard is compiled from source on every run, never imported, because a cached `.pyc` once let a restored file be tested as its broken version.

## Real bug or modeling error?

A counterexample is a real bug when the three steps describe something a Teach session could actually do: ask for that path, in that working folder, with those links present. Reproduce it outside the checker by piping the same event to the guard the way the hook does:

```sh
echo '{"tool_name":"Write","cwd":"<course>","tool_input":{"file_path":"<course>/link_cfg"}}' | python3 -I skills/visual-teach/scripts/teach_guard.py <course>
```

Exit 0 on a harmful path confirms the bug. It is a modeling error when the checker's world is wrong: the fixture links point somewhere a real course could not have (they are relative so a copy links within itself), `harmed()` disagrees with the protected list you meant, or an earlier case's write was not undone. Fix the checker for a modeling error; never weaken `harmed()` or drop segments to make a real counterexample go away.

## When you change the guard on purpose

- Protecting a new file or folder: add it to `teach_guard.py`, to the `--disallowedTools` rules in `Course.teach_command`, to `harmed()`, to `build()` so the fixture holds one, and its name in two casings to `SEGMENTS`.
- Allowing a file that was protected: remove it from the same places, and say why in the commit.
- Adding a Teach engine (for example Codex): the guard only covers edits that go through its hook. An engine that can also write through a shell, or that has no edit hook, needs its own containment, and this check says nothing about it. Add that engine's path into the course to the table above once it is verified.

## What it does not cover

- **Bound:** paths up to 3 pieces from the 24 listed. A longer path built only from these pieces adds nothing new for this guard, but a new kind of trick (a new link shape, an odd character) needs a new piece.
- **Hard links:** a hard link to `course.json` inside the course would get through, because the guard sees a different name. A Teach session on Claude has no shell and cannot make one; a person or another tool could.
- **Timing:** a link swapped between the guard's check and the write is not modeled. Teach sessions have no way to make links.
- **Platform:** run on macOS (case-insensitive disk) and Linux. Windows path forms (`course.json.`, `COURSE~1.JSO`, `::$DATA`) are not in the segments.
- **Wiring:** whether Claude Code actually runs the hook, and the `--disallowedTools` rules, are covered by `test_serve.py`, not here.

## Proving the check can fail

On 2026-10-26 the check caught each of these breaks of the real `teach_guard.py`, then passed again on the restored file: links not followed (paths cleaned up as text only), no link or `..` handling at all, names compared with case, `.claude/` unprotected, all of `assets/` editable, `course.json` unprotected. When you change the checker, break the guard the same way once (on a scratch edit you then undo) and see it fail.
