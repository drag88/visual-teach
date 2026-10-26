"""Browser test for ask-while-reading: the starter lesson, served by serve.py, with a fake `claude`.

Usage: python3 test_reader.py [screenshot-dir]
Needs Python Playwright with Chromium. Costs nothing: the fake replays a canned answer.
"""

import json
import os
import shutil
import stat
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import serve  # noqa: E402
from check_lessons import launch  # noqa: E402
from test_serve import FAKE_CLAUDE, fake_codex  # noqa: E402

STARTER = HERE.parent / "starter"
WIDTHS = {"desktop": 1280, "big": 1728, "phone": 390}
SOURCE_WIDTHS = {"phone": 390, "laptop": 1000, "desktop": 1280}  # bottom sheet below 1180, side panel above
# A dictated question, as long as the ones real learners ask from the bottom bar.
LONG_QUESTION = ("So does that mean that if the reader comes back to the logbook on a different day it will be a new "
                 "session, and it will not remember what was said before unless something saved it, and if so where?")
FILLER = "".join(f"<p>Filler paragraph {i} that gives the lesson enough length to scroll through.</p>\n" for i in range(24))
# Real code quoted with its citation, a citation to a private file, and a recall quiz.
EXTRA = """<pre><code>def greet(name):
    return "hi " + name</code></pre>
<p class="src">src/app.py:40-41</p>
<p>Settings come from <code class="src">.env:1</code> when it starts.</p>
<div class="quiz recall" id="q-greet"><p class="q">What does greet return?</p><div class="model">A greeting with the name added</div></div>
"""
ANSWER = "It says hi to the name"


def build_workspace(root):
    shutil.copytree(STARTER / "assets", root / "assets")
    (root / "lessons").mkdir()
    lesson = (STARTER / "lesson.html").read_text().replace("<h2>Practice</h2>", FILLER + EXTRA + "<h2>Practice</h2>", 1)
    # Lesson files are written by teaching sessions, so a script inside one must never run when served.
    lesson = lesson.replace("<footer>", '<script>window.pwned = 1</script><img src="x" onerror="window.pwned = 2" alt="">\n<footer>', 1)
    (root / "lessons/0001-lesson.html").write_text(lesson)
    shutil.copy(STARTER / "index.html", root / "index.html")
    (root / "NOTES.md").write_text("Analogy: the runner is the office manager.\n")


def build_source(root):
    """A source folder: a 60-line file whose lines 40-41 the lesson quotes, a note, and a secret."""
    (root / "src").mkdir(parents=True)
    lines = [f"line_{i} = {i}" for i in range(1, 61)]
    lines[39:41] = ["def greet(name):", '    return "hi " + name']
    (root / "src/app.py").write_text("\n".join(lines) + "\n")
    (root / "notes.md").write_text("Greet is the front desk.\n")
    (root / ".env").write_text("SECRET=hunter2\n")


def last_stdin(log):
    return [json.loads(line) for line in Path(log).read_text().splitlines() if '"stdin"' in line][-1]["stdin"]


def select_words(pg, selector, words):
    """Highlight `words` inside the first element matching selector, as a reader would."""
    pg.evaluate(
        """([selector, words]) => {
          const el = document.querySelector(selector);
          const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
          let n;
          while ((n = walker.nextNode())) {
            const i = n.data.indexOf(words);
            if (i < 0) continue;
            const r = document.createRange();
            r.setStart(n, i);
            r.setEnd(n, i + words.length);
            const s = getSelection();
            s.removeAllRanges();
            s.addRange(r);
            return;
          }
          throw new Error("words not found");
        }""",
        [selector, words],
    )


