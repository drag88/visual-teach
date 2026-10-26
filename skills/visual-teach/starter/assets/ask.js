// Ask while reading: highlight text in a lesson and get a live answer from Claude in a card beside it.
// Needs the course served by the skill's scripts/serve.py. Opened as a plain file, the lesson works as before.
(() => {
  const main = document.querySelector("main");
  if (!main) return;

  const SKIP = "nav, h1, h2, h3, .subtitle, .src, .score, .read, footer, script, .ask-card";
  const LABEL = { explain: "Explain", simpler: "Simpler", more: "More", walk: "Walk through", uses: "Where else",
    connect: "Connect", ask: "Ask", whole: "Ask", check: "Check" };
  // A citation: path:12 or path:12-20, as a lesson's .src line and inline code show it.
  const CITE = /^(\S+?):(\d+)(?:-(\d+))?$/;
  const BLOCK = "main > [data-p]"; // a lesson paragraph, numbered on load
  const lesson = decodeURIComponent(location.pathname.replace(/^\/+/, ""));
  const title = (document.querySelector("h1") || document.querySelector("title") || {}).textContent || "";
  const wide = matchMedia("(min-width: 1180px)");
  const narrow = matchMedia("(max-width: 720px), (pointer: coarse)");
  const cards = [];
  let mode = store("vt-mode") || "quick";
  let code = null; // the source folder answers may read, from ping

  const blocks = [...main.children].filter((el) => !el.matches(SKIP));
  blocks.forEach((el, i) => {
    el.dataset.p = i + 1;
    el.dataset.key = keyOf(el);
  });

  if (!/^https?:$/.test(location.protocol)) return hint();
  fetch("/api/ping")
    .then((r) => (r.ok ? r.json() : null))
    .then((info) => (info ? start(info) : hint()))
    .catch(hint);

  // Setup

  function start(info) {
    code = info.code || null;
    document.body.classList.add("ask-on");
    document.body.classList.toggle("ask-hidden", store("vt-answers") === "hidden");
    buildSelectionBar();
    buildAskBar();
    getJSON("/api/threads?lesson=" + encodeURIComponent(lesson))
      .then(({ threads }) => {
        threads.forEach(restore);
        layout();
        highlight();
      }).catch(() => {});
    wide.addEventListener("change", () => {
      cards.filter((c) => !c.closest(".ask-panel")).forEach((c) => place(c, c.block)); // panel answers stay put
      layout();
    });
    addEventListener("resize", scheduleLayout);
    document.addEventListener("click", (e) => {
      const chip = e.target.closest(".ask-pchip");
      if (!chip) return;
      e.preventDefault();
      if (chip.classList.contains("ask-src")) {
        const card = chip.closest(".ask-card");
        return openSource(chip.dataset.path, +chip.dataset.start, +chip.dataset.end, card ? card.block : null);
      }
      const target = main.querySelector(`[data-p="${chip.dataset.p}"]`);
      if (!target) return;
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      target.classList.remove("ask-flash");
      void target.offsetWidth;
      target.classList.add("ask-flash");
    });
    if (code) {
      for (const el of main.querySelectorAll(".src")) {
        const c = citeOf(el);
        if (!c) continue;
        // A link, not a button: a button never breaks across lines, which strands a "(" before it.
        const link = Object.assign(node("a", "ask-cite"), { href: "#", textContent: el.textContent.trim() });
        link.setAttribute("role", "button");
        link.addEventListener("click", (e) => {
          e.preventDefault();
          openSource(c.path, c.start, c.end, blockOf(el));
        });
        el.replaceChildren(link);
      }
    }
    document.addEventListener("quiz", onQuiz);
    if (/^\/(index\.html)?$/.test(location.pathname)) {
      showReview();
      showRecords();
    }
    showTeach();
  }

  let topicsLoaded = false;
  function loadTopics() {
    if (topicsLoaded) return;
    topicsLoaded = true;
    getJSON("/api/topics").then(({ topics }) => {
      const list = node("datalist");
      list.id = "ask-topics";
      for (const t of topics) list.append(Object.assign(node("option"), { value: t.title }));
      document.body.append(list);
    }).catch(() => { topicsLoaded = false; });
  }

  function hint() {
    const line = node("p", "ask-hint");
    line.textContent = "Open this course with visual-teach's open_course.py to ask questions as you read.";
    main.append(line);
  }

  // Highlight, then pick what to ask

  let pending = null;
  let selBar = null;

  function buildSelectionBar() {
    selBar = node("div", "ask-sel");
    selBar.hidden = true;
    for (const kind of ["explain", "simpler", "more", "walk", ...(code ? ["uses"] : []), "connect", "ask"]) {
      const b = node("button");
      b.type = "button";
      b.textContent = kind === "connect" || kind === "ask" ? LABEL[kind] + "…" : LABEL[kind];
      b.dataset.kind = kind;
      selBar.append(b);
    }
    const form = node("form", "ask-sel-form");
    form.hidden = true;
    const input = questionBox("Your question");
    // Connect picks from the course's topics, and only a one-line input can offer a list (datalist).
    const topic = node("input");
    topic.placeholder = "Connect to which topic?";
    topic.setAttribute("aria-label", topic.placeholder);
    topic.setAttribute("list", "ask-topics");
    const go = node("button");
    go.type = "submit";
    go.textContent = "Ask";
    form.append(input, topic, go);
    selBar.append(form);
    document.body.append(selBar);

    selBar.addEventListener("mousedown", (e) => {
      if (e.target.tagName === "BUTTON") e.preventDefault(); // keep the highlight while clicking
    });
    selBar.addEventListener("click", (e) => {
      const kind = e.target.dataset && e.target.dataset.kind;
      if (!kind || !pending) return;
      if (kind === "connect" || kind === "ask") {
        form.hidden = false;
        form.dataset.kind = kind;
        const connect = kind === "connect";
        input.hidden = connect;
        topic.hidden = !connect;
        input.value = topic.value = "";
        input.style.height = "";
        if (connect) loadTopics();
        (connect ? topic : input).focus();
        return;
      }
      submit(kind);
    });
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const text = (form.dataset.kind === "connect" ? topic : input).value.trim();
      if (!text || !pending) return;
      submit(form.dataset.kind, text);
    });
    document.addEventListener("selectionchange", debounce(onSelection, 150));
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      if (!selBar.hidden) hideSelectionBar();
      else if (panel && panel.open) panel.close();
    });
  }

  function onSelection() {
    if (selBar.contains(document.activeElement)) return;
    const sel = getSelection();
    if (!sel.rangeCount || sel.isCollapsed) return hideSelectionBar();
    const range = sel.getRangeAt(0);
    const start = range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentElement;
    const text = sel.toString().replace(/\s+/g, " ").trim();
    if (!start || !text || text.length > 2000 || start.closest(".ask-card")) return hideSelectionBar();
    if (start.closest(".ask-lines")) {
      // In the source panel: the card goes to the lesson block that opened it.
      pending = { block: panel.block, text, quote: null, range: range.cloneRange(), code: true, source: panelSource(range),
        inPanel: true };
      return showSelectionBar(range);
    }
    const block = start.closest(BLOCK);
    if (!block) return hideSelectionBar();
    const pre = start.closest("pre");
    pending = { block, text, quote: quoteOf(block, range, text), range: range.cloneRange(), code: Boolean(pre),
      source: pre ? citeOf(pre.nextElementSibling) : null };
    showSelectionBar(range);
  }

  function showSelectionBar(range) {
    selBar.querySelector(".ask-sel-form").hidden = true;
    selBar.querySelector('[data-kind="walk"]').hidden = !pending.code;
    selBar.hidden = false;
    selBar.classList.toggle("docked", narrow.matches);
    if (narrow.matches) {
      selBar.style.top = selBar.style.left = "";
      return;
    }
    const r = range.getBoundingClientRect();
    let top = r.top + scrollY - selBar.offsetHeight - 10;
    if (top < scrollY + 8) top = r.bottom + scrollY + 10;
    const left = Math.min(Math.max(r.left + scrollX + r.width / 2 - selBar.offsetWidth / 2, 8),
      scrollX + innerWidth - selBar.offsetWidth - 8);
    selBar.style.top = top + "px";
    selBar.style.left = left + "px";
  }

  function hideSelectionBar() {
    if (selBar) selBar.hidden = true;
  }

  function submit(kind, text) {
    const { block, text: selection, quote, range, source, inPanel } = pending;
    hideSelectionBar();
    setHidden(false);
    getSelection().removeAllRanges();
    const card = makeCard({ kind, selection, block });
    card.range = range;
    highlight();
    place(card, block);
    // Asked in the source panel: the answer sits under those lines while the panel is open, since the
    // panel covers the margin where cards usually go. releaseCards() puts it back beside the lesson.
    const row = inPanel && source && panel.lines.querySelector(`.ask-line[data-n="${source.end}"]`);
    if (row) {
      card.classList.remove("in-margin");
      row.after(card);
    }
    layout();
    send(card, {
      kind, mode, lesson, lesson_title: title, selection, source,
      para: paraOf(block, quote),
      para_text: block ? clip(clean(block.innerText), 1500) : null,
      question: kind === "ask" ? text : null,
      topic: kind === "connect" ? text : null,
      lesson_text: lessonText(),
    }, kind === "ask" ? text : kind === "connect" ? "Connect to " + text : null);
  }

  // Ask about the whole lesson

  function buildAskBar() {
    const bar = node("form", "ask-bar");
    const input = questionBox("Ask about this page");
    const key = node("span", "ask-key");
    key.textContent = "/";
    const modes = node("div", "ask-mode");
    modes.setAttribute("role", "group");
    modes.setAttribute("aria-label", "Answer depth");
    for (const m of ["quick", "deep"]) {
      const b = node("button");
      b.type = "button";
      b.dataset.mode = m;
      b.textContent = m === "quick" ? "Quick" : "Deep";
      b.setAttribute("aria-pressed", String(m === mode));
      b.addEventListener("click", () => {
        mode = m;
        store("vt-mode", m);
        modes.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.mode === m)));
      });
      modes.append(b);
    }
    showBtn = button("", () => setHidden(!document.body.classList.contains("ask-hidden")));
    showBtn.className = "ask-show";
    updateShow();
    const sendBtn = node("button", "ask-send");
    sendBtn.type = "submit";
    sendBtn.textContent = "↑";
    sendBtn.setAttribute("aria-label", "Send");
    bar.append(input, key, showBtn, modes, sendBtn);
    document.body.append(bar);
    bar.addEventListener("submit", (e) => {
      e.preventDefault();
      const q = input.value.trim();
      if (!q) return;
      input.value = "";
      input.style.height = "";
      setHidden(false);
      // Answer beside the paragraph being read, so the learner keeps their place.
      const block = readingBlock();
      const card = makeCard({ kind: "whole", block });
      place(card, block);
      layout();
      card.scrollIntoView({ behavior: "smooth", block: "nearest" });
      send(card, {
        kind: "whole", mode, lesson, lesson_title: title, question: q, lesson_text: lessonText(),
        para: paraOf(block),
      }, q);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key !== "/" || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable) return;
      e.preventDefault();
      input.focus();
    });
  }

  // One switch shows or hides every answer. Hidden is plain reading: no cards or marks, and the text back
  // in the centre. Asking anything shows them again.
  let showBtn = null;
  function setHidden(hidden) {
    document.body.classList.toggle("ask-hidden", hidden);
    store("vt-answers", hidden ? "hidden" : "shown");
    updateShow();
    highlight();
    layout();
  }

  function updateShow() {
    if (!showBtn) return;
    showBtn.hidden = !cards.length;
    showBtn.textContent = document.body.classList.contains("ask-hidden") ? `Show answers (${cards.length})` : "Hide answers";
  }

  // The paragraph being read: the first one that reaches below the top quarter of the screen.
  function readingBlock() {
    return blocks.find((b) => b.getBoundingClientRect().bottom > innerHeight / 4) || blocks[blocks.length - 1] || null;
  }

  // Question boxes grow with the question, so a long dictated one stays in view. Enter sends; Shift+Enter is a new line.
  function questionBox(label) {
    const box = node("textarea");
    box.rows = 1;
    box.placeholder = label;
    box.setAttribute("aria-label", label);
    box.addEventListener("input", () => {
      box.style.height = "auto";
      box.style.height = box.scrollHeight + "px";
    });
    box.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
      e.preventDefault();
      box.form.requestSubmit();
    });
    return box;
  }

  // Cards

  function makeCard({ kind, selection, block, thread = null }) {
    const card = node("aside", "ask-card");
    const head = node("div", "ask-head");
    const label = node("span", "ask-kind");
    label.textContent = LABEL[kind];
    const where = node("span", "ask-where");
    where.textContent = block ? "¶" + block.dataset.p : "whole page";
    const quote = node("span", "ask-quote");
    quote.textContent = selection ? "“" + clip(selection, 60) + "”" : "";
    const toggle = node("button", "ask-toggle");
    toggle.type = "button";
    toggle.setAttribute("aria-label", "Fold or unfold");
    toggle.textContent = "–";
    toggle.addEventListener("click", () => {
      setFolded(card, !card.classList.contains("folded"));
      layout();
    });
    head.append(label, where, quote, toggle);
    const log = node("div", "ask-log");
    const foot = node("div", "ask-foot");
    const meta = node("span", "ask-meta");
    foot.append(meta, button("Copy", () => copy(card)), button("Retry", () => retry(card)), button("Delete", () => remove(card)));
    const follow = node("form", "ask-follow");
    const input = questionBox("Ask a follow-up");
    const go = node("button");
    go.type = "submit";
    go.textContent = "↑";
    go.setAttribute("aria-label", "Send follow-up");
    follow.append(input, go);
    follow.addEventListener("submit", (e) => {
      e.preventDefault();
      const q = input.value.trim();
      if (!q || !card.thread) return;
      input.value = "";
      input.style.height = "";
      send(card, { thread: card.thread, kind: "ask", mode, lesson, question: q }, q);
    });
    card.append(head, log, foot, follow);
    Object.assign(card, { log, meta, block, followUp: [input, go] });
    setThread(card, thread);
    cards.push(card);
    updateShow();
    return card;
  }

  // A follow-up continues the thread the first answer opened, so the box waits until there is one.
  function setThread(card, thread) {
    card.thread = thread;
    card.followUp.forEach((el) => { el.disabled = !thread; });
  }

  function post(path, body, signal) {
    return fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
  }

  function getJSON(path) {
    return fetch(path).then((r) => r.json());
  }

  // The paragraph a question is about, as the server logs it and a reload finds it again.
  function paraOf(block, quote = null) {
    return block ? { n: +block.dataset.p, key: block.dataset.key, quote } : null;
  }

  function exchange(card, question) {
    const ex = node("div", "ask-ex");
    if (question) {
      const q = node("p", "ask-q");
      q.textContent = question;
      ex.append(q);
    }
    ex.status = node("p", "ask-status");
    ex.answer = node("div", "ask-answer");
    ex.append(ex.status, ex.answer);
    card.log.append(ex);
    return ex;
  }

  async function send(card, body, question) {
    card.lastBody = body;
    card.lastQuestion = question;
    const ex = exchange(card, question);
    ex.status.textContent = "Thinking…";
    ex.text = "";
    card.controller = new AbortController();
    card.classList.add("busy");
    try {
      const res = await post("/api/ask", body, card.controller.signal);
      if (!res.ok || !res.body) throw new Error("the server answered " + res.status);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let cut;
        while ((cut = buf.indexOf("\n\n")) >= 0) {
          handle(card, ex, buf.slice(0, cut));
          buf = buf.slice(cut + 2);
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") fail(ex, err.message);
    } finally {
      card.classList.remove("busy");
      layout();
    }
  }

  function handle(card, ex, chunk) {
    let event = "", data = "";
    for (const line of chunk.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice(7);
      else if (line.startsWith("data: ")) data += line.slice(6);
    }
    let d;
    try { d = JSON.parse(data); } catch { return; }
    if (event === "thread") setThread(card, d.thread);
    else if (event === "status") ex.status.textContent = d.text + "…";
    else if (event === "delta") {
      ex.text += d.text;
      ex.status.textContent = "";
      if (!ex.frame) ex.frame = requestAnimationFrame(() => render(ex));
    } else if (event === "done") {
      render(ex);
      ex.status.remove();
      card.meta.textContent = metaLine(d);
    } else if (event === "error") fail(ex, d.message);
  }

  function render(ex) {
    cancelAnimationFrame(ex.frame);
    ex.frame = 0;
    ex.answer.innerHTML = md(ex.text);
    layout();
  }

  function fail(ex, message) {
    ex.status.className = "ask-status ask-error";
    ex.status.textContent = "No answer: " + message;
  }

  function retry(card) {
    if (!card.lastBody) return;
    const last = card.log.lastElementChild;
    if (last) last.remove();
    const body = { ...card.lastBody };
    if (!body.thread && card.thread) {
      // Retrying the first question: drop the unanswered thread and start it again.
      post("/api/delete", { thread: card.thread }).catch(() => {});
      setThread(card, null);
    }
    send(card, body, card.lastQuestion);
  }

  function remove(card) {
    if (card.controller) card.controller.abort();
    if (card.thread) post("/api/delete", { thread: card.thread }).catch(() => {});
    cards.splice(cards.indexOf(card), 1);
    card.remove();
    updateShow();
    if (card.block && !cards.some((c) => c.block === card.block)) card.block.classList.remove("has-ask");
    highlight();
    layout();
  }

  function copy(card) {
    const text = [...card.log.querySelectorAll(".ask-answer")].map((a) => a.innerText).join("\n\n");
    if (navigator.clipboard && isSecureContext) return navigator.clipboard.writeText(text);
    const area = Object.assign(node("textarea"), { value: text });
    document.body.append(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }

  function restore(t) {
    const block = findBlock(t.anchor);
    const card = makeCard({ kind: t.kind, selection: t.selection, block, thread: t.thread });
    let ex = null;
    for (const m of t.messages) {
      if (m.role === "user") {
        const asked = ["ask", "whole", "connect", "check"].includes(t.kind) || ex;
        // The log keeps the task Claude was given; the learner asked to connect to a topic.
        const text = !ex && t.kind === "connect" && t.topic ? "Connect to " + t.topic : m.text;
        ex = exchange(card, asked ? text : null);
        ex.status.remove();
        ex.answered = false;
      } else if (m.role === "assistant" && ex) {
        ex.answer.innerHTML = md(m.text || "");
        ex.answered = true;
        card.meta.textContent = metaLine(m);
      }
    }
    // The reader left, the server stopped or the run failed before an answer was saved.
    const unanswered = ex && !ex.answered;
    if (unanswered) ex.answer.append(Object.assign(node("p", "ask-status"), { textContent: "No answer was saved for this. Ask it again below." }));
    if (t.anchor && !block) {
      const moved = node("p", "ask-status");
      moved.textContent = "The passage this was about has moved or changed.";
      card.log.prepend(moved);
    }
    if (block && t.anchor && t.anchor.quote) card.range = findRange(block, t.anchor.quote.exact);
    setFolded(card, !unanswered);
    place(card, block);
  }

  function setFolded(card, folded) {
    card.classList.toggle("folded", folded);
    card.querySelector(".ask-toggle").textContent = folded ? "+" : "–";
  }

  // Source panel: the cited file with numbered lines, beside the lesson (a bottom sheet on a phone).

  let panel = null;
  const REFUSED = { 413: "This file is too large to show.", 415: "This file is not plain text." };

  function openSource(path, from, to, block) {
    if (!panel) {
      panel = node("dialog", "ask-panel");
      panel.setAttribute("aria-label", "Source");
      const head = node("div", "ask-panel-head");
      head.append(node("span", "ask-panel-path"), button("Close", () => panel.close()));
      panel.lines = node("div", "ask-lines");
      panel.append(head, panel.lines);
      panel.addEventListener("close", () => {
        panel.req = null;
        document.body.classList.remove("ask-panel-open");
        releaseCards();
      });
      document.body.append(panel);
    }
    releaseCards();
    Object.assign(panel, { block, path });
    panel.querySelector(".ask-panel-path").textContent = `${path}:${from}${to > from ? "-" + to : ""}`;
    panel.lines.replaceChildren(note("Loading…"));
    panel.show();
    document.body.classList.add("ask-panel-open");
    // As a bottom sheet the panel covers the lower part of the screen, so lift the cited passage above it.
    if (!wide.matches && block) block.scrollIntoView({ behavior: "smooth", block: "start" });
    const req = (panel.req = {}); // a reply for a file opened earlier, or after closing, is dropped
    fetch("/api/source?path=" + encodeURIComponent(path))
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d) => {
        if (panel.req !== req) return;
        panel.path = d.path;
        const rows = document.createDocumentFragment();
        d.text.replace(/\r?\n$/, "").split(/\r?\n/).forEach((t, i) => {
          const row = node("div", "ask-line");
          row.dataset.n = i + 1;
          row.textContent = t;
          if (i + 1 >= from && i + 1 <= to) row.classList.add("cited");
          rows.append(row);
        });
        panel.lines.replaceChildren(rows);
        const first = panel.lines.children[from - 1];
        if (first) panel.lines.scrollTop = first.offsetTop - panel.lines.clientHeight / 3;
      })
      // A refused or missing file gets one plain line, never its content.
      .catch((status) => {
        if (panel.req === req) panel.lines.replaceChildren(note(REFUSED[status] || "This file is not in the source folder, or is private."));
      });
  }

  function releaseCards() {
    const held = [...panel.querySelectorAll(".ask-card")];
    held.forEach((c) => place(c, c.block));
    if (held.length) layout();
  }

  function note(text) {
    const p = node("p", "ask-panel-note");
    p.textContent = text;
    return p;
  }

  // The lines a panel selection covers. A triple-click ends at the start of the next line.
  function panelSource(range) {
    const row = (n) => (n.nodeType === 1 ? n : n.parentElement).closest(".ask-line");
    const a = row(range.startContainer);
    let b = row(range.endContainer);
    if (a && b && b !== a && range.endOffset === 0) b = b.previousElementSibling;
    return a && b ? { path: panel.path, start: +a.dataset.n, end: +b.dataset.n } : null;
  }

  function citeOf(el) {
    const m = el && el.matches(".src") && CITE.exec(el.textContent.trim());
    return m ? { path: m[1], start: +m[2], end: +(m[3] || m[2]) } : null;
  }

  // A code block's source line belongs to the code above it.
  function blockOf(el) {
    let b = el.closest(BLOCK) || el;
    while (b && !b.matches(BLOCK)) b = b.previousElementSibling;
    return b;
  }

  // Quizzes: results feed spaced review; a revealed recall answer can be marked by Claude.

  function onQuiz(e) {
    const d = e.detail || {};
    const quiz = e.target.closest(".quiz") || e.target;
    if (d.event === "answered") {
      post("/api/quiz", { lesson, quiz: d.quiz, type: d.type, q: d.q, right: d.right }).catch(() => {});
    } else if (d.event === "revealed" && (d.answer || "").trim()) {
      const old = quiz.querySelector(".ask-check");
      if (old) old.remove();
      const b = button("Check my answer", () => {
        b.remove();
        checkAnswer(quiz, d);
      });
      b.className = "act ask-check";
      quiz.append(b);
    }
  }

  function checkAnswer(quiz, d) {
    const block = quiz.closest(BLOCK);
    setHidden(false);
    const card = makeCard({ kind: "check", block });
    place(card, block);
    layout();
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    send(card, {
      kind: "check", mode, lesson, lesson_title: title, quiz: d.quiz, question: d.q, answer: d.answer, model: d.model,
      para: paraOf(block), lesson_text: lessonText(),
    }, d.answer);
  }

  function showReview() {
    const lists = main.querySelectorAll("ol.syllabus");
    if (!lists.length) return;
    getJSON("/api/review").then(({ due, waiting }) => {
      const list = node("ul", "ask-review");
      for (const item of due || []) {
        const url = new URL(item.href, location.href);
        if (url.origin !== location.origin) continue;
        const a = node("a");
        a.href = url.href;
        a.textContent = item.q || item.quiz;
        const li = node("li");
        li.append(a);
        list.append(li);
      }
      if (!list.children.length && !waiting) return;
      const head = node("h2");
      head.textContent = "Review";
      const parts = [head, ...(list.children.length ? [list] : [])];
      if (waiting) {
        const later = node("p", "ask-review-later");
        later.textContent = `${waiting} missed question${waiting === 1 ? "" : "s"} will come back here for review.`;
        parts.push(later);
      }
      lists[lists.length - 1].after(...parts);
    }).catch(() => {});
  }

  // Learning records: what the learner has shown, listed on the course home page, each with a Delete for one that is
  // wrong. The server moves the file to .deleted/, so it can be put back by hand.
  function showRecords() {
    getJSON("/api/records").then(({ records }) => {
      if (!records || !records.length) return;
      const head = node("h2");
      head.textContent = "What you have shown";
      const list = node("ul", "ask-records");
      for (const r of records) {
        const li = node("li");
        const name = node("span");
        name.textContent = r.title + (r.superseded ? " (superseded)" : "");
        const del = button("Delete", () => {
          if (!confirm(`Delete the learning record "${r.title}"?`)) return;
          post("/api/records/delete", { name: r.name }).then((res) => {
            if (!res.ok) return;
            li.remove();
            if (!list.children.length) { head.remove(); list.remove(); }
          }).catch(() => {});
        });
        li.append(name, " ", del);
        list.append(li);
      }
      main.append(head, list);
    }).catch(() => {});
  }

  // Teaching: a Teach button beside the light/dark switch, on every page of the computer running the server, opens a
  // small panel to start a session, follow it and see the course check. The job runs on the server, so it carries
  // on if the page closes; an open page checks on it every two seconds while it runs.

  const TEACH_LABEL = {
    next: "Teach the next lesson", update: "Update lessons from my questions",
    refresh: "Refresh the source copy", fix: "Fix the check problems",
  };
  const TEACH_DOING = {
    next: "Writing the next lesson", update: "Updating lessons from your questions",
    refresh: "Refreshing the source copy", fix: "Fixing the check problems",
  };
  const TEACH_ENDED = { done: "Done", stopped: "Stopped", failed: "Failed" };
  let teachTimer = 0;
  let teach = null; // { toggle, panel, refresh }

  function showTeach() {
    getJSON("/api/teach").then((info) => {
      if (!info.allowed) return;
      const toggle = node("button", "ask-teach-toggle");
      toggle.type = "button";
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-controls", "teach");
      const panel = node("section", "ask-teach");
      Object.assign(panel, { id: "teach", hidden: true, tabIndex: -1 });
      panel.setAttribute("aria-label", "Teaching");
      teach = { toggle, panel, refresh: info.refresh };
      toggle.addEventListener("click", () => setTeachOpen(panel.hidden));
      document.addEventListener("click", (e) => {
        if (!panel.hidden && !panel.contains(e.target) && !toggle.contains(e.target)) setTeachOpen(false);
      });
      document.addEventListener("keydown", (e) => {
        if (e.key !== "Escape" || panel.hidden) return;
        setTeachOpen(false);
        toggle.focus();
      });
      const bar = topBar();
      bar.prepend(toggle); // left of the light/dark switch
      bar.append(panel);
      renderTeach(info.job);
      const fromHash = () => { if (location.hash === "#teach") setTeachOpen(true); };
      fromHash();
      addEventListener("hashchange", fromHash);
    }).catch(() => {});
  }

  // The row at the top right that theme.js also puts its switch in, whichever script gets there first.
  function topBar() {
    let bar = document.querySelector(".top-bar");
    if (!bar) {
      bar = node("div", "top-bar");
      document.body.prepend(bar);
    }
    return bar;
  }

  function setTeachOpen(open) {
    teach.panel.hidden = !open;
    teach.toggle.setAttribute("aria-expanded", String(open));
    if (open) teach.panel.focus();
  }

  function startTeach(action) {
    post("/api/teach", { action })
      .then((r) => r.json().catch(() => ({})).then((d) => (r.ok ? d : Promise.reject(new Error(d.error || "the server answered " + r.status)))))
      .then(({ job }) => renderTeach(job))
      .catch(async (err) => {
        try {
          renderTeach((await getJSON("/api/teach")).job);
        } catch (_) { /* Keep the start error visible if the status request also fails. */ }
        teach.panel.prepend(Object.assign(node("p", "ask-error"), { textContent: "Could not start: " + err.message }));
      });
  }

  function pollTeach() {
    clearTimeout(teachTimer);
    getJSON("/api/teach").then(({ job }) => renderTeach(job))
      .catch(() => { teachTimer = setTimeout(pollTeach, 4000); });
  }

  function minutes(since) {
    const m = Math.round((Date.now() - new Date(since)) / 60000);
    return m >= 1 ? `${m} min` : "just now";
  }

  function textLine(cls, text) {
    return Object.assign(node("p", cls), { textContent: text });
  }

  function renderTeach(job) {
    const { toggle, panel } = teach;
    const running = Boolean(job && job.state === "running");
    clearTimeout(teachTimer); // a start from this page renders without pollTeach, so one may be waiting
    if (running) teachTimer = setTimeout(pollTeach, 2000);
    toggle.classList.toggle("running", running);
    toggle.textContent = running ? `Teaching · ${minutes(job.started)}` : "Teach";
    // Rebuild only when something shown has changed: rebuilding on every poll would drop the learner's focus and
    // close Earlier steps while they read it.
    const shown = JSON.stringify([job, running && minutes(job.started), teach.refresh]);
    if (shown === teach.shown) return;
    teach.shown = shown;
    // The control the learner was on (Stop, say), found again by its label after the rebuild.
    const focused = panel.contains(document.activeElement) ? document.activeElement.textContent : null;
    panel.replaceChildren(textLine("ask-teach-title", "Teaching"));
    if (running) {
      const now = node("p", "ask-teach-now");
      now.append(Object.assign(node("span", "ask-teach-live"), { textContent: TEACH_DOING[job.action] }),
        Object.assign(node("span", "ask-teach-time"), { textContent: minutes(job.started) }));
      panel.append(now, textLine("ask-teach-step", job.lines.length ? job.lines[job.lines.length - 1] : "Starting…"));
      if (job.lines.length > 1) {
        const log = node("details", "ask-teach-log");
        log.open = Boolean(teach.logOpen);
        log.addEventListener("toggle", () => { teach.logOpen = log.open; });
        const list = node("ol");
        for (const text of job.lines.slice(-8, -1).reverse()) list.append(Object.assign(node("li"), { textContent: text }));
        log.append(Object.assign(node("summary"), { textContent: "Earlier steps" }), list);
        panel.append(log);
      }
      const stop = button("Stop", () => post("/api/teach/stop", {}).then(pollTeach).catch(() => {}));
      stop.className = "ask-teach-stop";
      panel.append(stop);
      refocus(focused);
      return;
    }
    if (job) {
      const ended = node("p", "ask-teach-now");
      ended.append(Object.assign(node("span", `ask-teach-ended ${job.state}`), { textContent: `${TEACH_LABEL[job.action]}: ${TEACH_ENDED[job.state] || job.state}` }),
        Object.assign(node("span", "ask-teach-time"), { textContent: job.cost_usd != null ? `≈$${Number(job.cost_usd).toFixed(2)}` : "" }));
      panel.append(ended);
      if (job.summary.trim()) {
        const summary = node("div", "ask-teach-summary");
        summary.innerHTML = md(job.summary.trim());
        panel.append(summary);
      }
      if (job.error) panel.append(textLine("ask-error", job.error));
      // A refresh's output is its result, and a failed job's last lines say where it stopped.
      if (job.lines.length && (job.action === "refresh" || job.state === "failed")) {
        panel.append(Object.assign(node("pre", "ask-teach-check"), { textContent: job.lines.slice(-5).join("\n") }));
      }
      if (job.check) {
        const passed = job.check.ok === true;
        panel.append(textLine(`ask-teach-verdict ${passed ? "ok" : "no"}`, passed ? "The course check passed."
          : job.check.ok === false ? "The course check found problems:" : "The course check did not run."));
        if (!passed) panel.append(Object.assign(node("pre", "ask-teach-check"), { textContent: job.check.text }));
      }
      const after = node("p", "ask-teach-after");
      if (job.check && job.check.ok === false) after.append(button("Ask Claude to fix these", () => startTeach("fix")));
      if (job.state === "done") after.append(Object.assign(node("a"), { href: location.href.split("#")[0], textContent: "Reload to see the changes" }));
      if (after.children.length) panel.append(after);
    } else {
      panel.append(textLine("ask-teach-note", "Runs a session with Claude (Opus) in this course's folder. "
        + "It takes 5 to 15 minutes and carries on if you close the page."));
    }
    const actions = node("div", "ask-teach-actions");
    for (const action of ["next", "update", ...(teach.refresh ? ["refresh"] : [])]) {
      actions.append(button(TEACH_LABEL[action], () => startTeach(action)));
    }
    panel.append(actions);
    refocus(focused);
  }

  function refocus(label) {
    if (label === null) return;
    const again = [...teach.panel.querySelectorAll("button, summary, a")].find((el) => el.textContent === label);
    (again || teach.panel).focus();
  }

  // Where cards go: the right margin on wide screens, under the paragraph otherwise.

  function place(card, block) {
    card.block = block;
    if (block) block.classList.add("has-ask");
    const inMargin = Boolean(block && wide.matches);
    card.classList.toggle("in-margin", inMargin);
    if (inMargin) main.append(card);
    else if (block) {
      let after = block;
      // Past earlier cards, and past a code block's source line so the two stay together.
      while (after.nextElementSibling && after.nextElementSibling.matches(".ask-card, .src")) after = after.nextElementSibling;
      after.after(card);
    } else {
      const footer = main.querySelector("footer");
      if (footer) footer.before(card);
      else main.append(card);
    }
  }

  let frame = 0;
  function scheduleLayout() {
    if (!frame) frame = requestAnimationFrame(() => { frame = 0; layout(); });
  }

  function layout() {
    let y = 0;
    const margin = cards.filter((c) => c.classList.contains("in-margin"))
      .sort((a, b) => a.block.offsetTop - b.block.offsetTop);
    for (const c of margin) {
      const top = Math.max(c.block.offsetTop, y);
      c.style.top = top + "px";
      y = top + c.offsetHeight + 12;
    }
    main.style.minHeight = margin.length ? y + "px" : "";
  }

  // Finding passages again after a reload

  function findBlock(anchor) {
    if (!anchor) return null;
    const byKey = anchor.key && main.querySelector(`main > [data-key="${CSS.escape(anchor.key)}"]`);
    if (byKey) return byKey;
    const exact = anchor.quote && anchor.quote.exact;
    return (exact && blocks.find((b) => clean(b.textContent).includes(exact))) || null;
  }

  function findRange(block, exact) {
    if (!exact) return null;
    const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      const i = n.data.indexOf(exact);
      if (i >= 0) {
        const r = document.createRange();
        r.setStart(n, i);
        r.setEnd(n, i + exact.length);
        return r;
      }
    }
    return null;
  }

  function highlight() {
    if (!window.CSS || !CSS.highlights || typeof Highlight === "undefined") return;
    const ranges = document.body.classList.contains("ask-hidden") ? [] : cards.map((c) => c.range).filter(Boolean);
    CSS.highlights.set("asked", new Highlight(...ranges));
  }

  function quoteOf(block, range, exact) {
    const before = document.createRange();
    before.selectNodeContents(block);
    before.setEnd(range.startContainer, range.startOffset);
    const after = document.createRange();
    after.selectNodeContents(block);
    after.setStart(range.endContainer, range.endOffset);
    return { exact, prefix: clean(before.toString()).slice(-32), suffix: clean(after.toString()).slice(0, 32) };
  }

  // Text helpers

  let lessonCache = null;
  function lessonText() {
    if (lessonCache === null) {
      lessonCache = blocks.map((b) => `¶${b.dataset.p} ${clip(clean(b.innerText), 700)}`).join("\n").slice(0, 24000);
    }
    return lessonCache;
  }

  function md(src) {
    let out = "";
    src.split(/```[\w-]*\n?/).forEach((part, i) => {
      if (i % 2) {
        out += `<pre><code>${esc(part.replace(/\n$/, ""))}</code></pre>`;
        return;
      }
      for (const para of part.split(/\n{2,}/)) {
        const p = para.trim();
        if (!p) continue;
        const lines = p.split("\n");
        if (lines.every((l) => /^\s*([-*]|\d+\.)\s+/.test(l))) {
          const tag = /^\s*\d+\./.test(lines[0]) ? "ol" : "ul";
          out += `<${tag}>` + lines.map((l) => `<li>${inline(l.replace(/^\s*([-*]|\d+\.)\s+/, ""))}</li>`).join("") + `</${tag}>`;
        } else {
          const cls = /^Outside the text:/i.test(p) ? ' class="ask-outside"' : "";
          out += `<p${cls}>${inline(p).replace(/\n/g, "<br>")}</p>`;
        }
      }
    });
    return out;
  }

  function inline(s) {
    // Code, links and bare URLs become finished HTML first and are held aside, so no later pattern
    // can run inside a tag this function built. Model text is untrusted: it may quote hostile pages.
    const kept = [];
    const hold = (html) => `\u0000${kept.push(html) - 1}\u0000`;
    const link = (href, text) => hold(`<a href="${esc(href)}" target="_blank" rel="noopener">${esc(text)}</a>`);
    // path:line[-line] opens the source panel. A path has a dot or a slash, so 10:30 stays a time.
    const cite = (m, p, a, b) => code && /[./]/.test(p)
      ? hold(`<a class="ask-pchip ask-src" href="#" data-path="${esc(p)}" data-start="${a}" data-end="${b || a}">${esc(m)}</a>`)
      : null;
    s = s.replace(/\u0000/g, "")
      .replace(/`([^`]+)`/g, (_, c) => {
        const m = /^([\w./-]*[\w-]):(\d+)(?:-(\d+))?$/.exec(c);
        return (m && cite(...m)) || hold(`<code>${esc(c)}</code>`);
      })
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s()<>"']+)\)/g, (_, t, u) => link(u, t))
      .replace(/https?:\/\/[^\s()<>"'`]+/g, (u) => link(u, u))
      .replace(/(?<![\w./-])([\w./-]*[\w-]):(\d+)(?:-(\d+))?(?![\w:])/g, (...m) => cite(...m) || m[0]);
    s = esc(s)
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/==([^=]+)==/g, "<mark>$1</mark>")
      .replace(/¶(\d+)/g, '<a class="ask-pchip" href="#" data-p="$1">¶$1</a>');
    return s.replace(/\u0000(\d+)\u0000/g, (_, i) => kept[+i]);
  }

  function metaLine(d) {
    const parts = [];
    const m = /claude-([a-z]+)-(\d+)-(\d+)/.exec(d.model || "");
    if (m) parts.push(`${m[1][0].toUpperCase()}${m[1].slice(1)} ${m[2]}.${m[3]}`);
    else if (d.model) parts.push(d.model);
    if (d.ms_first_word != null) parts.push(`first words ${(d.ms_first_word / 1000).toFixed(1)}s`);
    if (d.cost_usd != null) parts.push(`≈$${Number(d.cost_usd).toFixed(2)}`);
    return parts.join(" · ");
  }

  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function clean(s) { return (s || "").replace(/\s+/g, " ").trim(); }
  function clip(s, n) { return s.length > n ? s.slice(0, n - 1) + "…" : s; }
  function keyOf(el) {
    return clean(el.textContent).toLowerCase().split(" ").slice(0, 6).join("-").replace(/[^a-z0-9-]/g, "");
  }
  function node(tag, cls) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    return el;
  }
  function button(text, onClick) {
    const b = node("button");
    b.type = "button";
    b.textContent = text;
    b.addEventListener("click", onClick);
    return b;
  }
  function debounce(fn, ms) {
    let t;
    return () => { clearTimeout(t); t = setTimeout(fn, ms); };
  }
  function store(key, value) {
    try {
      if (value === undefined) return localStorage.getItem(key);
      localStorage.setItem(key, value);
    } catch {
      return null;
    }
  }
})();
