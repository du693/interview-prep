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
const loginBtn = document.getElementById("login-btn");
const userBadge = document.getElementById("user-badge");
const userEmailEl = document.getElementById("user-email");
const logoutBtn = document.getElementById("logout-btn");
const embeddedCloseBtn = document.getElementById("embedded-close-btn");

embeddedCloseBtn.addEventListener("click", () => {
  try {
    if (window.parent && typeof window.parent.closeBriefingModal === "function") {
      window.parent.closeBriefingModal();
      return;
    }
  } catch {
    // fall through to postMessage
  }
  window.parent.postMessage({ type: "close-briefing-modal" }, window.location.origin);
});

const scrollHint = document.getElementById("scroll-hint");
if (document.documentElement.classList.contains("embedded") && scrollHint) {
  const getActiveView = () => (composer.style.display !== "none" ? composer : conversation);
  const updateScrollHint = () => {
    const view = getActiveView();
    const scrollable = view.scrollHeight > view.clientHeight + 4;
    const nearBottom = view.scrollHeight - view.scrollTop - view.clientHeight < 24;
    scrollHint.style.display = scrollable && !nearBottom ? "flex" : "none";
  };
  composer.addEventListener("scroll", updateScrollHint);
  conversation.addEventListener("scroll", updateScrollHint);
  window.addEventListener("resize", updateScrollHint);
  updateScrollHint();
}

function decodeJwtEmail(token) {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload.email || payload.user_metadata?.email || "";
  } catch {
    return "";
  }
}

const AUTH_TOKEN = document.body.dataset.token || "";
const AUTH_EMAIL = document.body.dataset.email || "";

function updateAuthUI() {
  if (AUTH_TOKEN) {
    loginBtn.style.display = "none";
    userBadge.style.display = "flex";
    userEmailEl.textContent = AUTH_EMAIL;
  } else {
    loginBtn.style.display = "inline-flex";
    userBadge.style.display = "none";
  }
}
updateAuthUI();

logoutBtn.addEventListener("click", () => {
  window.location.href = "/auth/logout";
});

