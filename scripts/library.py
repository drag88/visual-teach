"""Write the learning library: one page, <learn-root>/index.html, listing every course and what it holds.

Usage: python3 library.py <learn-root>

A course is a folder directly under learn-root holding both MISSION.md and index.html; anything else (hidden
folders, _sources, _build) is skipped. Per course the page shows what is available (lessons and their status,
reference sheets, carry-over rules, glossary terms) and what the learner has shown (learning records, retired quiz
questions, questions due for review). There is no search box: the browser's find on this one page searches every
course at once.

Each run rebuilds the page from the courses' own files and copies the skill's style.css and theme.js into
library-assets/ beside it, so the library looks like the courses and has the same light and dark switch. The courses
themselves are only read. A course whose server is running is linked through it, so review and citations work.
"""

import html
import json
import re
import shutil
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
import urllib.request
from urllib.parse import quote

from serve import records_in, review_of  # the scripts folder is on the path when this runs

SKILL = Path(__file__).resolve().parent.parent
MARKER = "<!-- visual-teach library -->"
ASSETS = ["style.css", "theme.js"]
ASSETS_DIR = "library-assets"  # its own folder, so a learn folder's own assets/ is never touched


def words(text):
    return " ".join(text.split())


def esc(text):
    return html.escape(text, quote=True)


def link(href, text):
    return f'<a href="{esc(href)}">{esc(text)}</a>'


def safely(read, default):
    """read(), or default when the file it reads is missing or malformed, so one broken file empties only its own
    part of one course and the page still gets written."""
    try:
        return read()
    except Exception:  # whatever a bad file raises: OSError, UnicodeDecodeError, a parser's own error
        return default


class Index(HTMLParser):
    """What the library needs from a course's index.html: the h1, each item of ol.syllabus, and the reference sheets
    linked under the Reference heading. Read as HTML, so a class or href is found however the tag is written."""

    def __init__(self, text):
        super().__init__()
        self.title, self.lessons, self.sheets = "", [], []
        self.heading = None  # [tag, text so far] inside an h1 or h2
        self.section = ""  # the last h2's text
        self.syllabus = False
        self.item = self.sheet = None  # the syllabus item and the reference link being read
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        a = {k: v or "" for k, v in attrs}
        classes = a.get("class", "").split()
        if tag in ("h1", "h2"):
            self.heading = [tag, ""]
        elif tag == "ol" and "syllabus" in classes:
            self.syllabus = True
        elif tag == "li" and self.syllabus:
            self.item = {"title": "", "href": None, "soon": "soon" in classes, "cut": False}
            self.lessons.append(self.item)
        elif tag == "br" and self.item:
            self.item["cut"] = True  # after the line break come the item's tags, not its title
        elif tag == "a" and self.item and not self.item["cut"]:
            self.item["href"] = self.item["href"] or a.get("href") or None
        elif tag == "a" and self.section.lower().startswith("reference") and a.get("href", "").startswith("reference/"):
            self.sheet = {"href": a["href"], "title": ""}
            self.sheets.append(self.sheet)

    def handle_endtag(self, tag):
        if self.heading and tag == self.heading[0]:
            text = words(self.heading[1])
            if tag == "h2":
                self.section = text
            elif not self.title:
                self.title = text
            self.heading = None
        elif tag == "ol":
            self.syllabus, self.item = False, None
        elif tag == "li":
            self.item = None
        elif tag == "a":
            self.sheet = None

    def handle_data(self, data):
        if self.heading:
            self.heading[1] += data
        if self.item and not self.item["cut"]:
            self.item["title"] += data
        if self.sheet:
            self.sheet["title"] += data


