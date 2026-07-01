const BTN_CLASS = "rr-mark-btn";

function createBtn() {
  const btn = document.createElement("div");
  btn.className = BTN_CLASS;
  btn.setAttribute("role", "button");
  btn.setAttribute("tabindex", "0");
  btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>Mark as interview`;
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    console.log("[RevReady] Mark as interview clicked");
  });
  return btn;
}

function ensureInjected() {
  const bar = document.querySelector(".pPTZAe");
  if (!bar) return;
  if (bar.querySelector(`.${BTN_CLASS}`)) return;

  const btn = createBtn();
  bar.prepend(btn);
}

const observer = new MutationObserver(ensureInjected);
observer.observe(document.body, { childList: true, subtree: true });

// Catch initial state in case popup is already open
ensureInjected();
