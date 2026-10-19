"""Browser test for the quiz widgets: a lesson opened as a plain file, no server.

Usage: python3 test_quiz.py
Needs Python Playwright with Chromium.
"""

import shutil
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_lessons import launch  # noqa: E402

STARTER = Path(__file__).resolve().parent.parent / "starter"
FILLER = "".join(f"<p>Filler paragraph {i}, so the quizzes sit below the first screen.</p>\n" for i in range(30))
# The mcq has no id, so quiz.js keys it by the first six words of its question.
MCQ_KEY = "k-which-part-does-the-work-in"

LESSON = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="../assets/style.css">
<script>window.got = []; document.addEventListener("quiz", (e) => got.push(e.detail));</script>
</head><body><main>
{FILLER}
<div class="quiz predict" id="q-print"><p class="q">What will this print?</p>
<pre><code>print(2 + 2)</code></pre><div class="model">It prints 4.</div></div>
<div class="quiz mcq"><p class="q">Which part does the work in this picture, and why?</p>
<div class="opts"><button class="opt" data-right>The step</button><button class="opt">The input</button></div>
<p class="fb">The step changes things.</p></div>
<div class="quiz recall" id="q-recall"><p class="q">Say what the step does.</p><div class="model">It turns input into output.</div></div>
<p class="score" id="score"></p>
{FILLER}
</main><script src="../assets/quiz.js"></script></body></html>
"""

DETAIL_KEYS = {"quiz", "type", "event", "right", "q", "answer", "model"}


def run(lesson):
    problems = []
    with sync_playwright() as p:
        browser = launch(p)
        pg = browser.new_page(viewport={"width": 390, "height": 844})
        pg.set_default_timeout(5000)
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(lesson.as_uri())
        score = lambda: pg.locator("#score").inner_text()

        keys = pg.evaluate("[...document.querySelectorAll('.quiz')].map((q) => q.dataset.quiz)")
        if keys != ["q-print", MCQ_KEY, "q-recall"]:
            problems.append(f"data-quiz keys are {keys}, not the ids plus {MCQ_KEY}")

        predict = pg.locator("#q-print")
        predict.locator("textarea").fill("4")
        predict.locator("button.act").click()
        if not predict.locator(".model").is_visible():
            problems.append("predict did not show the real outcome")
        predict.locator("button.mark", has_text="I got it").click()
        if score():
            problems.append(f"a self-mark alone wrote the score line '{score()}'")

        mcq = pg.locator(f'[data-quiz="{MCQ_KEY}"]')
        mcq.locator("button.opt:not([data-right])").click()
        mcq.locator("button.opt[data-right]").click()
        graded = score()
        if graded != "0 of 1 right first time":
            problems.append(f"after one wrong mcq the score reads '{graded}'")

        recall = pg.locator("#q-recall")
        recall.locator("textarea").fill("it changes things")
        recall.locator("button.act").click()
        recall.locator("button.mark", has_text="I missed it").click()
        if score() != graded:
            problems.append(f"a self-mark changed the score line from '{graded}' to '{score()}'")

        got = pg.evaluate("got")
        seen = [(d.get("quiz"), d.get("type"), d.get("event"), d.get("right")) for d in got]
        want = [
            ("q-print", "predict", "revealed", None),
            ("q-print", "predict", "answered", True),
            (MCQ_KEY, "mcq", "answered", False),
            ("q-recall", "recall", "revealed", None),
            ("q-recall", "recall", "answered", False),
        ]
        if seen != want:
            problems.append(f"quiz events were {seen}, expected {want}")
        problems += [f"event detail keys {sorted(d)}" for d in got if set(d) != DETAIL_KEYS]
        shown = [d for d in got if d.get("event") == "revealed"]
        if [(d.get("q"), d.get("answer"), d.get("model")) for d in shown] != [
            ("What will this print?", "4", "It prints 4."),
            ("Say what the step does.", "it changes things", "It turns input into output."),
        ]:
            problems.append(f"revealed events carry the wrong question, answer or model: {shown}")

        # A fresh page, so the hash is read on load rather than as an in-page hash change.
        pg2 = browser.new_page(viewport={"width": 390, "height": 844})
        pg2.on("pageerror", lambda e: errors.append(str(e)))
        pg2.goto(f"{lesson.as_uri()}#{MCQ_KEY}")
        landed = pg2.evaluate(f"""(() => {{
          const q = document.querySelector('[data-quiz="{MCQ_KEY}"]'), r = q.getBoundingClientRect();
          return {{inView: scrollY > 0 && r.top >= 0 && r.bottom <= innerHeight, flash: q.classList.contains("flash")}};
        }})()""")
        if not landed["inView"]:
            problems.append(f"#{MCQ_KEY} did not scroll its quiz into view")
        if not landed["flash"]:
            problems.append(f"#{MCQ_KEY} did not flash its quiz")

        problems += [f"script error: {e}" for e in errors]
        browser.close()
    return problems


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shutil.copytree(STARTER / "assets", tmp / "assets")
        (tmp / "lessons").mkdir()
        lesson = tmp / "lessons/0001-lesson.html"
        lesson.write_text(LESSON)
        problems = run(lesson)
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print("ok: predict reveals, self-marks fire answered and leave the score alone, mcq fires answered,"
          " an unkeyed quiz gets a k- key and its hash scrolls to it and flashes")


if __name__ == "__main__":
    main()
