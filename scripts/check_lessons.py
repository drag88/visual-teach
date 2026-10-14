"""Check a visual-teach workspace before handing lessons to the learner.

Usage: python3 check_lessons.py <workspace> [screenshot-dir]

For every page it checks that local links resolve and that nothing scrolls sideways at phone
width. For every lesson it answers each quiz correctly and expects a perfect score, checks that
diagram labels render at a readable size on a phone, and fails on any script error. Screenshots
of each lesson at phone width, light and dark, go to the screenshot dir when one is given.
Needs Python Playwright with Chromium.
"""

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_course import drifted  # noqa: E402

PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1280, "height": 900}
MIN_LABEL_PX = 9.5
MAX_SENTENCE_WORDS = 25


def check_links(pages):
    problems = []
    for page in pages:
        for href in re.findall(r'href="([^"#:?]+)"', page.read_text()):
            if not (page.parent / href).resolve().exists():
                problems.append(f"{page.name}: broken link {href}")
    return problems


def long_sentences(pg):
    """Sentences in the lesson's prose, captions and quizzes that run past the plain-English limit."""
    text = pg.evaluate(
        """() => [...document.querySelectorAll("main p, main li, main figcaption, main td, .quiz .q, .quiz .fb, .quiz .model")]
          .filter((el) => !el.closest("pre, nav, footer, .read"))
          .map((el) => el.innerText).join("\\n")"""
    )
    sentences = re.split(r"(?<=[.!?])\s+|\n", text)
    return [s.strip() for s in sentences if len(s.split()) > MAX_SENTENCE_WORDS]


def answer_quizzes(pg):
    for q in pg.locator(".quiz.mcq").all():
        q.locator("button[data-right]").click()
    for q in pg.locator(".quiz.order").all():
        for row in q.locator(".order-row").all():
            row.locator("select").select_option(row.get_attribute("data-pos"))
        q.locator("button.act").click()
    for q in pg.locator(".quiz.match").all():
        for row in q.locator(".match-row").all():
            row.locator("select").select_option(row.get_attribute("data-a"))
        q.locator("button.act").click()
    for q in pg.locator(".quiz.spot").all():
        q.locator(f'g[data-spot="{q.get_attribute("data-answer")}"]').first.click()
    for q in pg.locator(".quiz.recall").all():
        q.locator("textarea").fill("answer written from memory")
        q.locator("button.act").click()
    return pg.locator(".quiz").count()


def smallest_diagram_label(pg):
    return pg.evaluate(
        """() => {
          let min = Infinity;
          document.querySelectorAll("figure.diagram svg").forEach((svg) => {
            const scale = svg.getBoundingClientRect().width / svg.viewBox.baseVal.width;
            svg.querySelectorAll("text").forEach((t) => {
              const size = parseFloat(getComputedStyle(t).fontSize) * scale;
              if (size < min) min = size;
            });
          });
          return min;
        }"""
    )


def main():
    root = Path(sys.argv[1]).expanduser().resolve()
    shots = Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 else None
    lessons = sorted(root.glob("lessons/*.html"))
    pages = [p for p in [root / "index.html"] if p.exists()] + lessons + sorted(root.glob("reference/*.html"))
    problems = check_links(pages)
    problems += [f"{p.name}: does not load ask.js" for p in pages if "ask.js" not in p.read_text()]
    problems += [f"assets/{n} differs from the skill's copy; run sync_course.py" for n in drifted(root)]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for scheme in ("light", "dark"):
            ctx = browser.new_context(viewport=PHONE, color_scheme=scheme, device_scale_factor=2)
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            for page in pages:
                pg.goto(page.as_uri())
                if pg.evaluate("document.documentElement.scrollWidth > window.innerWidth"):
                    problems.append(f"{page.name} ({scheme}): page scrolls sideways at phone width")
            for lesson in lessons:
                pg.goto(lesson.as_uri())
                if scheme == "light":
                    n = answer_quizzes(pg)
                    score = pg.locator("#score").inner_text() if pg.locator("#score").count() else ""
                    graded = n - pg.locator(".quiz.recall").count()
                    if graded and score != f"{graded} of {graded} right first time":
                        problems.append(f"{lesson.name}: answering every quiz correctly scored '{score}'")
                    for s in long_sentences(pg):
                        problems.append(f"{lesson.name}: sentence over {MAX_SENTENCE_WORDS} words: {s[:90]}...")
                    smallest = smallest_diagram_label(pg)
                    if smallest != float("inf") and smallest < MIN_LABEL_PX:
                        problems.append(f"{lesson.name}: smallest diagram label renders at {smallest:.1f}px on a phone")
                if shots:
                    shots.mkdir(parents=True, exist_ok=True)
                    pg.screenshot(path=str(shots / f"{lesson.stem}-{scheme}.png"), full_page=True)
            problems += [f"{scheme}: script error: {e}" for e in errors]
            ctx.close()
        ctx = browser.new_context(viewport=DESKTOP)
        pg = ctx.new_page()
        for page in pages:
            pg.goto(page.as_uri())
            if pg.evaluate("document.documentElement.scrollWidth > window.innerWidth"):
                problems.append(f"{page.name}: page scrolls sideways at desktop width")
        browser.close()

    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print(f"ok: {len(pages)} pages, {len(lessons)} lessons")


if __name__ == "__main__":
    main()