const ICONS = {
  candidate_profile: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="0.8" fill="currentColor"/></svg>',
  culture: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="9" cy="8" r="3"/><path d="M2.5 20c0-3.2 2.9-5.5 6.5-5.5s6.5 2.3 6.5 5.5"/><circle cx="17.5" cy="9" r="2.3"/><path d="M16 14.2c2.6.4 4.5 2.2 4.5 4.8"/></svg>',
  experience_level: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 20V12"/><path d="M12 20V4"/><path d="M20 20v-7"/></svg>',
  environment: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="9"/><path d="M15 9l-2.2 5.2L9 16l2.2-5.2z"/></svg>',
  company_explainer: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="4" y="3" width="10" height="18" rx="1"/><path d="M14 9h6v12h-6"/><path d="M7 7h.01M11 7h.01M7 11h.01M11 11h.01M7 15h.01M11 15h.01"/></svg>',
  locations: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 21s7-7.2 7-12a7 7 0 1 0-14 0c0 4.8 7 12 7 12z"/><circle cx="12" cy="9" r="2.4"/></svg>',
  stage_brief: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>',
  watch_out: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 3.5l9 16h-18z"/><path d="M12 10v4"/><path d="M12 17.2h.01"/></svg>',
  skills_at_risk: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M8 4L3 12l5 8"/><path d="M16 4l5 8-5 8"/></svg>',
  prep_plan: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M9 11l2 2 4-4"/><circle cx="12" cy="12" r="9"/></svg>',
  role_questions: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="9"/><path d="M9.5 9.2a2.5 2.5 0 1 1 3.7 2.2c-.7.4-1.2.9-1.2 1.8v.4"/><path d="M12 17h.01"/></svg>',
  research_questions: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/><path d="M10.5 7.5v6"/><path d="M7.5 10.5h6"/></svg>',
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
  if (document.documentElement.classList.contains("embedded")) {
    conversation.style.display = "block";
    void conversation.offsetHeight;
    composer.classList.add("slide-out");
    conversation.classList.add("slide-in");
    setTimeout(() => {
      composer.style.display = "none";
    }, 870);
    return;
  }
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

async function renderList(iconKey, label, items) {
  if (!items || items.length === 0) return;

  const section = document.createElement("div");
  section.className = "result-section";
  const head = document.createElement("div");
  head.className = "section-head";
  const icon = document.createElement("span");
  icon.className = "icon";
  icon.innerHTML = ICONS[iconKey];
  const h2 = document.createElement("h2");
  h2.textContent = label;
  head.appendChild(icon);
  head.appendChild(h2);
  const ul = document.createElement("ul");
  section.appendChild(head);
  section.appendChild(ul);
  resultEl.appendChild(section);

  let i = 1;
  for (const item of items) {
    const li = document.createElement("li");
    const badge = document.createElement("span");
    badge.className = "q-badge";
    badge.textContent = String(i++);
    const span = document.createElement("span");
    li.appendChild(badge);
    li.appendChild(span);
    ul.appendChild(li);
    await typeInto(span, item);
  }
}

async function renderResult(result) {
  resultEl.innerHTML = "";
  for (const [key, label] of SECTIONS) {
    const p = makeSection(key, label);
    await typeInto(p, result[key] || "");
  }

  if (result.stage_brief) {
    const p = makeSection("stage_brief", "What to expect");
    await typeInto(p, result.stage_brief);
  }
  if (result.watch_out) {
    const p = makeSection("watch_out", "Watch out for");
    await typeInto(p, result.watch_out);
  }

  await renderList("skills_at_risk", "Skills at risk", result.skills_at_risk);
  await renderList("prep_plan", "Prep plan", result.prep_plan);
  await renderList("role_questions", "Questions to ask", result.role_questions);
  await renderList("research_questions", "Questions from your research", result.research_questions);
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
  const headers = AUTH_TOKEN ? { Authorization: `Bearer ${AUTH_TOKEN}` } : {};
  const res = await fetch("/briefing/sample", { method: "POST", headers });
  const data = await res.json();
  userMsg.textContent = "Load a sample briefing for Account Executive at Creatio.";
  history.pushState({}, "", `/app?job=${data.job_id}`);
  showConversation();
  startPolling(data.job_id);
}

composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  composerError.style.display = "none";

  if (!AUTH_TOKEN) {
    composerError.textContent = "Please sign in with Google to continue.";
    composerError.style.display = "block";
    return;
  }

  const formData = new FormData(composer);
  const stage = formData.get("stage_type") || "intro_call";

  if (stage === "recruiter_screen") {
    await handleRecruiterSave(formData);
    return;
  }

  submitBtn.disabled = true;
  submitBtnLabel.textContent = "Generating...";

  try {
    const res = await fetch("/briefing", {
      method: "POST",
      headers: { Authorization: `Bearer ${AUTH_TOKEN}` },
      body: formData,
    });
    const data = await res.json();

    if (res.status === 401) {
      composerError.textContent = data.detail || "Your session has expired — please sign in again.";
      composerError.style.display = "block";
      submitBtn.disabled = false;
      submitBtnLabel.textContent = "Generate briefing";
      return;
    }

    if (!res.ok) {
      composerError.textContent = data.error || data.detail || "Something went wrong.";
      composerError.style.display = "block";
      submitBtn.disabled = false;
      submitBtnLabel.textContent = "Generate briefing";
      return;
    }

    const jobTitle = formData.get("job_title");
    const companyName = formData.get("company_name");
    userMsg.textContent = `Generate a briefing for the ${jobTitle} role at ${companyName}.`;

    history.pushState({}, "", `/app?job=${data.job_id}`);
    showConversation();
    startPolling(data.job_id);
  } catch {
    composerError.textContent = "Network error — please try again.";
    composerError.style.display = "block";
    submitBtn.disabled = false;
    submitBtnLabel.textContent = "Generate briefing";
  }
});

