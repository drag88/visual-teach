---
reviewer: codex exec, independent review of the uncommitted diff
model: gpt-6.1-sol, model_reasoning_effort xhigh
date: 2026-10-22
reviewed: worktree feat/teaching-depth before commit, against docs/plans/2026-10-22-2056-feat-teaching-depth-plan.md
---

# Codex review of the teaching-depth change

Findings as reported, with what was done about each.

1. **High, scripts/library.py, assets.** The first library build replaced `~/learn/assets/style.css` and `theme.js` without checking whose they were. **Fixed:** the library keeps its two files in `~/learn/library-assets/` instead, a folder nothing else uses; the symlink refusal stays.
2. **Medium, scripts/library.py, links.** Links opened the course as a plain file, where the reader script exits, so the review list, citations and questions do not work. **Fixed:** when a course's server is running (`.serve.json` answers `/api/ping` as that course), its links go through the server, with the phone token before any fragment; otherwise they stay plain files. Pinned by `test_links_go_through_a_running_server_only`.
3. **Medium, scripts/library.py, learning records.** A record marked `Status: superseded` showed like a current one. **Fixed:** such a record is shown with "superseded" after its date, so the history stays visible but is not read as current understanding. Pinned in `test_the_page_lists_what_each_course_holds`.
4. **Medium, scripts/check_lessons.py:41.** The `blockquote` exemption missed a quote nested inside a counted element such as `.quiz .model`. **Fixed:** each counted element's text has its nested quotes' text removed before sentences are split.
5. **Low, scripts/check_lessons.py:44.** The splitter still ignored a straight single quote or a closing square bracket after a full stop. **Fixed:** both added to the closing marks.
6. **Low, SKILL.md:50.** The map-lesson exception left a thin map ambiguously acceptable. **Fixed:** the exception now covers only the parts list in the map's diagram or table; the map's prose still explains the ideas that make the parts fit together.
7. **Low, README.md:153.** The safety note promised one file written outside a course. **Fixed:** it now names the diagram profile, the library page and its two style files.

Also reported: `Course.review` matched the old implementation on 10,000 generated histories and the existing test fixture, keeping exactly `{due, waiting}`; both course indexes under `~/learn` parsed; release checks passed. The reviewer could not run the library tests in its sandbox (temporary-directory setup blocked) and did not rerun the browser suites; those were run here and pass (see the test record and the commit).

Verdict as given: not safe to release until items 1 to 4 were fixed and U3 was complete. Both are now done: items 1 to 7 fixed above, U3 recorded in `2026-10-22-teaching-depth-test.md`.