class Rules(HTMLParser):
    """The first cell of each table row in reference/carry-over.html: the portable rule. Header rows use th."""

    def __init__(self, text):
        super().__init__()
        self.rules, self.cells, self.cell = [], 0, None
        self.feed(text)
        self.close()

    def end_cell(self):
        if self.cell is not None and words(self.cell):
            self.rules.append(words(self.cell))
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag in ("tr", "td", "th"):
            self.end_cell()  # a cell whose end tag was left out ends where the next one starts
            self.cells = 0 if tag == "tr" else self.cells + 1
            if tag == "td" and self.cells == 1:
                self.cell = ""

    def handle_endtag(self, tag):
        if tag in ("td", "tr", "table"):
            self.end_cell()

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data


def read(path):
    return Path(path).read_text(encoding="utf-8")


def why(mission):
    """The first paragraph under "## Why" in MISSION.md, as one line."""
    lines = mission.split("\n")
    start = next(i for i, line in enumerate(lines) if line.strip().lower() == "## why") + 1
    para = []
    for line in lines[start:]:
        if line.startswith("#") or (not line.strip() and para):
            break
        para.append(line)
    return words(" ".join(para))


def terms(glossary):
    """The bold term that opens each glossary entry (GLOSSARY-FORMAT.md: **Term**: definition)."""
    return [words(t) for t in re.findall(r"^\*\*(.+?)\*\*", glossary, re.M)]


def record(path):
    """(title, date, superseded) for one learning record: its first "# " heading, the day the file last changed, and
    whether its Status says a later record replaced it (LEARNING-RECORD-FORMAT.md), so history is not shown as current."""
    text = read(path)
    title = next((line[2:] for line in text.split("\n") if line.startswith("# ")), path.stem)
    day = datetime.fromtimestamp(path.stat().st_mtime).date()
    superseded = re.search(r"^Status:\s*superseded", text, re.M | re.I) is not None
    return words(title), f"{day.day} {day:%b %Y}", superseded


def server(ws):
    """(url, token) of the course's running server, or None. Links then open the live pages, where review, citations
    and questions work; as plain files they only read. A stale .serve.json is a crash or a reboot, so it is pinged."""
    run = safely(lambda: json.loads(read(ws / ".serve.json")), {})
    port, url = run.get("port"), run.get("url")
    token = run.get("phone_url", "").partition("?k=")[2] or None
    if not isinstance(port, int) or not isinstance(url, str):
        return None
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/api/ping" + (f"?k={token}" if token else ""), timeout=1) as r:
            info = json.loads(r.read())
    except (OSError, ValueError):
        return None
    return (url.rstrip("/"), token) if isinstance(info, dict) and info.get("course") == str(ws) else None


def review(log):
    """(questions due, retired questions) from a course's quiz.jsonl, by the server's own rule."""
    due, _, retired = review_of(records_in(read(log)))
    return len(due), retired


def course(ws):
    """Everything the page shows for one course folder."""
    index = safely(lambda: Index(read(ws / "index.html")), None)
    due, retired = safely(lambda: review(ws / "quiz.jsonl"), (0, []))
    return {"name": ws.name, "title": index.title if index and index.title else ws.name, "server": server(ws),
            "why": safely(lambda: why(read(ws / "MISSION.md")), ""),
            "lessons": index.lessons if index else [], "sheets": index.sheets if index else [],
            "rules": safely(lambda: Rules(read(ws / "reference" / "carry-over.html")).rules, []),
            "terms": safely(lambda: terms(read(ws / "GLOSSARY.md")), []),
            "records": [r for r in (safely(lambda: record(p), None) for p in sorted(ws.glob("learning-records/*.md"))) if r],
            "due": due, "retired": retired}


def href(c, path):
    """A link into the course: through its running server when there is one, else the file beside this page."""
    if c["server"]:
        url, token = c["server"]
        page, _, fragment = path.partition("#")
        return f"{url}/{page}" + (f"?k={token}" if token else "") + (f"#{fragment}" if fragment else "")
    return f"{quote(c['name'])}/{path}"