async function handleRecruiterSave(formData) {
  submitBtn.disabled = true;
  submitBtnLabel.textContent = "Saving...";

  try {
    const res = await fetch("/recruiter-screen", {
      method: "POST",
      headers: { Authorization: `Bearer ${AUTH_TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        company_name: formData.get("company_name") || "",
        job_title: formData.get("job_title") || "",
        notes: formData.get("recruiter_notes") || "",
        comp_range: formData.get("comp_range") || "",
      }),
    });

    if (!res.ok) {
      const data = await res.json();
      composerError.textContent = data.error || data.detail || "Something went wrong.";
      composerError.style.display = "block";
      return;
    }

    const jobTitle = formData.get("job_title") || "this role";
    const company = formData.get("company_name") || "";
    userMsg.textContent = `Recruiter screen — ${jobTitle}${company ? ` at ${company}` : ""}.`;
    showConversation();

    result.innerHTML = `
      <div class="recruiter-save-card">
        <div class="rsc-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M20 6L9 17l-5-5"/></svg>
        </div>
        <h3>Added to pipeline</h3>
        <p>${jobTitle}${company ? ` at <strong>${company}</strong>` : ""} — saved at the recruiter screen stage.</p>
        <p class="rsc-hint">No briefing needed yet. Once you're through to the next stage, come back and prep properly.</p>
      </div>`;
  } catch {
    composerError.textContent = "Network error — please try again.";
    composerError.style.display = "block";
  } finally {
    submitBtn.disabled = false;
    submitBtnLabel.textContent = "Save to pipeline";
  }
}

const stageFieldGroups = Array.from(document.querySelectorAll(".stage-fields"));
const materialsSection = document.getElementById("materials-section");
const jdField = composer.querySelector('[name="job_description"]');
const resumeField = composer.querySelector('[name="resume"]');

function syncStageFields() {
  const selected = composer.querySelector('input[name="stage_type"]:checked');
  const stage = selected ? selected.value : "intro_call";
  const isRecruiter = stage === "recruiter_screen";

  stageFieldGroups.forEach((group) => {
    group.classList.toggle("active", group.dataset.stage === stage);
  });

  submitBtnLabel.textContent = isRecruiter ? "Save to pipeline" : "Generate briefing";
  if (materialsSection) materialsSection.style.display = isRecruiter ? "none" : "";
  if (jdField) jdField.required = !isRecruiter;
  if (resumeField) resumeField.required = !isRecruiter;
}
composer.querySelectorAll('input[name="stage_type"]').forEach((input) => {
  input.addEventListener("change", syncStageFields);
});
syncStageFields();

resetBtn.addEventListener("click", () => {
  location.href = "/app";
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

// Pre-fill form from pipeline entry + URL params, save changes back on blur
(async () => {
  const params = new URLSearchParams(location.search);
  const pipelineId = params.get("pipeline_id");

  const fields = {
    company_name: document.querySelector("[name='company_name']"),
    job_title:    document.querySelector("[name='job_title']"),
    company_url:  document.querySelector("[name='company_url']"),
    role_level:   document.querySelector("[name='role_level']"),
    interviewer_name:  document.querySelector("[name='interviewer_name']"),
    interviewer_title: document.querySelector("[name='interviewer_title']"),
  };

  // Pre-fill from pipeline entry if we have an ID
  if (pipelineId && AUTH_TOKEN) {
    try {
      const res = await fetch(`/pipeline/entries/${pipelineId}`, {
        headers: { Authorization: `Bearer ${AUTH_TOKEN}` },
      });
      if (res.ok) {
        const entry = await res.json();
        if (fields.company_name && entry.company)    fields.company_name.value = entry.company;
        if (fields.job_title    && entry.role)       fields.job_title.value    = entry.role;
        if (fields.company_url  && entry.companyUrl) fields.company_url.value  = entry.companyUrl;
        if (fields.role_level   && entry.roleLevel)  fields.role_level.value   = entry.roleLevel;
      }
    } catch { /* non-fatal */ }
  }

  // URL params fill any gaps (company/role fallback, plus interviewer which isn't in pipeline)
  const p = { company: params.get("company"), role: params.get("role"),
               interviewer: params.get("interviewer"), interviewer_title: params.get("interviewer_title") };
  if (fields.company_name && p.company && !fields.company_name.value)         fields.company_name.value = p.company;
  if (fields.job_title    && p.role    && !fields.job_title.value)            fields.job_title.value    = p.role;
  if (fields.interviewer_name  && p.interviewer       && !fields.interviewer_name.value)  fields.interviewer_name.value  = p.interviewer;
  if (fields.interviewer_title && p.interviewer_title && !fields.interviewer_title.value) fields.interviewer_title.value = p.interviewer_title;

  // Save field changes back to the pipeline entry on blur
  if (pipelineId && AUTH_TOKEN) {
    const patchMap = {
      company_name: "company",
      job_title:    "role",
      company_url:  "companyUrl",
      role_level:   "roleLevel",
    };
    Object.entries(patchMap).forEach(([fieldName, pipelineKey]) => {
      const el = fields[fieldName];
      if (!el) return;
      el.addEventListener("blur", () => {
        const val = el.value.trim();
        fetch(`/pipeline/entries/${pipelineId}`, {
          method: "PATCH",
          headers: { Authorization: `Bearer ${AUTH_TOKEN}`, "Content-Type": "application/json" },
          body: JSON.stringify({ [pipelineKey]: val }),
        }).catch(() => {});
      });
    });
  }
})();
