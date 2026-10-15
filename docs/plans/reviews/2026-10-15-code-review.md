---
reviewer: independent code review, read-only
date: 2026-10-15
reviewed: uncommitted working tree on 1f24715, after units U1 to U4 of docs/plans/2026-10-15-1315-feat-learning-tools-plan.md
---

# Code review: learning tools batch

All four findings were fixed the same day, each with a regression test in scripts/test_reader.py that failed first.

Four bugs found:

1. **Medium — stale source responses overwrite the current file.** [ask.js:543](../../../starter/assets/ask.js:543)  
   Open citation A, then B. If A responds last, B’s heading and lesson anchor remain above A’s contents. This can also detach an answer card inserted into B’s panel. Confirmed with an in-memory reproduction.  
   **Smallest fix:** track the current request and ignore stale success/error callbacks; invalidate it when closing.

2. **Medium — resizing hides a source-panel answer.** [ask.js:47](../../../starter/assets/ask.js:47)  
   Ask inside the panel at 1000px, then widen past 1180px. The breakpoint handler moves the answer into the lesson margin, which the open panel covers ([ask.css:191](../../../starter/assets/ask.css:191)).  
   **Smallest fix:** skip cards inside `.ask-panel` when relocating cards.

3. **Low — Connect loses its topic suggestions.** [ask.js:111](../../../starter/assets/ask.js:111)  
   The question control became a textarea, but Connect still assigns a datalist through `list`. Textareas do not support datalists, so existing topic suggestions disappear.  
   **Smallest fix:** retain an input for Connect.

4. **Low — printing after selecting Dark can hide code and model answers.** [style.css:186](../../../starter/assets/style.css:186)  
   The more specific dark-theme selector overrides print’s `color-scheme: light`. Print forces black text while code/model backgrounds remain nearly black; printing backgrounds makes them unreadable.  
   **Smallest fix:** include `:root[data-theme]` in the print selector.

No findings in source confinement, parent-repository ignore handling, size/encoding limits, LAN gating, quiz/review folding or due dates.

No findings in model/file HTML safety, non-HTTP links, Check-my-answer payloads, review links, or predict/self-mark/ID/score behavior.

No files changed. Syntax checks and focused in-memory probes passed.  
Full fixture-based suites were skipped under read-only restrictions; browser policy declined local-page access, so layout and print findings remain source-verified.
