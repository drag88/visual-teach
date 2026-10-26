// Light or dark. Follows the system until the learner picks one with the switch, then remembers it in this
// browser. Some built-in browsers (cmux's, for one) always report light, so the switch is the way out.
// Loaded in <head> so the chosen theme is set before the page paints.
(() => {
  const root = document.documentElement;
  const KEY = "vt-theme";
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") root.dataset.theme = saved;
  } catch {}

  const shown = () => root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");

  addEventListener("DOMContentLoaded", () => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "theme-toggle";
    const label = () => (b.textContent = shown() === "dark" ? "Light" : "Dark");
    label();
    b.addEventListener("click", () => {
      root.dataset.theme = shown() === "dark" ? "light" : "dark";
      try { localStorage.setItem(KEY, root.dataset.theme); } catch {}
      label();
    });
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", label);
    // The row at the top right, shared with ask.js's Teach button, whichever script gets there first.
    let bar = document.querySelector(".top-bar");
    if (!bar) {
      bar = document.createElement("div");
      bar.className = "top-bar";
      document.body.prepend(bar);
    }
    bar.append(b);
  });
})();
