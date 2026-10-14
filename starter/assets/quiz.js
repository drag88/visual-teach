// Quiz widgets shared by every lesson. Markup lives in the lesson; this file adds behaviour.
//
// Multiple choice:
//   <div class="quiz mcq"><p class="q">Question</p>
//     <div class="opts"><button class="opt" data-right>Answer</button><button class="opt">Other</button></div>
//     <p class="fb">Why the right answer is right.</p></div>
// Recall (write first, then compare):
//   <div class="quiz recall"><p class="q">Prompt</p><div class="model">Model answer</div></div>
// Ordering (list the steps in the correct order; they are shuffled on load):
//   <div class="quiz order"><p class="q">Prompt</p><ol class="items"><li>First</li><li>Second</li></ol></div>
// Matching (each item gets a dropdown of every distinct answer, sorted A to Z):
//   <div class="quiz match"><p class="q">Prompt</p><ul class="pairs"><li data-a="Tool">ask_book</li></ul></div>
// Spot (tap a part of a diagram; clones the lesson's hero diagram so the reader answers on the picture):
//   <div class="quiz spot" data-from="hero-figure-id" data-answer="spot-id"><p class="q">Prompt</p><p class="fb">Why</p></div>
//   The hero <figure id="hero-figure-id"> wraps each tappable part in <g data-spot="spot-id">.
// Score line: <p class="score" id="score"></p>

(function () {
  const shuffle = (a) => {
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  };

  let asked = 0;
  let firstTry = 0;
  const scoreEl = () => document.getElementById("score");
  const updateScore = () => {
    const el = scoreEl();
    if (el && asked) el.textContent = `${firstTry} of ${asked} right first time`;
  };

  document.querySelectorAll(".quiz.mcq").forEach((quiz) => {
    const opts = quiz.querySelector(".opts");
    const buttons = shuffle([...opts.querySelectorAll("button.opt")]);
    buttons.forEach((b) => opts.appendChild(b));
    const fb = quiz.querySelector(".fb");
    let done = false;
    buttons.forEach((b) =>
      b.addEventListener("click", () => {
        if (done) return;
        done = true;
        asked++;
        const right = b.hasAttribute("data-right");
        if (right) firstTry++;
        b.classList.add(right ? "right" : "wrong");
        buttons.find((x) => x.hasAttribute("data-right")).classList.add("right");
        if (fb) fb.classList.add("show", right ? "ok" : "no");
        updateScore();
      })
    );
  });

  document.querySelectorAll(".quiz.recall").forEach((quiz) => {
    const model = quiz.querySelector(".model");
    const box = document.createElement("textarea");
    box.placeholder = "Write your answer from memory before you reveal.";
    const btn = document.createElement("button");
    btn.className = "act";
    btn.textContent = "Compare with the answer";
    btn.addEventListener("click", () => {
      if (!box.value.trim()) {
        box.focus();
        return;
      }
      model.classList.add("show");
      btn.remove();
    });
    quiz.insertBefore(box, model);
    quiz.insertBefore(btn, model);
  });

  document.querySelectorAll(".quiz.order").forEach((quiz) => {
    const list = quiz.querySelector("ol.items");
    const steps = [...list.querySelectorAll("li")].map((li, i) => ({ html: li.innerHTML, pos: i + 1 }));
    list.remove();
    const rows = shuffle(steps.slice()).map((s) => {
      const row = document.createElement("div");
      row.className = "order-row";
      row.dataset.pos = s.pos;
      const sel = document.createElement("select");
      sel.innerHTML = '<option value="">#</option>' + steps.map((_, i) => `<option>${i + 1}</option>`).join("");
      const text = document.createElement("div");
      text.innerHTML = s.html;
      row.append(sel, text);
      quiz.appendChild(row);
      return { row, sel, pos: s.pos };
    });
    const btn = document.createElement("button");
    btn.className = "act";
    btn.textContent = "Check order";
    const fb = document.createElement("p");
    fb.className = "fb";
    let counted = false;
    btn.addEventListener("click", () => {
      let ok = 0;
      rows.forEach((r) => {
        const right = Number(r.sel.value) === r.pos;
        if (right) ok++;
        r.row.classList.toggle("right", right);
        r.row.classList.toggle("wrong", !right);
      });
      const all = ok === rows.length;
      if (!counted) {
        counted = true;
        asked++;
        if (all) firstTry++;
        updateScore();
      }
      fb.className = "fb show " + (all ? "ok" : "no");
      fb.textContent = all
        ? "Every step is in place."
        : `${ok} of ${rows.length} in place. The red ones are off; try again.`;
    });
    quiz.append(btn, fb);
  });
  document.querySelectorAll(".quiz.match").forEach((quiz) => {
    const list = quiz.querySelector("ul.pairs");
    const items = [...list.querySelectorAll("li")].map((li) => ({ html: li.innerHTML, a: li.dataset.a }));
    const answers = [...new Set(items.map((i) => i.a))].sort();
    list.remove();
    const rows = shuffle(items.slice()).map((it) => {
      const row = document.createElement("div");
      row.className = "match-row";
      row.dataset.a = it.a;
      const text = document.createElement("div");
      text.innerHTML = it.html;
      const sel = document.createElement("select");
      sel.innerHTML = '<option value="">Pick</option>' + answers.map((a) => `<option>${a}</option>`).join("");
      row.append(text, sel);
      quiz.appendChild(row);
      return { row, sel, a: it.a };
    });
    const btn = document.createElement("button");
    btn.className = "act";
    btn.textContent = "Check matches";
    const fb = document.createElement("p");
    fb.className = "fb";
    let counted = false;
    btn.addEventListener("click", () => {
      let ok = 0;
      rows.forEach((r) => {
        const right = r.sel.value === r.a;
        if (right) ok++;
        r.row.classList.toggle("right", right);
        r.row.classList.toggle("wrong", !right);
      });
      const all = ok === rows.length;
      if (!counted) {
        counted = true;
        asked++;
        if (all) firstTry++;
        updateScore();
      }
      fb.className = "fb show " + (all ? "ok" : "no");
      fb.textContent = all ? "Every match is right." : `${ok} of ${rows.length} right. Fix the red ones and check again.`;
    });
    quiz.append(btn, fb);
  });
  document.querySelectorAll(".quiz.spot").forEach((quiz) => {
    const source = document.getElementById(quiz.dataset.from);
    if (!source) return;
    const clone = source.querySelector(".scroll").cloneNode(true);
    // Ids must stay unique; marker references still resolve to the hero diagram's markers.
    clone.querySelectorAll("[id]").forEach((el) => el.removeAttribute("id"));
    const svg = clone.querySelector("svg");
    svg.removeAttribute("aria-labelledby");
    svg.setAttribute("aria-label", quiz.querySelector(".q").textContent);
    const fb = quiz.querySelector(".fb");
    quiz.insertBefore(clone, fb);
    const parts = [...clone.querySelectorAll("g[data-spot]")];
    let done = false;
    const pick = (g) => {
      if (done) return;
      done = true;
      asked++;
      const right = g.dataset.spot === quiz.dataset.answer;
      if (right) firstTry++;
      g.classList.add(right ? "right" : "wrong");
      parts.filter((x) => x.dataset.spot === quiz.dataset.answer).forEach((x) => x.classList.add("right"));
      fb.classList.add("show", right ? "ok" : "no");
      updateScore();
    };
    parts.forEach((g) => {
      g.setAttribute("tabindex", "0");
      g.setAttribute("role", "button");
      g.addEventListener("click", () => pick(g));
      g.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          pick(g);
        }
      });
    });
  });
})();
