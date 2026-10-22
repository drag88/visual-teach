"""Tests for library.py: the learning library page built from the course folders, and when opening a course
rebuilds it. No network, no Claude.

Usage: python3 test_library.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import library  # noqa: E402

INDEX = """<!doctype html><html><head><title>Tab title</title></head><body><main>
<h1>Tiny &amp; course</h1>
<h2>Fundamentals</h2>
<ol class="syllabus">
  <li><a href="lessons/0001-one.html">The first lesson</a><br><span class="tag">ready · its terms</span></li>
  <li class="soon">The second lesson<br><span class="tag">not written yet</span></li>
</ol>
<h2>Reference</h2>
<ul>
  <li><a href="reference/carry-over.html">Rules that carry over</a>: for the next project</li>
  <li><a href="https://example.org/">Not a sheet</a></li>
</ul>
</main></body></html>
"""

CARRY_OVER = """<!doctype html><html><body><main><h1>Rules that carry over</h1>
<div class="table-wrap"><table>
<tr><th>Portable rule</th><th>How it showed up here</th></tr>
<tr><td>A request and its <code>execution</code> are separate.</td><td>The model asks; the tool reads.</td></tr>
<tr><td>Evidence decides the next lap.</td><td>A pass stopped the loop.</td></tr>
</table></div></main></body></html>
"""

GLOSSARY = """# Tiny Glossary

A **bold word** in the description is not a term.

## Terms

**Harness**:
The software around a model that runs its tools.