def table(groups):
    """Groups of (label, [cell HTML]): one item per row, so long text wraps in its own cell, and the label only on its
    group's first row. Plain cells, not th: on a phone style.css stacks each row and hides any row holding a th, so
    there the label reads as a heading over its items."""
    rows = [f"<tr><td>{label if i == 0 else ''}</td><td>{cell}</td></tr>"
            for label, cells in groups for i, cell in enumerate(cells)]
    return '<div class="table-wrap"><table>\n' + "\n".join(rows) + "\n</table></div>" if rows else ""


def render(c):
    out = [f'<h2>{link(href(c, "index.html"), c["title"])}</h2>']
    if c["why"]:
        out.append(f"<p>{esc(c['why'])}</p>")
    out.append("<h3>Available</h3>")
    if c["lessons"]:
        items = []
        for lesson in c["lessons"]:
            name = link(href(c, lesson["href"]), words(lesson["title"])) if lesson["href"] else esc(words(lesson["title"]))
            soon = ' class="soon"' if lesson["soon"] else ""
            items.append(f'<li{soon}>{name}<br><span class="tag">{"planned" if lesson["soon"] else "ready"}</span></li>')
        out.append('<ol class="syllabus">\n' + "\n".join(items) + "\n</ol>")
    sheet = href(c, "reference/carry-over.html")
    out.append(table([("Sheets", [link(href(c, s["href"]), words(s["title"])) for s in c["sheets"]]),
                      ("Rules", [link(sheet, rule) for rule in c["rules"]]),
                      ("Terms", [esc(term) for term in c["terms"]])]))
    out.append("<h3>Shown</h3>")
    due = c["due"]
    out.append(table([("Records", [f"{esc(title)} · {day}" + (" · superseded" if old else "") for title, day, old in c["records"]]),
                      ("Retired", [link(href(c, r["href"]), r["q"] if isinstance(r["q"], str) else r["quiz"]) for r in c["retired"]]),
                      ("Review", [link(href(c, "index.html"), f"{due} question{'' if due == 1 else 's'} due")])]))
    return "\n".join(part for part in out if part)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Learning library</title>
{marker}
<link rel="stylesheet" href="{assets}/style.css">
<script src="{assets}/theme.js"></script>
</head>
<body>
<main>

<h1>Learning library</h1>
<p class="subtitle">Every course in this folder: what it offers and what you have shown you know. Use your browser's find to look an idea up across all of them.</p>

{courses}

<p class="aside">A question is retired once you get it right three times in a row after missing it. This page is rebuilt each time you open a course.</p>

</main>
</body>
</html>
"""


def write(root):
    """Rebuild root/index.html and its two shared files, and return the page's path. An index.html that is not a
    library page is left alone, so pointing this at a course folder by mistake cannot overwrite the course."""
    root = Path(root).expanduser().resolve()
    page = root / "index.html"
    if page.is_symlink() or (page.exists() and MARKER not in page.read_text(encoding="utf-8", errors="replace")):
        raise ValueError(f"{page} is not a library page, so it was left alone.")
    if (root / ASSETS_DIR).is_symlink():
        raise ValueError(f"{root / ASSETS_DIR} is a symlink, so it was left alone.")
    (root / ASSETS_DIR).mkdir(exist_ok=True)
    for name in ASSETS:
        dest = root / ASSETS_DIR / name
        dest.unlink(missing_ok=True)  # replace a link with a copy; never write through it
        shutil.copy(SKILL / "starter" / "assets" / name, dest)
    found = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))
                   and (p / "MISSION.md").is_file() and (p / "index.html").is_file())
    courses = "\n\n".join(render(course(p)) for p in found) or "<p>No courses yet.</p>"
    page.write_text(PAGE.format(marker=MARKER, courses=courses, assets=ASSETS_DIR), encoding="utf-8")
    return page


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        print(f"Wrote {write(sys.argv[1])}")
    except (OSError, ValueError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
