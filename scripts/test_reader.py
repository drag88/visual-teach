"""Browser test for ask-while-reading: the starter lesson, served by serve.py, with a fake `claude`.

Usage: python3 test_reader.py [screenshot-dir]
Needs Python Playwright with Chromium. Costs nothing: the fake replays a canned answer.
"""

import os
import shutil
import stat
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import serve  # noqa: E402
from test_serve import FAKE_CLAUDE  # noqa: E402

STARTER = HERE.parent / "starter"
WIDTHS = {"desktop": 1280, "phone": 390}


def build_workspace(root):
    shutil.copytree(STARTER / "assets", root / "assets")
    (root / "lessons").mkdir()
    shutil.copy(STARTER / "lesson.html", root / "lessons/0001-lesson.html")
    shutil.copy(STARTER / "index.html", root / "index.html")
    (root / "NOTES.md").write_text("Analogy: the runner is the office manager.\n")


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
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": width, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        url = f"{base}/lessons/0001-lesson.html"
        pg.goto(url)
        pg.wait_for_selector("body.ask-on")
        para = "main > h2 + p"
        assert pg.locator("main > [data-p]").count() >= 5, "paragraphs are numbered"

        select_words(pg, para, "explains the diagram")
        pg.wait_for_selector(".ask-sel:not([hidden])")
        pg.locator(".ask-sel button", has_text="Explain").click()
        card = pg.locator(".ask-card").first
        card.locator(".ask-answer", has_text="office manager").first.wait_for()
        assert card.locator(".ask-pchip").count() == 1, "¶ citation became a chip"
        if width >= 1180:
            assert "in-margin" in card.get_attribute("class"), "card sits in the margin on wide screens"
        else:
            assert pg.evaluate(f"document.querySelector('{para}').nextElementSibling.classList.contains('ask-card')"), \
                "card sits under its paragraph on narrow screens"
        card.locator(".ask-meta", has_text="first words").wait_for()

        card.locator(".ask-follow input").fill("And who is the worker?")
        card.locator(".ask-follow button").click()
        pg.wait_for_function("document.querySelectorAll('.ask-card .ask-ex').length === 2")
        card.locator(".ask-ex").nth(1).locator(".ask-answer", has_text="office manager").wait_for()

        pg.locator(".ask-bar input").fill("What is this lesson about?")
        pg.locator(".ask-bar .ask-send").click()
        pg.wait_for_function("document.querySelectorAll('.ask-card').length === 2")
        whole = pg.locator(".ask-card", has=pg.locator(".ask-where", has_text="whole page"))
        whole.locator(".ask-answer", has_text="office manager").wait_for()
        assert pg.evaluate("document.querySelector('main footer').previousElementSibling.classList.contains('ask-card')"), \
            "whole-lesson card sits before the footer"

        if pg.evaluate("document.documentElement.scrollWidth > window.innerWidth"):
            problems.append(f"{width_name}: page scrolls sideways")
        if shots:
            pg.screenshot(path=str(shots / f"reader-{width_name}.png"), full_page=True)

        pg.reload()
        pg.wait_for_function("document.querySelectorAll('.ask-card').length === 2")
        restored = pg.locator(".ask-card", has=pg.locator(".ask-kind", has_text="Explain"))
        assert "folded" in restored.get_attribute("class"), "saved cards come back folded"
        assert restored.locator(".ask-ex").count() == 2, "the follow-up came back with its thread"
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


# Answers come from a model that may have read hostile text (a fetched page, a code comment), so they
# must render as text and plain links only, whatever they contain.
HOSTILE = "\n\n".join([
    "https://example.com/(https://x/onmouseover=window.pwned=1//",
    "[click](javascript:window.pwned=1) and [x](https://a.com/\"onmouseover=\"window.pwned=1)",
    "==<img src=x onerror=window.pwned=1>== and `<script>window.pwned=1</script>`",
    "**[a](https://b.com/(https://c.com/onmouseover=window.pwned=1//)**",
])


def check_answers_are_inert(base):
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        pg.goto(f"{base}/lessons/0001-lesson.html")
        pg.wait_for_selector("body.ask-on")
        pg.locator(".ask-bar input").fill("Anything")
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
            server = serve.make_server(ws, port=0, claude=str(fake))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                problems += run(name, width, f"http://localhost:{server.server_address[1]}", shots)
            finally:
                server.shutdown()
                server.server_close()
        ws = tmp / "hostile"
        ws.mkdir()
        build_workspace(ws)
        os.environ["FAKE_TEXT"] = HOSTILE
        server = serve.make_server(ws, port=0, claude=str(fake))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            problems += check_answers_are_inert(f"http://localhost:{server.server_address[1]}")
        finally:
            os.environ.pop("FAKE_TEXT", None)
            server.shutdown()
            server.server_close()
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print("ok: highlight, stream, follow-up, whole-page ask, reload and delete at", ", ".join(WIDTHS), "+ hostile answers render inert")


if __name__ == "__main__":
    main()
