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

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_course import drifted  # noqa: E402

PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1280, "height": 900}
MIN_LABEL_PX = 9.5
MAX_SENTENCE_WORDS = 25
SELF_MARKED = ".quiz.recall, .quiz.predict"  # the learner marks these; they stay out of the score


def check_links(pages):
    problems = []
    for page in pages:
        for href in re.findall(r'href="([^"#:?]+)"', page.read_text(encoding="utf-8")):
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


def answer_quiz(q):
    kind = (q.get_attribute("class") or "").split()
    if "mcq" in kind:
        q.locator("button[data-right]").click()
    elif "order" in kind or "match" in kind:
        rows, key = (".order-row", "data-pos") if "order" in kind else (".match-row", "data-a")
        for row in q.locator(rows).all():
            row.locator("select").select_option(row.get_attribute(key))
        q.locator("button.act").click()
    elif "spot" in kind:
        q.locator(f'g[data-spot="{q.get_attribute("data-answer")}"]').first.click()
    elif "recall" in kind or "predict" in kind:
        q.locator("textarea").fill("answer written from memory")
        q.locator("button.act").click()
        # Self-marks feed review, not the score, so marking them right must leave the score line alone.
        q.locator("button.mark", has_text="I got it").click()


def answer_quizzes(pg, lesson):
    """Answer every quiz correctly. Returns the quiz count and one line for each quiz that could not be answered:
    a broken quiz is a problem to fix in the lesson, not a crash of the whole check."""
    quizzes, problems = pg.locator(".quiz").all(), []
    for q in quizzes:
        try:
            answer_quiz(q)
            continue
        except PlaywrightTimeout:
            reason = "its right answer, or the part to tap, is not on the page"
        except PlaywrightError as exc:
            reason = (str(exc).splitlines() or ["no reason given"])[0]
        problems.append(f"{lesson.name}: quiz {q.get_attribute('id') or '(no id)'} could not be answered: {reason}")
    return len(quizzes), problems


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


def launch(p):
    """Playwright's own Chromium, or the installed Chrome when that was never downloaded."""
    try:
        return p.chromium.launch()
    except Exception:
        return p.chromium.launch(channel="chrome")


def main():
    root = Path(sys.argv[1]).expanduser().resolve()
    shots = Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 else None
    lessons = sorted(root.glob("lessons/*.html"))
    pages = [p for p in [root / "index.html"] if p.exists()] + lessons + sorted(root.glob("reference/*.html"))
    problems = check_links(pages)
    for page in pages:
        text = page.read_text(encoding="utf-8")
        problems += [f"{page.name}: does not load {js}" for js in ("theme.js", "ask.js") if js not in text]
    problems += [f"assets/{n} differs from the skill's copy; run sync_course.py" for n in drifted(root)]

    with sync_playwright() as p:
        browser = launch(p)
        for scheme in ("light", "dark"):
            ctx = browser.new_context(viewport=PHONE, color_scheme=scheme, device_scale_factor=2)
            pg = ctx.new_page()
            pg.set_default_timeout(5000)  # a quiz that cannot be answered fails in seconds, not half a minute
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            for page in pages:
                pg.goto(page.as_uri())
                if pg.evaluate("document.documentElement.scrollWidth > window.innerWidth"):
                    problems.append(f"{page.name} ({scheme}): page scrolls sideways at phone width")
            for lesson in lessons:
                pg.goto(lesson.as_uri())
                if scheme == "light":
                    n, unanswered = answer_quizzes(pg, lesson)
                    problems += unanswered
                    score = pg.locator("#score").inner_text() if pg.locator("#score").count() else ""
                    graded = n - pg.locator(SELF_MARKED).count()
                    # Review history and links key on the quiz id, so each needs its own.
                    ids = pg.evaluate("[...document.querySelectorAll('.quiz')].map((q) => q.id)")
                    if "" in ids:
                        problems.append(f'{lesson.name}: {ids.count("")} quiz(zes) without an id="q-..."')
                    dupes = sorted({i for i in ids if i and ids.count(i) > 1})
                    if dupes:
                        problems.append(f"{lesson.name}: quiz id used twice: {', '.join(dupes)}")
                    if graded and not unanswered and score != f"{graded} of {graded} right first time":
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
            hidden = pg.evaluate("[...document.querySelectorAll('main pre')].filter((p) => p.scrollWidth > p.clientWidth + 1).length")
            if hidden:
                problems.append(f"{page.name}: {hidden} code block(s) hide long lines behind a sideways scroll")
        browser.close()

    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print(f"ok: {len(pages)} pages, {len(lessons)} lessons")


if __name__ == "__main__":
    main()
