const composer = document.getElementById("composer");
const conversation = document.getElementById("conversation");
const userMsg = document.getElementById("user-msg");
const statusLine = document.getElementById("status-line");
const statusText = document.getElementById("status-text");
const resultEl = document.getElementById("result");
const resultActions = document.getElementById("result-actions");
const resetBtn = document.getElementById("reset-btn");
const downloadBtn = document.getElementById("download-btn");
const composerError = document.getElementById("composer-error");
const submitBtn = document.getElementById("submit-btn");
const submitBtnLabel = document.getElementById("submit-btn-label");
const sampleLink = document.getElementById("sample-link");
const steps = Array.from(document.querySelectorAll("#stepper .step"));

const ICONS = {
  candidate_profile: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="0.8" fill="currentColor"/></svg>',
  culture: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="9" cy="8" r="3"/><path d="M2.5 20c0-3.2 2.9-5.5 6.5-5.5s6.5 2.3 6.5 5.5"/><circle cx="17.5" cy="9" r="2.3"/><path d="M16 14.2c2.6.4 4.5 2.2 4.5 4.8"/></svg>',
  experience_level: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 20V12"/><path d="M12 20V4"/><path d="M20 20v-7"/></svg>',
  environment: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="9"/><path d="M15 9l-2.2 5.2L9 16l2.2-5.2z"/></svg>',
  company_explainer: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="4" y="3" width="10" height="18" rx="1"/><path d="M14 9h6v12h-6"/><path d="M7 7h.01M11 7h.01M7 11h.01M11 11h.01M7 15h.01M11 15h.01"/></svg>',
  locations: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 21s7-7.2 7-12a7 7 0 1 0-14 0c0 4.8 7 12 7 12z"/><circle cx="12" cy="9" r="2.4"/></svg>',
  questions: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="9"/><path d="M9.5 9.2a2.5 2.5 0 1 1 3.7 2.2c-.7.4-1.2.9-1.2 1.8v.4"/><path d="M12 17h.01"/></svg>',
};

const SECTIONS = [
  ["candidate_profile", "What they're looking for"],
  ["culture", "Culture"],
  ["experience_level", "Experience level"],
  ["environment", "Environment"],
  ["company_explainer", "What the company does"],
  ["locations", "Locations"],
];

function showConversation() {
  composer.style.display = "none";
  conversation.style.display = "block";
}

function setStep(index) {
  steps.forEach((step, i) => {
    step.classList.toggle("done", i < index);
    step.classList.toggle("active", i === index);
  });
}

function typeInto(el, text, chunk = 3, delay = 12) {
  return new Promise((resolve) => {
    if (!text) {
      resolve();
      return;
    }
    let i = 0;
    const id = setInterval(() => {
      i += chunk;
      el.textContent = text.slice(0, i);
      if (i >= text.length) {
        clearInterval(id);
        resolve();
      }
    }, delay);
  });
}

function makeSection(key, label) {
  const section = document.createElement("div");
  section.className = "result-section";
  const head = document.createElement("div");
  head.className = "section-head";
  const icon = document.createElement("span");
  icon.className = "icon";
  icon.innerHTML = ICONS[key] || "";
  const h2 = document.createElement("h2");
  h2.textContent = label;
  head.appendChild(icon);
  head.appendChild(h2);
  const p = document.createElement("p");
  section.appendChild(head);
  section.appendChild(p);
  resultEl.appendChild(section);
  return p;
}

async function renderResult(result) {
  resultEl.innerHTML = "";
  for (const [key, label] of SECTIONS) {
    const p = makeSection(key, label);
    await typeInto(p, result[key] || "");
  }

  const section = document.createElement("div");
  section.className = "result-section";
  const head = document.createElement("div");
  head.className = "section-head";
  const icon = document.createElement("span");
  icon.className = "icon";
  icon.innerHTML = ICONS.questions;
  const h2 = document.createElement("h2");
  h2.textContent = "Questions to ask";
  head.appendChild(icon);
  head.appendChild(h2);
  const ul = document.createElement("ul");
  section.appendChild(head);
  section.appendChild(ul);
  resultEl.appendChild(section);

  let i = 1;
  for (const q of result.questions_to_ask || []) {
    const li = document.createElement("li");
    const badge = document.createElement("span");
    badge.className = "q-badge";
    badge.textContent = String(i++);
    const span = document.createElement("span");
    li.appendChild(badge);
    li.appendChild(span);
    ul.appendChild(li);
    await typeInto(span, q);
  }
}

function showError(message) {
  statusLine.style.display = "none";
  resultEl.innerHTML = "";
  const box = document.createElement("div");
  box.className = "error-box";
  box.textContent = message;
  resultEl.appendChild(box);
  downloadBtn.style.display = "none";
  resultActions.style.display = "flex";
}

function startPolling(jobId) {
  let lastStage = null;
  let stageIndex = -1;
  const interval = setInterval(async () => {
    let res, data;
    try {
      res = await fetch(`/briefing/${jobId}/status`);
      data = await res.json();
    } catch {
      return;
    }
    if (!res.ok) {
      clearInterval(interval);
      showError(data.error || "That briefing could not be found.");
      return;
    }
    if (data.status === "pending") {
      if (data.stage && data.stage !== lastStage) {
        lastStage = data.stage;
        stageIndex = Math.min(stageIndex + 1, steps.length - 1);
        statusText.textContent = data.stage;
        setStep(stageIndex);
      }
    } else if (data.status === "done") {
      clearInterval(interval);
      statusLine.style.display = "none";
      renderResult(data.result).then(() => {
        downloadBtn.href = `/briefing/${jobId}/report.pdf`;
        downloadBtn.style.display = "inline-flex";
        resultActions.style.display = "flex";
      });
    } else if (data.status === "error") {
      clearInterval(interval);
      showError(data.error);
    }
  }, 1500);
}

async function startSample() {
  const res = await fetch("/briefing/sample", { method: "POST" });
  const data = await res.json();
  userMsg.textContent = "Load a sample briefing for Account Executive at Creatio.";
  history.pushState({}, "", `/?job=${data.job_id}`);
  showConversation();
  startPolling(data.job_id);
}

composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  composerError.style.display = "none";
  submitBtn.disabled = true;
  submitBtnLabel.textContent = "Generating...";

  const formData = new FormData(composer);

  try {
    const res = await fetch("/briefing", { method: "POST", body: formData });
    const data = await res.json();

    if (!res.ok) {
      composerError.textContent = data.error || "Something went wrong.";
      composerError.style.display = "block";
      submitBtn.disabled = false;
      submitBtnLabel.textContent = "Generate briefing";
      return;
    }

    const jobTitle = formData.get("job_title");
    const companyName = formData.get("company_name");
    userMsg.textContent = `Generate a briefing for the ${jobTitle} role at ${companyName}.`;

    history.pushState({}, "", `/?job=${data.job_id}`);
    showConversation();
    startPolling(data.job_id);
  } catch {
    composerError.textContent = "Network error — please try again.";
    composerError.style.display = "block";
    submitBtn.disabled = false;
    submitBtnLabel.textContent = "Generate briefing";
  }
});

resetBtn.addEventListener("click", () => {
  location.href = "/";
});

sampleLink.addEventListener("click", (event) => {
  event.preventDefault();
  startSample();
});

const existingJob = new URLSearchParams(location.search).get("job");
if (existingJob) {
  userMsg.textContent = "Picking back up where we left off...";
  showConversation();
  startPolling(existingJob);
}