def run(width_name, width, base, shots):
    problems = []
    with sync_playwright() as p:
        browser = launch(p)
        pg = browser.new_page(viewport={"width": width, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        url = f"{base}/lessons/0001-lesson.html"
        pg.goto(url)
        pg.wait_for_selector("body.ask-on")
        if pg.evaluate("window.pwned"):
            problems.append(f"{width_name}: a script written into a lesson ran")
        para = "main > h2 + p"
        assert pg.locator("main > [data-p]").count() >= 5, "paragraphs are numbered"
        if pg.locator(".ask-cite").count():
            problems.append(f"{width_name}: citations became buttons without a source folder")

        select_words(pg, para, "walks the hero")
        pg.wait_for_selector(".ask-sel:not([hidden])")
        if pg.locator(".ask-sel button:visible", has_text="Where else").count() or pg.locator(".ask-sel button:visible", has_text="Walk through").count():
            problems.append(f"{width_name}: Where else or Walk through offered on prose without a source folder")
        pg.locator(".ask-sel button", has_text="Explain").click()
        card = pg.locator(".ask-card").first
        card.locator(".ask-answer", has_text="office manager").first.wait_for()
        assert card.locator(".ask-pchip").count() == 1, "¶ citation became a chip"
        if width >= 1180:
            assert "in-margin" in card.get_attribute("class"), "card sits in the margin on wide screens"
            # Text plus answers fill a wide screen evenly: equal space left and right, nothing off the edge.
            left = pg.evaluate("document.querySelector('main').getBoundingClientRect().left")
            box = card.bounding_box()
            right = width - (box["x"] + box["width"])
            if right < 0 or abs(left - right) > 48 or max(left, right) > 0.12 * width:
                problems.append(f"{width_name}: {left:.0f}px empty on the left but {right:.0f}px on the right")
        else:
            assert pg.evaluate(f"document.querySelector('{para}').nextElementSibling.classList.contains('ask-card')"), \
                "card sits under its paragraph on narrow screens"
        card.locator(".ask-meta", has_text="first words").wait_for()

        card.locator(".ask-follow textarea").fill("And who is the worker?")
        card.locator(".ask-follow textarea").press("Enter")
        pg.wait_for_function("document.querySelectorAll('.ask-card .ask-ex').length === 2")
        card.locator(".ask-ex").nth(1).locator(".ask-answer", has_text="office manager").wait_for()

        # A page question asked mid-lesson lands beside the paragraph being read, without jumping the page.
        pg.evaluate("[...document.querySelectorAll('main > p')].find((p) => p.textContent.includes('Filler paragraph 12'))"
                    ".scrollIntoView({block: 'start'})")
        y = pg.evaluate("scrollY")
        on_screen = pg.evaluate("""[...document.querySelectorAll('main > [data-p]')]
          .filter((b) => { const r = b.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight; })
          .map((b) => '¶' + b.dataset.p)""")
        bar = pg.locator(".ask-bar textarea")
        bar.fill(LONG_QUESTION)
        if not bar.evaluate("(el) => el.scrollHeight <= el.clientHeight + 1"):
            problems.append(f"{width_name}: a long question is cut off in the bottom bar")
        bar.press("Enter")
        pg.wait_for_function("document.querySelectorAll('.ask-card').length === 2")
        whole = pg.locator(".ask-card", has=pg.locator(".ask-q", has_text="So does that mean"))
        whole.locator(".ask-answer", has_text="office manager").wait_for()
        asked_at = whole.locator(".ask-where").inner_text()
        if asked_at not in on_screen:
            problems.append(f"{width_name}: page question card sits at {asked_at}, not beside the paragraphs on screen {on_screen}")
        if abs(pg.evaluate("scrollY") - y) > 450:
            problems.append(f"{width_name}: asking about the page scrolled away from where the learner was reading")

        if pg.evaluate("document.documentElement.scrollWidth > window.innerWidth"):
            problems.append(f"{width_name}: page scrolls sideways")
        if shots:
            pg.screenshot(path=str(shots / f"reader-{width_name}.png"), full_page=True)

        # The course home page shows its own questions only, not every lesson's.
        pg.goto(f"{base}/")
        pg.wait_for_selector("body.ask-on")
        pg.wait_for_timeout(500)
        if pg.locator(".ask-card").count():
            problems.append(f"{width_name}: the course home page shows {pg.locator('.ask-card').count()} cards from lessons")
        pg.goto(url)
        pg.wait_for_selector("body.ask-on")

        pg.reload()
        pg.wait_for_function("document.querySelectorAll('.ask-card').length === 2")
        restored = pg.locator(".ask-card", has=pg.locator(".ask-kind", has_text="Explain"))
        assert "folded" in restored.get_attribute("class"), "saved cards come back folded"
        assert restored.locator(".ask-ex").count() == 2, "the follow-up came back with its thread"
        back = pg.locator(".ask-card", has=pg.locator(".ask-q", has_text="So does that mean")).locator(".ask-where").inner_text()
        if back != asked_at:
            problems.append(f"{width_name}: page question came back at {back}, not {asked_at}")

        # One switch hides every answer for plain reading, remembers it, and brings them back.
        toggle = pg.locator(".ask-show")
        if toggle.inner_text() != "Hide answers":
            problems.append(f"{width_name}: the switch reads '{toggle.inner_text()}' while answers show")
        toggle.click()
        if pg.locator(".ask-card:visible").count():
            problems.append(f"{width_name}: Hide answers left cards on screen")
        pg.reload()
        pg.wait_for_function("document.querySelectorAll('.ask-card').length === 2")
        if pg.locator(".ask-card:visible").count() or toggle.inner_text() != "Show answers (2)":
            problems.append(f"{width_name}: hidden answers did not stay hidden after a reload")
        if width >= 1180:
            gap = pg.evaluate("(() => { const r = document.querySelector('main').getBoundingClientRect(); return r.left - (innerWidth - r.right); })()")
            if abs(gap) > 2:
                problems.append(f"{width_name}: with answers hidden the text is not centred ({gap:.0f}px off)")
        toggle.click()
        if pg.locator(".ask-card:visible").count() != 2:
            problems.append(f"{width_name}: Show answers did not bring both cards back")
        restored.locator(".ask-toggle").click()
        restored.locator(".ask-foot button", has_text="Delete").click()
        pg.wait_for_function("document.querySelectorAll('.ask-card').length === 1")
        pg.reload()
        pg.wait_for_function("document.body.classList.contains('ask-on')")
        pg.wait_for_timeout(500)
        if pg.locator(".ask-card").count() != 1:
            problems.append(f"{width_name}: deleted card came back after reload")
        problems += [f"{width_name}: script error: {e}" for e in errors]
        browser.close()
    return problems


def check_sources(width_name, width, base, ws, log, shots):
    """Source panel, Walk through and Where else, answer citations, Check my answer, and review."""
    problems = []
    with sync_playwright() as p:
        browser = launch(p)
        pg = browser.new_page(viewport={"width": width, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{base}/lessons/0001-lesson.html")
        pg.wait_for_selector("body.ask-on")
        pre_p = pg.evaluate("document.querySelector('main > pre').dataset.p")
        quiz_p = pg.evaluate("document.querySelector('#q-greet').dataset.p")
        cited = "[...document.querySelectorAll('.ask-panel[open] .ask-line.cited')].map((l) => +l.dataset.n)"

        select_words(pg, "main > h2 + p", "walks the hero")
        pg.wait_for_selector(".ask-sel:not([hidden])")
        if pg.locator(".ask-sel button:visible", has_text="Walk through").count():
            problems.append(f"{width_name}: Walk through offered on prose")
        if not pg.locator(".ask-sel button:visible", has_text="Where else").count():
            problems.append(f"{width_name}: Where else missing with a source folder")
        pg.keyboard.press("Escape")

        # A lesson citation opens the file, cited lines tinted and in view.
        pg.locator("p.src .ask-cite").click()
        pg.wait_for_selector(".ask-panel[open] .ask-line.cited")
        if pg.evaluate(cited) != [40, 41]:
            problems.append(f"{width_name}: citation tinted lines {pg.evaluate(cited)}, not 40-41")
        tint = pg.evaluate("['.ask-line.cited', '.ask-line:not(.cited)'].map((q) => getComputedStyle(document.querySelector(q)).backgroundColor)")
        if tint[0] == tint[1]:
            problems.append(f"{width_name}: cited lines are not tinted")
        if not pg.evaluate("""(() => { const l = document.querySelector('.ask-line.cited').getBoundingClientRect();
            const b = document.querySelector('.ask-lines').getBoundingClientRect(); return l.top >= b.top && l.bottom <= b.bottom; })()"""):
            problems.append(f"{width_name}: the first cited line is not scrolled into view")
        # Wide screens: the panel fills the space right of the text and covers no lesson line.
        # Narrower: a bottom sheet, with the lesson readable above it.
        box = pg.locator(".ask-panel").bounding_box()
        text_right = pg.evaluate("document.querySelector('main').getBoundingClientRect().right")
        if width >= 1180 and (box["x"] < text_right - 1 or box["x"] + box["width"] < width - 1 or box["height"] < 899):
            problems.append(f"{width_name}: panel covers the text or leaves a gap: {box}, text ends at {text_right:.0f}")
        if width < 1180 and (box["width"] < width - 1 or box["y"] < 900 * 0.3 or box["y"] + box["height"] < 899):
            problems.append(f"{width_name}: panel is not a bottom sheet: {box}")

        # Highlighting in the panel offers the code actions; Walk through attaches to the quoted code block.
        select_words(pg, '.ask-line[data-n="40"]', "greet")
        pg.wait_for_selector(".ask-sel:not([hidden])")
        for label in ("Walk through", "Where else"):
            if not pg.locator(".ask-sel button:visible", has_text=label).count():
                problems.append(f"{width_name}: {label} missing for a selection in the panel")
        bar, sheet = pg.locator(".ask-sel").bounding_box(), pg.locator(".ask-panel").bounding_box()
        if width <= 720 and bar["y"] + bar["height"] > sheet["y"]:
            problems.append(f"{width_name}: the selection bar covers the source sheet")
        if pg.evaluate("document.documentElement.scrollWidth > window.innerWidth"):
            problems.append(f"{width_name}: page scrolls sideways with the panel open")
        if shots:
            pg.screenshot(path=str(shots / f"reader-panel-{width_name}.png"))
        os.environ["FAKE_TEXT"] = "Line 40 starts greet, see `src/app.py:40-41` and notes.md:1, like the office manager."
        pg.locator(".ask-sel button", has_text="Walk through").click()
        walk = pg.locator(".ask-card", has=pg.locator(".ask-kind", has_text="Walk through"))
        walk.locator(".ask-meta", has_text="first words").wait_for()
        if walk.locator(".ask-where").inner_text() != "¶" + pre_p:
            problems.append(f"{width_name}: walk card sits at {walk.locator('.ask-where').inner_text()}, not the code block ¶{pre_p}")
        if 'lines 40-40 of src/app.py' not in last_stdin(log):
            problems.append(f"{width_name}: Claude was not told the highlighted lines and path")
        # The answer sits under the asked lines inside the panel, not hidden behind it, and goes back
        # beside its lesson block when the panel closes.
        if not walk.evaluate("(c) => Boolean(c.closest('.ask-panel')) && c.previousElementSibling.dataset.n === '40'"):
            problems.append(f"{width_name}: walk answer is not under line 40 in the panel")
        pg.keyboard.press("Escape")
        if pg.locator(".ask-panel[open]").count():
            problems.append(f"{width_name}: Escape did not close the panel")
        try:  # the dialog's close event comes a moment after Escape. A locator wait, since the page's CSP forbids eval
            pg.locator("main .ask-card .ask-kind", has_text="Walk through").first.wait_for(timeout=3000)
        except Exception:
            problems.append(f"{width_name}: walk answer did not return to the lesson when the panel closed")

        # A citation in an answer opens the panel too.
        if walk.locator(".ask-answer .ask-src").count() != 2:
            problems.append(f"{width_name}: answer citations did not become links")
        walk.locator(".ask-answer .ask-src").first.click()
        pg.wait_for_selector(".ask-panel[open] .ask-line.cited")
        if pg.evaluate(cited) != [40, 41]:
            problems.append(f"{width_name}: answer citation tinted lines {pg.evaluate(cited)}, not 40-41")
        pg.locator(".ask-panel-head button", has_text="Close").click()

        # Highlighting in the lesson's quoted code sends its citation along.
        select_words(pg, "main > pre", "return")
        pg.wait_for_selector(".ask-sel:not([hidden])")
        if not pg.locator(".ask-sel button:visible", has_text="Walk through").count():
            problems.append(f"{width_name}: Walk through missing for a selection in code")
        pg.locator(".ask-sel button", has_text="Where else").click()
        pg.locator(".ask-card", has=pg.locator(".ask-kind", has_text="Where else")).locator(".ask-meta", has_text="first words").wait_for()
        if "of src/app.py" not in last_stdin(log):
            problems.append(f"{width_name}: a selection in quoted code did not name its source")

        # An inline citation flows with its sentence, so a "(" before it never ends a line on its own.
        if pg.evaluate("getComputedStyle(document.querySelector('code.src .ask-cite')).display") != "inline":
            problems.append(f"{width_name}: inline citations do not wrap with their sentence")

        # A private file shows one plain line and none of its content.
        pg.locator("code.src .ask-cite").click()
        pg.locator(".ask-panel[open] .ask-panel-note", has_text="not in the source folder").wait_for()
        if pg.locator(".ask-line").count() or "hunter2" in pg.locator(".ask-panel").inner_text():
            problems.append(f"{width_name}: a private file's content reached the panel")
        pg.locator(".ask-panel-head button", has_text="Close").click()

        # Quiz results are posted; a revealed recall answer can be checked by Claude.
        quiz_event = """([event, detail]) => document.querySelector('#q-greet').dispatchEvent(new CustomEvent('quiz',
            {bubbles: true, detail: {quiz: 'q-greet', type: 'recall', q: 'What does greet return?', event, ...detail}}))"""
        with pg.expect_response(lambda r: r.url.endswith("/api/quiz")) as posted:
            pg.evaluate(quiz_event, ["answered", {"right": True}])
        if not posted.value.ok or '"q-greet"' not in (ws / "quiz.jsonl").read_text():
            problems.append(f"{width_name}: a quiz result was not saved")
        os.environ["FAKE_TEXT"] = "Nearly. The office manager would add the greeting."
        pg.evaluate(quiz_event, ["revealed", {"right": None, "answer": ANSWER, "model": "A greeting with the name added"}])
        pg.locator("#q-greet .ask-check").click()
        check = pg.locator(".ask-card", has=pg.locator(".ask-kind", has_text="Check"))
        check.locator(".ask-meta", has_text="first words").wait_for()
        stdin = last_stdin(log)
        if ANSWER not in stdin or "A greeting with the name added" not in stdin:
            problems.append(f"{width_name}: the check did not send the answer and the right answer")
        if check.locator(".ask-where").inner_text() != "¶" + quiz_p or check.locator(".ask-q").inner_text() != ANSWER:
            problems.append(f"{width_name}: the check card is not at the quiz or does not show the answer")

        pg.reload()
        pg.wait_for_function("document.querySelectorAll('.ask-card').length === 3")
        if check.locator(".ask-q").inner_text() != ANSWER:
            problems.append(f"{width_name}: the check card came back without the learner's answer")

        # A late reply for an earlier file must not replace the open one; widening the window keeps a panel
        # answer in the panel; Connect keeps its topic list; a dark page prints light.
        held = []
        late = lambda url: "path=.env" in url  # noqa: E731
        pg.route(late, lambda route: held.append(route))
        pg.locator(".ask-cite", has_text=".env:1").click()
        pg.locator(".ask-cite", has_text="src/app.py").click()
        pg.wait_for_selector(".ask-panel[open] .ask-line.cited")
        held[0].continue_()
        pg.wait_for_timeout(400)
        if pg.locator(".ask-panel[open] .ask-line.cited").count() != 2:
            problems.append(f"{width_name}: a late reply for an earlier file replaced the open one")
            pg.locator(".ask-cite", has_text="src/app.py").click()
            pg.wait_for_selector(".ask-panel[open] .ask-line.cited")
        pg.unroute(late)
        if width < 1180:
            select_words(pg, '.ask-line[data-n="41"]', "return")
            pg.locator(".ask-sel button", has_text="Walk through").click()
            pg.wait_for_function("Boolean(document.querySelector('.ask-panel .ask-card'))")
            pg.set_viewport_size({"width": 1280, "height": 900})
            pg.wait_for_timeout(400)
            if not pg.evaluate("Boolean(document.querySelector('.ask-panel[open] .ask-card'))"):
                problems.append(f"{width_name}: widening the window moved a panel answer behind the panel")
            pg.set_viewport_size({"width": width, "height": 900})
        pg.locator(".ask-panel-head button", has_text="Close").click()
        select_words(pg, "main > h2 + p", "walks")
        pg.wait_for_selector(".ask-sel:not([hidden])")
        pg.locator(".ask-sel button", has_text="Connect").click()
        field = pg.evaluate("[document.activeElement.tagName, document.activeElement.getAttribute('list')]")
        if field != ["INPUT", "ask-topics"]:
            problems.append(f"{width_name}: Connect lost its topic suggestions ({field})")
        pg.keyboard.press("Escape")
        pg.evaluate("document.documentElement.dataset.theme = 'dark'")
        pg.emulate_media(media="print")
        printed = pg.evaluate("getComputedStyle(document.querySelector('main pre')).backgroundColor")
        pg.emulate_media(media="screen")
        if printed != "rgb(245, 245, 245)":
            problems.append(f"{width_name}: a dark page prints code on {printed}")

        # A missed question that is due shows on the course index.
        pg.goto(f"{base}/")
        pg.wait_for_selector("body.ask-on")
        pg.wait_for_selector("ol.syllabus ~ .ask-review a")
        links = pg.locator(".ask-review a")
        if links.count() != 1 or not links.first.get_attribute("href").endswith("/lessons/0001-lesson.html#q-old"):
            problems.append(f"{width_name}: review list is not the one due question")
        problems += [f"{width_name}: script error: {e}" for e in errors]
        browser.close()
    os.environ.pop("FAKE_TEXT", None)
    return problems


# Answers come from a model that may have read hostile text (a fetched page, a code comment), so they
# must render as text and plain links only, whatever they contain.
HOSTILE = "\n\n".join([
    "https://example.com/(https://x/onmouseover=window.pwned=1//",
    "[click](javascript:window.pwned=1) and [x](https://a.com/\"onmouseover=\"window.pwned=1)",
    "==<img src=x onerror=window.pwned=1>== and `<script>window.pwned=1</script>`",
    "**[a](https://b.com/(https://c.com/onmouseover=window.pwned=1//)**",
    "See lessons/x.html:3 and `a.py:1`, which stay text without a source folder.",
])


def check_answers_are_inert(base):
    problems = []
    with sync_playwright() as p:
        browser = launch(p)
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        pg.goto(f"{base}/lessons/0001-lesson.html")
        pg.wait_for_selector("body.ask-on")
        pg.locator(".ask-bar textarea").fill("Anything")
        pg.locator(".ask-bar .ask-send").click()
        pg.locator(".ask-card .ask-meta", has_text="first words").wait_for()
        for link in pg.locator(".ask-answer a").all():
            link.hover()
        bad = pg.evaluate("""() => {
          const out = [];
          for (const el of document.querySelectorAll('.ask-answer *')) {
            for (const a of el.attributes) if (/^on/i.test(a.name)) out.push(el.tagName + ' has ' + a.name);
            if (/^(SCRIPT|IMG|IFRAME|OBJECT|EMBED)$/.test(el.tagName)) out.push('element ' + el.tagName);
            if (el.tagName === 'A' && el.closest('a') !== el) out.push('nested link');
            if (el.tagName === 'A' && !el.classList.contains('ask-pchip') && !/^https?:/.test(el.getAttribute('href') || '')) out.push('link to ' + el.getAttribute('href'));
            if (el.tagName === 'A' && el.parentElement.closest('a')) out.push('link inside a link');
          }
          if (window.pwned) out.push('script ran');
          return out;
        }""")
        problems += [f"hostile answer: {b}" for b in bad]
        if pg.locator(".ask-src").count():
            problems.append("answer citations became links without a source folder")
        browser.close()
    return problems


def check_theme(base):
    """The theme switch flips light and dark whatever the system says, and remembers the choice."""
    problems = []
    bg = "getComputedStyle(document.body).backgroundColor"
    with sync_playwright() as p:
        browser = launch(p)
        url = f"{base}/lessons/0001-lesson.html"
        system = {}
        for scheme in ("light", "dark"):
            ctx = browser.new_context(color_scheme=scheme)
            pg = ctx.new_page()
            pg.goto(url)
            system[scheme] = pg.evaluate(bg)
            pg.locator(".theme-toggle").click()
            flipped = pg.evaluate(bg)
            pg.reload()
            if flipped == system[scheme] or pg.evaluate(bg) != flipped:
                problems.append(f"theme: on a {scheme} system the switch does not flip and stay flipped")
            ctx.close()
        if system["light"] == system["dark"]:
            problems.append("theme: with no choice made, the page ignores the system's light or dark setting")
        browser.close()
    return problems


def check_engines(tmp, claude, shots):
    """The Claude / Codex switch: shown only with two usable engines, remembered, sent with every question, and
    never leaving a stale choice or a dead page when Codex is unavailable."""
    problems = []
    os.environ["FAKE_CODEX_LOG"] = str(tmp / "codex.log")
    codex = fake_codex(tmp / "bin")
    calls = lambda: [l for l in (tmp / "codex.log").read_text().splitlines() if '"exec"' in l] if (tmp / "codex.log").exists() else []  # noqa: E731

    def served(name, claude_path, leak=""):
        ws = tmp / f"eng-{name}"
        ws.mkdir()
        build_workspace(ws)
        os.environ["FAKE_CODEX_LEAK"] = leak
        server = serve.make_server(ws, port=0, claude=claude_path, codex=codex)
        server.course.codex_ready()
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return ws, server, f"http://localhost:{server.server_address[1]}/lessons/0001-lesson.html"

    with sync_playwright() as p:
        browser = launch(p)
        for width_name, width in (("phone", 390), ("desktop", 1280)):
            ws, server, url = served(f"both-{width_name}", claude)
            try:
                (ws / "course.json").write_text(json.dumps({"engine": "codex"}))
                ctx = browser.new_context(viewport={"width": width, "height": 800})
                pg = ctx.new_page()
                pg.goto(url)
                pick = pg.locator(".ask-engine button")
                if pick.count() != 2:
                    problems.append(f"engines {width_name}: no Claude / Codex switch with both engines usable")
                    continue
                if pg.locator('.ask-engine button[aria-pressed="true"]').inner_text() != "Codex":
                    problems.append(f"engines {width_name}: the course default (Codex) is not selected")
                send_box, bar_box = pg.locator(".ask-send").bounding_box(), pg.locator(".ask-bar").bounding_box()
                box = pg.locator(".ask-bar textarea").bounding_box()
                last = pg.locator(".ask-engine button").last.bounding_box()
                if (send_box["x"] + send_box["width"] > width or box["width"] < 0.5 * bar_box["width"]
                        or last["x"] + last["width"] > send_box["x"] + 1):
                    problems.append(f"engines {width_name}: the switch squeezes the question box or clips the controls")
                before = len(calls())
                pg.locator(".ask-bar textarea").fill("What is the runner?")
                pg.locator(".ask-bar textarea").press("Enter")
                pg.locator(".ask-card .ask-meta", has_text="first words").last.wait_for(timeout=15000)
                meta = pg.locator(".ask-card .ask-meta").last.inner_text()
                if len(calls()) != before + 1 or "tokens" not in meta or "$" in meta:
                    problems.append(f"engines {width_name}: a Codex question did not reach Codex or shows a cost: {meta!r}")
                # Ask Claude, then switch to Codex for a follow-up in the same card.
                pg.locator('.ask-engine button[data-engine="claude"]').focus()
                pg.keyboard.press("Enter")
                pg.locator(".ask-bar textarea").fill("Who is the worker?")
                pg.locator(".ask-bar textarea").press("Enter")
                card = pg.locator(".ask-card").last
                card.locator(".ask-meta", has_text="first words").wait_for(timeout=15000)
                pg.locator('.ask-engine button[data-engine="codex"]').click()
                before = len(calls())
                card.locator(".ask-follow textarea").fill("And then?")
                card.locator(".ask-follow textarea").press("Enter")
                pg.wait_for_function("() => !document.querySelector('.ask-card.busy')", timeout=15000)
                if len(calls()) != before + 1:
                    problems.append(f"engines {width_name}: a follow-up after switching to Codex did not go to Codex")
                pg.locator('.ask-engine button[data-engine="claude"]').click()
                pg.reload()
                if pg.locator('.ask-engine button[aria-pressed="true"]').inner_text() != "Claude":
                    problems.append(f"engines {width_name}: the choice of Claude is not remembered over the course default")
                if shots:
                    pg.screenshot(path=str(shots / f"engines-{width_name}.png"))
                ctx.close()
            finally:
                server.shutdown()
                server.server_close()

        ws, server, url = served("unavailable", claude, leak="ask-read-outside")
        try:
            ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            ctx.add_init_script("localStorage.setItem('vt-engine', 'codex')")
            pg = ctx.new_page()
            pg.goto(url)
            note = pg.locator(".ask-engine-note")
            if pg.locator(".ask-engine").count() or not note.count() or "ask-read-outside" not in note.inner_text():
                problems.append("engines: an unavailable Codex still shows the switch or hides the reason")
            elif note.get_attribute("aria-live") != "polite":
                problems.append("engines: the reason line is not announced")
            before = len(calls())
            pg.locator(".ask-bar textarea").fill("Who answers?")
            pg.locator(".ask-bar textarea").press("Enter")
            pg.locator(".ask-card .ask-meta", has_text="first words").last.wait_for(timeout=15000)
            if len(calls()) != before:
                problems.append("engines: a stale remembered Codex choice still sent the question to Codex")
            ctx.close()
        finally:
            server.shutdown()
            server.server_close()

        ws, server, url = served("none", "", leak="ask-read-outside")
        try:
            ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            pg = ctx.new_page()
            pg.goto(url)
            if not pg.locator(".ask-bar textarea").is_disabled() or not pg.locator(".ask-engine-note").count():
                problems.append("engines: with no usable engine the ask bar is not disabled with a reason")
            if not pg.locator("main h1").is_visible():
                problems.append("engines: with no usable engine the lesson does not read")
            ctx.close()
        finally:
            server.shutdown()
            server.server_close()
        os.environ.pop("FAKE_CODEX_LEAK", None)
        browser.close()
    return problems


def check_teaching(base, course, shots):
    """Teach, beside the light/dark switch on every page, opens a panel that starts sessions, shows their progress
    and check, and offers a fix."""
    problems = []
    os.environ.pop("FAKE_TEXT", None)  # the default fake answer, not the hostile one this server started with
    with sync_playwright() as p:
        browser = launch(p)
        for name, width in (("phone", 390), ("desktop", 1280)):
            course.check = lambda *_: (True, "ok: 3 pages, 1 lessons")
            pg = browser.new_page(viewport={"width": width, "height": 900})
            pg.goto(f"{base}/")
            toggle = pg.locator(".top-bar .ask-teach-toggle")
            toggle.wait_for()
            if pg.evaluate("[...document.querySelector('.top-bar').children].map((c) => c.className).filter((c) => c !== 'ask-teach').join(' ')") != "ask-teach-toggle theme-toggle":
                problems.append(f"teaching ({name}): Teach is not beside the light/dark switch")
            if pg.locator("main .ask-teach").count():
                problems.append(f"teaching ({name}): a Teaching section is still in the page")
            if pg.locator(".ask-teach").is_visible():
                problems.append(f"teaching ({name}): the panel is open before Teach is pressed")
            toggle.click()
            labels = pg.locator(".ask-teach-actions button").all_inner_texts()
            if labels != ["Teach the next lesson", "Update lessons from my questions"]:
                problems.append(f"teaching ({name}): buttons are {labels}")
            box = pg.locator(".ask-teach").bounding_box()
            if box["x"] < 0 or box["x"] + box["width"] > width:
                problems.append(f"teaching ({name}): the panel runs off the screen")
            pg.locator(".ask-teach-actions button", has_text="Teach the next lesson").click()
            pg.locator(".ask-teach-summary", has_text="office manager").wait_for()
            pg.locator(".ask-teach-verdict.ok").wait_for()
            if not pg.locator(".ask-teach a", has_text="Reload").count():
                problems.append(f"teaching ({name}): no way to see the updated pages")
            course.check = lambda *_: (False, "0001-lesson.html: sentence over 25 words")
            pg.locator(".ask-teach-actions button", has_text="Update lessons").click()
            fix = pg.locator(".ask-teach button", has_text="Fix these")
            fix.wait_for()
            pg.locator(".ask-teach-check", has_text="sentence over 25 words").wait_for()
            course.check = lambda *_: (True, "ok")
            fix.click()
            pg.locator(".ask-teach-verdict.ok").wait_for()
            if pg.evaluate("document.documentElement.scrollWidth > window.innerWidth"):
                problems.append(f"teaching ({name}): page scrolls sideways")
            if shots:
                pg.screenshot(path=str(shots / f"teaching-{name}.png"))
            pg.keyboard.press("Escape")
            if pg.locator(".ask-teach").is_visible():
                problems.append(f"teaching ({name}): Escape does not close the panel")
            lesson_page = browser.new_page(viewport={"width": width, "height": 900})
            lesson_page.goto(f"{base}/lessons/0001-lesson.html")
            try:
                lesson_page.locator(".top-bar .ask-teach-toggle").wait_for(timeout=5000)
            except Exception:
                problems.append(f"teaching ({name}): a lesson page has no Teach button")
            lesson_page.goto(f"{base}/index.html#teach")
            try:
                lesson_page.locator(".ask-teach").wait_for(state="visible", timeout=5000)
            except Exception:
                problems.append(f"teaching ({name}): a link to #teach does not open the panel")
            lesson_page.goto(f"{base}/lessons/0001-lesson.html")
            lesson_page.locator(".ask-teach-toggle").wait_for()
            lesson_page.evaluate("location.hash = 'teach'")
            try:
                lesson_page.locator(".ask-teach").wait_for(state="visible", timeout=3000)
            except Exception:
                problems.append(f"teaching ({name}): going to #teach on an open page does not open the panel")
            lesson_page.close()
            # A failed refresh shows why, from its own output.
            (course.ws / "course.json").write_text(json.dumps({"refresh": "echo the copy is out of date; exit 1"}))
            refresh_page = browser.new_page(viewport={"width": width, "height": 900})
            refresh_page.goto(f"{base}/")
            refresh_page.locator(".ask-teach-toggle").click()
            refresh_page.locator(".ask-teach-actions button", has_text="Refresh the source copy").click()
            try:
                refresh_page.locator(".ask-teach", has_text="the copy is out of date").wait_for(timeout=10000)
            except Exception:
                problems.append(f"teaching ({name}): a failed refresh does not show its output")
            refresh_page.close()
            (course.ws / "course.json").unlink()
            other = browser.new_page(viewport={"width": width, "height": 900})
            other.goto(f"{base}/")
            other.locator(".ask-teach-toggle").click()
            os.environ["FAKE_CLAUDE_SLOW"] = "1"
            pg.evaluate("""fetch('/api/teach', {method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action: 'next'})})""")
            other.locator(".ask-teach-actions button", has_text="Teach the next lesson").click()
            try:
                other.locator(".ask-teach button", has_text="Stop").wait_for(timeout=5000)
            except Exception:
                problems.append(f"teaching ({name}): a second tab did not show the job already running")
            else:
                if "Teaching" not in other.locator(".ask-teach-toggle").inner_text():
                    problems.append(f"teaching ({name}): the Teach button does not show the running job")
                # Polling every two seconds must not rebuild an unchanged panel, which drops focus and closes folds.
                other.locator(".ask-teach button", has_text="Stop").focus()
                other.wait_for_timeout(2600)
                if other.evaluate("document.activeElement.textContent") != "Stop":
                    problems.append(f"teaching ({name}): the panel's focus is lost while a job runs")
                other.locator(".ask-teach button", has_text="Stop").click()
            os.environ.pop("FAKE_CLAUDE_SLOW", None)
            other.locator(".ask-teach-ended.stopped").wait_for(timeout=15000)
            other.close()
            pg.close()
        browser.close()
    return problems


def main():
    shots = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        bindir = tmp / "bin"
        bindir.mkdir()
        fake = bindir / "claude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        os.environ["FAKE_CLAUDE_LOG"] = str(tmp / "claude.log")
        for name, width in WIDTHS.items():
            ws = tmp / name
            ws.mkdir()
            build_workspace(ws)
            server = serve.make_server(ws, port=0, claude=str(fake), codex="")
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                problems += run(name, width, f"http://localhost:{server.server_address[1]}", shots)
            finally:
                server.shutdown()
                server.server_close()
        for name in SOURCE_WIDTHS:
            ws = tmp / f"src-{name}"
            ws.mkdir()
            build_workspace(ws)
            build_source(tmp / f"code-{name}")
            missed = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
            (ws / "quiz.jsonl").write_text(json.dumps({"t": missed, "lesson": "lessons/0001-lesson.html", "quiz": "q-old",
                                                       "type": "mcq", "q": "Which part does the work?", "right": False}) + "\n")
            server = serve.make_server(ws, port=0, code=tmp / f"code-{name}", claude=str(fake), codex="")
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                problems += check_sources(name, SOURCE_WIDTHS[name], f"http://localhost:{server.server_address[1]}", ws,
                                          tmp / "claude.log", shots)
            finally:
                server.shutdown()
                server.server_close()
        ws = tmp / "hostile"
        ws.mkdir()
        build_workspace(ws)
        os.environ["FAKE_TEXT"] = HOSTILE
        server = serve.make_server(ws, port=0, claude=str(fake), codex="")
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            problems += check_answers_are_inert(f"http://localhost:{server.server_address[1]}")
            problems += check_theme(f"http://localhost:{server.server_address[1]}")
            problems += check_teaching(f"http://localhost:{server.server_address[1]}", server.course, shots)
            problems += check_engines(tmp, str(fake), shots)
        finally:
            os.environ.pop("FAKE_TEXT", None)
            server.shutdown()
            server.server_close()
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print("ok: highlight, stream, follow-up, whole-page ask, reload and delete at", ", ".join(WIDTHS),
          "+ source panel, code actions, Check my answer and review at " + ", ".join(SOURCE_WIDTHS) + " + hostile answers render inert + theme switch + teaching from the page + engine switch")


if __name__ == "__main__":
    main()
