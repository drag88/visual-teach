// Quiz widgets shared by every lesson. Markup lives in the lesson; this file adds behaviour.
//
// Multiple choice:
//   <div class="quiz mcq"><p class="q">Question</p>
//     <div class="opts"><button class="opt" data-right>Answer</button><button class="opt">Other</button></div>
//     <p class="fb">Why the right answer is right.</p></div>
// Recall (write first, then compare):
//   <div class="quiz recall"><p class="q">Prompt</p><div class="model">Model answer</div></div>
// Predict (recall for an outcome: what will this print, what happened next, what does the data show):
//   <div class="quiz predict"><p class="q">Prompt</p><pre><code>optional code or data</code></pre><div class="model">The real outcome</div></div>
//   After the reveal, recall and predict ask "I got it" or "I missed it". These marks feed review, not the score.
// Ordering (list the steps in the correct order; they are shuffled on load):
//   <div class="quiz order"><p class="q">Prompt</p><ol class="items"><li>First</li><li>Second</li></ol></div>
// Matching (each item gets a dropdown of every distinct answer, sorted A to Z):
//   <div class="quiz match"><p class="q">Prompt</p><ul class="pairs"><li data-a="Tool">ask_book</li></ul></div>
// Spot (tap a part of a diagram; clones the lesson's hero diagram so the reader answers on the picture):
//   <div class="quiz spot" data-from="hero-figure-id" data-answer="spot-id"><p class="q">Prompt</p><p class="fb">Why</p></div>
//   The hero <figure id="hero-figure-id"> wraps each tappable part in <g data-spot="spot-id">.
// Score line: <p class="score" id="score"></p>
//
// Ids: give every quiz id="q-<slug>". Without one it is keyed "k-" plus its question's first six words.
// Either way the key goes in data-quiz, and lesson.html#<key> scrolls to that quiz and flashes it.
// Event: each quiz dispatches a bubbling "quiz" CustomEvent with detail {quiz, type, event, right, q, answer, model}.
//   "answered" on the first check of mcq, order, match and spot (right true or false), and on a self-mark.
//   After a miss, mcq and spot offer Try again. A retry is practice: it adds no event and leaves the score alone.
//   "revealed" when recall or predict shows its answer, with the learner's text and the model text, right null.
// This file never talks to a server; ask.js listens for the event when a server is running.

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

  // The score counts first tries and review already has the miss, so a retry only clears this quiz's marks.
  const tryAgain = (quiz, reset, focus) => {
    const b = document.createElement("button");
    b.className = "act";
    b.textContent = "Try again";
    b.addEventListener("click", () => {
      b.remove();
      reset();
      focus.focus();
    });
    quiz.appendChild(b);
  };

  // A miss names the right answer in words at the start of the feedback: a coloured mark alone is easy to miss,
  // and some readers cannot see it. Returns the words, so a retry can take them away again.
  const nameAnswer = (fb, text) => {
    const answer = document.createElement("span");
    answer.className = "answer";
    answer.textContent = text;
    fb.prepend(answer);
    return answer;
  };

  const TYPES = ["mcq", "recall", "predict", "order", "match", "spot"];
  const question = (quiz) => quiz.querySelector(".q")?.textContent.trim() ?? "";
  const emit = (quiz, event, right, answer = null, model = null) =>
    quiz.dispatchEvent(
      new CustomEvent("quiz", {
        bubbles: true,
        detail: { quiz: quiz.dataset.quiz, type: TYPES.find((t) => quiz.classList.contains(t)), event, right, q: question(quiz), answer, model },
      })
    );

  // Unicode-aware, so a question in any language still gets a usable key.
  const slug = (s) => s.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-+|-+$/g, "");
  document.querySelectorAll(".quiz").forEach((quiz) => {
    quiz.dataset.quiz = quiz.id || "k-" + slug(question(quiz).split(/\s+/).slice(0, 6).join(" "));
  });

  document.querySelectorAll(".quiz.mcq").forEach((quiz) => {
    const opts = quiz.querySelector(".opts");
    const buttons = shuffle([...opts.querySelectorAll("button.opt")]);
    buttons.forEach((b) => opts.appendChild(b));
    const fb = quiz.querySelector(".fb");
    let done = false;
    let tried = false;
    buttons.forEach((b) =>
      b.addEventListener("click", () => {
        if (done) return;
        done = true;
        const right = b.hasAttribute("data-right");
        const correct = buttons.find((x) => x.hasAttribute("data-right"));
        b.classList.add(right ? "right" : "wrong");
        correct.classList.add("right");
        if (fb) fb.classList.add("show", right ? "ok" : "no");
        if (!tried) {
          tried = true;
          asked++;
          if (right) firstTry++;
          updateScore();
          emit(quiz, "answered", right, b.textContent.trim(), correct.textContent.trim());
        }
        if (!right) {
          const answer = fb && nameAnswer(fb, `The answer is “${correct.textContent.trim()}”. `);
          tryAgain(quiz, () => {
            done = false;
            buttons.forEach((x) => x.classList.remove("right", "wrong"));
            if (fb) fb.classList.remove("show", "ok", "no");
            if (answer) answer.remove();
          }, buttons[0]);
        }
      })
    );
  });

  document.querySelectorAll(".quiz.recall, .quiz.predict").forEach((quiz) => {
    const predict = quiz.classList.contains("predict");
    const model = quiz.querySelector(".model");
    const box = document.createElement("textarea");
    box.placeholder = predict ? "Write what you expect before you look." : "Write your answer from memory before you reveal.";
    const btn = document.createElement("button");
    btn.className = "act";
    btn.textContent = predict ? "Show the real outcome" : "Compare with the answer";
    // The learner marks their own answer; that feeds review but stays out of the score, which counts only checked answers.
    const marks = document.createElement("div");
    marks.className = "marks";
    [["I got it", true], ["I missed it", false]].forEach(([label, right]) => {
      const b = document.createElement("button");
      b.className = "mark";
      b.textContent = label;
      b.addEventListener("click", () => {
        marks.querySelectorAll("button").forEach((x) => (x.disabled = true));
        b.setAttribute("aria-pressed", "true");
        emit(quiz, "answered", right, box.value, model.textContent.trim());
      });
      marks.appendChild(b);
    });
    btn.addEventListener("click", () => {
      if (!box.value.trim()) {
        box.focus();
        return;
      }
      model.classList.add("show");
      btn.remove();
      model.after(marks);
      emit(quiz, "revealed", null, box.value, model.textContent.trim());
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
        emit(quiz, "answered", all);
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
        emit(quiz, "answered", all);
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
    const target = parts.find((x) => x.dataset.spot === quiz.dataset.answer);
    const label = (target && target.querySelector("text")?.textContent.trim()) || quiz.dataset.answer;
    let done = false;
    let tried = false;
    const pick = (g) => {
      if (done) return;
      done = true;
      const right = g.dataset.spot === quiz.dataset.answer;
      g.classList.add(right ? "right" : "wrong");
      parts.filter((x) => x.dataset.spot === quiz.dataset.answer).forEach((x) => x.classList.add("right"));
      fb.classList.add("show", right ? "ok" : "no");
      if (!tried) {
        tried = true;
        asked++;
        if (right) firstTry++;
        updateScore();
        emit(quiz, "answered", right);
      }
      if (!right) {
        const answer = nameAnswer(fb, `The answer is ${label}, marked in green. `);
        tryAgain(quiz, () => {
          done = false;
          parts.forEach((x) => x.classList.remove("right", "wrong"));
          fb.classList.remove("show", "ok", "no");
          answer.remove();
        }, parts[0]);
      }
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

  // A review link lands on its quiz. A "k-" key is not an element id, so the browser cannot scroll there itself.
  const land = () => {
    const key = decodeURIComponent(location.hash.slice(1));
    const quiz = key && document.querySelector(`.quiz[data-quiz="${CSS.escape(key)}"]`);
    if (!quiz) return;
    quiz.scrollIntoView({ block: "center" });
    quiz.classList.add("flash");
    quiz.addEventListener("animationend", () => quiz.classList.remove("flash"), { once: true });
  };
  land();
  window.addEventListener("hashchange", land);
})();