**Tool call**:
A request from the model to run one tool.
"""


def at(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).astimezone().isoformat(timespec="seconds")


def make_course(root, name="tiny"):
    ws = root / name
    for folder in ("lessons", "reference", "learning-records"):
        (ws / folder).mkdir(parents=True)
    (ws / "MISSION.md").write_text("# Mission: Tiny\n\n## Why\n\nTo learn the\nsmall things first.\n\nNot this.\n\n"
                                   "## Success looks like\n- Something\n", encoding="utf-8")
    (ws / "index.html").write_text(INDEX, encoding="utf-8")
    (ws / "lessons" / "0001-one.html").write_text("<h1>One</h1>", encoding="utf-8")
    (ws / "reference" / "carry-over.html").write_text(CARRY_OVER, encoding="utf-8")
    (ws / "GLOSSARY.md").write_text(GLOSSARY, encoding="utf-8")
    (ws / "learning-records" / "0001-x.md").write_text("---\nStatus: open\n---\n\n# The loop clicked\n\nBody.\n",
                                                      encoding="utf-8")
    (ws / "learning-records" / "0002-y.md").write_text("---\nStatus: superseded by LR-0003\n---\n\n# An old idea\n",
                                                      encoding="utf-8")
    lesson = "lessons/0001-one.html"
    rows = [  # q-kept: missed, then right three times, so retired. q-again: missed yesterday, so due.
        {"t": at(9), "lesson": lesson, "quiz": "q-kept", "q": "Which part runs the tool?", "right": False},
        {"t": at(8), "lesson": lesson, "quiz": "q-kept", "q": "Which part runs the tool?", "right": True},
        {"t": at(5), "lesson": lesson, "quiz": "q-kept", "q": "Which part runs the tool?", "right": True},
        {"t": at(2), "lesson": lesson, "quiz": "q-again", "q": "What stops the loop?", "right": None},
        {"t": at(1.01), "lesson": lesson, "quiz": "q-again", "q": "What stops the loop?", "right": False},
        {"t": at(1), "lesson": lesson, "quiz": "q-kept", "q": "Which part runs the tool?", "right": True},
    ]
    (ws / "quiz.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows) + "not json\n", encoding="utf-8")
    return ws


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.ws = make_course(self.root)
        (self.root / "notes").mkdir()
        (self.root / "notes" / "index.html").write_text("<h1>Not a course</h1>", encoding="utf-8")  # no MISSION.md
        (self.root / "_sources" / "x").mkdir(parents=True)
        for name in ("MISSION.md", "index.html"):
            (self.root / "_sources" / name).write_text("<h1>Sources</h1>", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_the_page_lists_what_each_course_holds(self):
        page = library.write(self.root)
        html = page.read_text(encoding="utf-8")
        self.assertIn(library.MARKER, html)
        self.assertEqual(html.count('<h2><a href="tiny/index.html">Tiny &amp; course</a></h2>'), 1, "the course, once")
        self.assertNotIn("Not a course", html, "a folder without MISSION.md is skipped")
        self.assertNotIn("Sources", html, "_sources is skipped")
        self.assertIn("<p>To learn the small things first.</p>", html, "the Why's first paragraph")
        self.assertIn('<li><a href="tiny/lessons/0001-one.html">The first lesson</a><br><span class="tag">ready</span></li>',
                      html)
        self.assertIn('<li class="soon">The second lesson<br><span class="tag">planned</span></li>', html)
        self.assertIn('<a href="tiny/reference/carry-over.html">Rules that carry over</a>', html)
        self.assertNotIn("Not a sheet", html, "only reference/ links are sheets")
        rules = ["A request and its execution are separate.", "Evidence decides the next lap."]
        self.assertEqual(library.course(self.ws)["rules"], rules, "one per body row; the header row is not a rule")
        self.assertIn(f'<tr><td>Rules</td><td><a href="tiny/reference/carry-over.html">{rules[0]}</a></td></tr>', html)
        self.assertIn(f'<tr><td></td><td><a href="tiny/reference/carry-over.html">{rules[1]}</a></td></tr>', html)
        self.assertIn("<tr><td>Terms</td><td>Harness</td></tr>\n<tr><td></td><td>Tool call</td></tr>", html)
        self.assertNotIn("bold word", html, "only a bold term opening a line is a glossary entry")
        self.assertIn("<tr><td>Records</td><td>The loop clicked · ", html)
        self.assertNotIn("The loop clicked · superseded", html)
        self.assertIn("An old idea · ", html)
        self.assertIn(" · superseded</td></tr>", html, "a replaced record is history, not current understanding")
        self.assertEqual(len(library.course(self.ws)["retired"]), 1)
        self.assertIn('<tr><td>Retired</td><td><a href="tiny/lessons/0001-one.html#q-kept">Which part runs the tool?</a>',
                      html)
        self.assertIn('<a href="tiny/index.html">1 question due</a>', html)
        self.assertNotIn("<th", html, "on a phone style.css hides every table row that holds a th")
        self.assertIn('href="library-assets/style.css"', html)
        for name in library.ASSETS:
            self.assertEqual((self.root / library.ASSETS_DIR / name).read_bytes(),
                             (HERE.parent / "starter" / "assets" / name).read_bytes())
        library.write(self.root)
        self.assertEqual(page.read_text(encoding="utf-8"), html, "a second run writes the same bytes")

    def test_review_follows_the_server_rule(self):
        due, retired = library.review(self.ws / "quiz.jsonl")
        self.assertEqual((due, [r["quiz"] for r in retired]), (1, ["q-kept"]))

    def test_a_broken_file_skips_only_its_own_part(self):
        (self.ws / "reference" / "carry-over.html").write_bytes(b"\xff\xfe<table><tr><td>bad")
        (self.ws / "MISSION.md").write_text("# Mission with no Why\n", encoding="utf-8")
        (self.ws / "quiz.jsonl").write_bytes(b"\xff")
        html = library.write(self.root).read_text(encoding="utf-8")
        self.assertNotIn("<td>Rules</td>", html)
        self.assertIn("<td>Harness</td>", html, "the rest of the course is still there")
        self.assertIn("0 questions due", html)

    def test_links_go_through_a_running_server_only(self):
        (self.ws / ".serve.json").write_text('{"pid": 1, "port": 1, "url": "http://localhost:1/"}', encoding="utf-8")
        html = library.write(self.root).read_text(encoding="utf-8")
        self.assertIn('<h2><a href="tiny/index.html">', html, "nothing answers on port 1, so links stay plain files")
        with mock.patch.object(library, "server", return_value=("http://localhost:8765", None)):
            html = library.write(self.root).read_text(encoding="utf-8")
        self.assertIn('<a href="http://localhost:8765/lessons/0001-one.html#q-kept">', html)
        with mock.patch.object(library, "server", return_value=("http://localhost:8765", "tok")):
            html = library.write(self.root).read_text(encoding="utf-8")
        self.assertIn('<a href="http://localhost:8765/lessons/0001-one.html?k=tok#q-kept">', html, "the token goes before the fragment")

    def test_an_index_that_is_not_the_library_is_left_alone(self):
        (self.root / "index.html").write_text("<h1>Someone's own page</h1>", encoding="utf-8")
        with self.assertRaises(ValueError):
            library.write(self.root)
        self.assertEqual((self.root / "index.html").read_text(encoding="utf-8"), "<h1>Someone's own page</h1>")


class OpenCourseTest(unittest.TestCase):
    """Opening a course rebuilds the library only in ~/learn or where the library already is."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.ws = make_course(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def update(self):
        import open_course
        out = StringIO()
        with redirect_stdout(out):
            open_course.update_library(self.ws)
        return out.getvalue()

    def test_a_course_elsewhere_gets_no_page_beside_it(self):
        self.assertEqual(self.update(), "")
        self.assertFalse((self.root / "index.html").exists())
        self.assertFalse((self.root / library.ASSETS_DIR).exists())

    def test_an_existing_library_is_rebuilt(self):
        (self.root / "index.html").write_text(library.MARKER, encoding="utf-8")
        self.assertEqual(self.update(), "")
        self.assertIn("Tiny &amp; course", (self.root / "index.html").read_text(encoding="utf-8"))

    def test_the_first_library_is_written_in_learn(self):
        learn = self.root / "learn"
        self.ws = make_course(learn)
        with mock.patch.dict(os.environ, {"HOME": str(self.root)}):  # Path.home() reads HOME
            self.assertEqual(self.update(), "")
        self.assertIn("Tiny &amp; course", (learn / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
