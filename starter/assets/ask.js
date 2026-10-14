// Ask while reading: highlight text in a lesson and get a live answer from Claude in a card beside it.
// Needs the course served by the skill's scripts/serve.py. Opened as a plain file, the lesson works as before.
(() => {
  const main = document.querySelector("main");
  if (!main) return;

  const SKIP = "nav, h1, h2, h3, .subtitle, .src, .score, .read, footer, script, .ask-card";
  const LABEL = { explain: "Explain", simpler: "Simpler", more: "More", connect: "Connect", ask: "Ask", whole: "Ask" };
  const lesson = decodeURIComponent(location.pathname.replace(/^\/+/, ""));
  const title = (document.querySelector("h1") || document.querySelector("title") || {}).textContent || "";
  const wide = matchMedia("(min-width: 1180px)");
  const narrow = matchMedia("(max-width: 720px), (pointer: coarse)");
  const cards = [];
  let mode = store("vt-mode") || "quick";

  const blocks = [...main.children].filter((el) => !el.matches(SKIP));
  blocks.forEach((el, i) => {
    el.dataset.p = i + 1;
    el.dataset.key = keyOf(el);
  });

  if (!/^https?:$/.test(location.protocol)) return hint();
  fetch("/api/ping")
    .then((r) => (r.ok ? r.json() : null))
    .then((info) => (info ? start() : hint()))
    .catch(hint);

  // Setup

  function start() {
    document.body.classList.add("ask-on");
    buildSelectionBar();
    buildAskBar();
    fetch("/api/threads?lesson=" + encodeURIComponent(lesson)).then((r) => r.json())
      .then(({ threads }) => {
        threads.forEach(restore);
        layout();
        highlight();
      }).catch(() => {});
    wide.addEventListener("change", () => {
      cards.forEach((c) => place(c, c.block));
      layout();
    });
    addEventListener("resize", scheduleLayout);
    document.addEventListener("click", (e) => {
      const chip = e.target.closest(".ask-pchip");
      if (!chip) return;
      e.preventDefault();
      const target = main.querySelector(`[data-p="${chip.dataset.p}"]`);
      if (!target) return;
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      target.classList.remove("ask-flash");
      void target.offsetWidth;
      target.classList.add("ask-flash");
    });
  }

  let topicsLoaded = false;
  function loadTopics() {
    if (topicsLoaded) return;
    topicsLoaded = true;
    fetch("/api/topics").then((r) => r.json()).then(({ topics }) => {
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
    for (const kind of ["explain", "simpler", "more", "connect", "ask"]) {
      const b = node("button");
      b.type = "button";
      b.textContent = kind === "connect" || kind === "ask" ? LABEL[kind] + "…" : LABEL[kind];
      b.dataset.kind = kind;
      selBar.append(b);
    }
    const form = node("form", "ask-sel-form");
    form.hidden = true;
    const input = node("input");
    input.setAttribute("aria-label", "Your question");
    const go = node("button");
    go.type = "submit";
    go.textContent = "Ask";
    form.append(input, go);
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
        input.value = "";
        input.placeholder = kind === "connect" ? "Connect to which topic?" : "Your question";
        if (kind === "connect") {
          loadTopics();
          input.setAttribute("list", "ask-topics");
        } else input.removeAttribute("list");
        input.focus();
        return;
      }
      submit(kind);
    });
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text || !pending) return;
      submit(form.dataset.kind, text);
    });
    document.addEventListener("selectionchange", debounce(onSelection, 150));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") hideSelectionBar();
    });
  }

  function onSelection() {
    if (selBar.contains(document.activeElement)) return;
    const sel = getSelection();
    if (!sel.rangeCount || sel.isCollapsed) return hideSelectionBar();
    const range = sel.getRangeAt(0);
    const start = range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentElement;
    const block = start && start.closest("main > [data-p]");
    const text = sel.toString().replace(/\s+/g, " ").trim();
    if (!block || !text || text.length > 2000 || start.closest(".ask-card")) return hideSelectionBar();
    pending = { block, text, quote: quoteOf(block, range, text), range: range.cloneRange() };
    showSelectionBar(range);
  }

  function showSelectionBar(range) {
    selBar.querySelector(".ask-sel-form").hidden = true;
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
    const { block, text: selection, quote, range } = pending;
    hideSelectionBar();
    getSelection().removeAllRanges();
    const card = makeCard({ kind, selection, block });
    card.range = range;
    highlight();
    place(card, block);
    layout();
    send(card, {
      kind, mode, lesson, lesson_title: title, selection,
      para: { n: +block.dataset.p, key: block.dataset.key, quote },
      para_text: clip(clean(block.innerText), 1500),
      question: kind === "ask" ? text : null,
      topic: kind === "connect" ? text : null,
      lesson_text: lessonText(),
    }, kind === "ask" ? text : kind === "connect" ? "Connect to " + text : null);
  }

  // Ask about the whole lesson

  function buildAskBar() {
    const bar = node("form", "ask-bar");
    const input = node("input");
    input.placeholder = "Ask about this page";
    input.setAttribute("aria-label", "Ask about this page");
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
    const sendBtn = node("button", "ask-send");
    sendBtn.type = "submit";
    sendBtn.textContent = "↑";
    sendBtn.setAttribute("aria-label", "Send");
    bar.append(input, key, modes, sendBtn);
    document.body.append(bar);
    bar.addEventListener("submit", (e) => {
      e.preventDefault();
      const q = input.value.trim();
      if (!q) return;
      input.value = "";
      const card = makeCard({ kind: "whole", block: null });
      place(card, null);
      layout();
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      send(card, { kind: "whole", mode, lesson, lesson_title: title, question: q, lesson_text: lessonText() }, q);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key !== "/" || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable) return;
      e.preventDefault();
      input.focus();
    });
  }

  // Cards

  function makeCard({ kind, selection, block, thread = null }) {
    const card = node("aside", "ask-card");
    card.thread = thread;
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
    const input = node("input");
    input.placeholder = "Ask a follow-up";
    input.setAttribute("aria-label", "Ask a follow-up");
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
      send(card, { thread: card.thread, kind: "ask", mode, lesson, question: q }, q);
    });
    card.append(head, log, foot, follow);
    Object.assign(card, { log, meta, block });
    cards.push(card);
    return card;
  }

  function post(path, body, signal) {
    return fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
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
    if (event === "thread") card.thread = d.thread;
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
      card.thread = null;
    }
    send(card, body, card.lastQuestion);
  }

  function remove(card) {
    if (card.controller) card.controller.abort();
    if (card.thread) post("/api/delete", { thread: card.thread }).catch(() => {});
    cards.splice(cards.indexOf(card), 1);
    card.remove();
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
        const asked = t.kind === "ask" || t.kind === "whole" || t.kind === "connect" || ex;
        ex = exchange(card, asked ? m.text : null);
        ex.status.remove();
      } else if (m.role === "assistant" && ex) {
        ex.answer.innerHTML = md(m.text || "");
        card.meta.textContent = metaLine(m);
      }
    }
    if (t.anchor && !block) {
      const moved = node("p", "ask-status");
      moved.textContent = "The passage this was about has moved or changed.";
      card.log.prepend(moved);
    }
    if (block && t.anchor && t.anchor.quote) card.range = findRange(block, t.anchor.quote.exact);
    setFolded(card, true);
    place(card, block);
  }

  function setFolded(card, folded) {
    card.classList.toggle("folded", folded);
    card.querySelector(".ask-toggle").textContent = folded ? "+" : "–";
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
      while (after.nextElementSibling && after.nextElementSibling.classList.contains("ask-card")) after = after.nextElementSibling;
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
    const ranges = cards.map((c) => c.range).filter(Boolean);
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
    s = s.replace(/\u0000/g, "")
      .replace(/`([^`]+)`/g, (_, c) => hold(`<code>${esc(c)}</code>`))
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s()<>"']+)\)/g, (_, t, u) => link(u, t))
      .replace(/https?:\/\/[^\s()<>"'`]+/g, (u) => link(u, u));
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
