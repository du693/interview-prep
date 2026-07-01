const ACCESS_TOKEN = document.body.dataset.token || "";

// ── In-memory cache (source of truth once loaded) ─────────────────

let pipelineCache = [];

function loadRawPipeline() {
  return pipelineCache;
}

async function loadInterviews() {
  try {
    const res = await fetch("/interviews", { headers: { Authorization: `Bearer ${ACCESS_TOKEN}` } });
    return res.ok ? (await res.json()).interviews || [] : [];
  } catch { return []; }
}

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

function daysFromToday(dateStr) {
  return Math.round((new Date(dateStr) - new Date(todayStr())) / 86400000);
}

// ── API helpers ───────────────────────────────────────────────────

const API_HEADERS = () => ({
  Authorization: `Bearer ${ACCESS_TOKEN}`,
  "Content-Type": "application/json",
});

async function apiLoadEntries() {
  const res = await fetch("/pipeline/entries", { headers: API_HEADERS() });
  if (!res.ok) return [];
  const data = await res.json();
  return data.entries || [];
}

async function apiCreateEntry(entry) {
  const res = await fetch("/pipeline/entries", {
    method: "POST",
    headers: API_HEADERS(),
    body: JSON.stringify(entry),
  });
  if (!res.ok) return entry;
  return res.json();
}

async function apiUpdateEntry(entry) {
  fetch(`/pipeline/entries/${entry.id}`, {
    method: "PATCH",
    headers: API_HEADERS(),
    body: JSON.stringify(entry),
  }).catch(() => {});
}

async function apiDeleteEntry(id) {
  fetch(`/pipeline/entries/${id}`, {
    method: "DELETE",
    headers: API_HEADERS(),
  }).catch(() => {});
}

// ── Init: load from API, then sync any new interview entries ──────

async function initPipeline() {
  pipelineCache = await apiLoadEntries();

  // Auto-add any scheduled_interviews not yet in pipeline
  const interviews = await loadInterviews();
  const known = new Set(pipelineCache.map((p) => p.company.toLowerCase().trim()));
  const toCreate = [];

  for (const iv of interviews) {
    if (!iv.company) continue;
    const key = iv.company.toLowerCase().trim();

    if (known.has(key)) {
      // Backfill screeningDate on existing entries that don't have it
      const existing = pipelineCache.find((p) => p.company.toLowerCase().trim() === key);
      if (existing && !existing.screeningDate && iv.date) {
        existing.screeningDate = iv.date;
        apiUpdateEntry(existing);
      }
      continue;
    }

    const days = daysFromToday(iv.date);
    let status = "prep";
    if (days < 0) {
      status = iv.reviewed && iv.review?.followupSent ? "followup" : "waiting";
    }

    toCreate.push({
      company: iv.company,
      role: iv.role || "",
      status,
      screeningDate: iv.date || "",
      calEventId: iv.calEventId || "",
      rounds: [],
      addedAt: todayStr(),
    });
    known.add(key);
  }

  for (const entry of toCreate) {
    const created = await apiCreateEntry(entry);
    pipelineCache.push(created);
  }
}

// Returns the current pipeline (synchronous after init)
function getPipeline() {
  return pipelineCache;
}

// ── Mutations ────────────────────────────────────────────────────

function advanceStatus(id, newStatus) {
  const entry = pipelineCache.find((p) => p.id === id);
  if (entry) {
    entry.status = newStatus;
    if (newStatus === "next_round" && (!entry.rounds || entry.rounds.length === 0)) {
      entry.rounds = [{
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        type: "",
        date: "",
      }];
    }
    apiUpdateEntry(entry);
  }
  renderPipeline();
}

function deleteEntry(id) {
  pipelineCache = pipelineCache.filter((p) => p.id !== id);
  apiDeleteEntry(id);
  renderPipeline();
}

// ── Stage config ─────────────────────────────────────────────────

const STAGES = [
  { key: "prep",      label: "Prep" },
  { key: "screening", label: "Screening" },
  { key: "followup",  label: "Follow Up" },
  { key: "waiting",   label: "Waiting" },
  { key: "next_step", label: "Next Step" },
];

const STATUS_INDEX = {
  prep:       0,
  screening:  1,
  followup:   2,
  waiting:    3,
  next_step:  4,
  next_round: 4,
  rejected:   4,
  // legacy key migration
  intro_incoming:      0,
  post_interview_sent: 1,
  followup_sent:       2,
  waiting_response:    3,
  response_received:   4,
};

// ── Progress bar ─────────────────────────────────────────────────

function buildProgressBar(entry) {
  const status = entry.status;
  const currentIndex = STATUS_INDEX[status] ?? 0;
  const isRejected = status === "rejected";
  const isNextRound = status === "next_round";
  const screeningPending = (status === "screening" || status === "intro_incoming" || status === "post_interview_sent")
    && (!entry.screeningDate || daysFromToday(entry.screeningDate) > 0);

  const bar = document.createElement("div");
  bar.className = "pl-progress";

  STAGES.forEach((stage, i) => {
    const step = document.createElement("div");
    step.className = "pl-progress-step";

    if (i < currentIndex) step.classList.add("done");
    if (i === currentIndex) {
      step.classList.add("current");
      if (isRejected) step.classList.add("rejected");
      if (isNextRound) step.classList.add("next-round");
      if (screeningPending) step.classList.add("pending");
    }

    const dot = document.createElement("div");
    dot.className = "pl-progress-dot";
    if (i < currentIndex) {
      dot.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>`;
    }

    const label = document.createElement("span");
    label.className = "pl-progress-label";
    if (i === 4 && isNextRound) label.textContent = "Next Round";
    else if (i === 4 && isRejected) label.textContent = "Rejected";
    else label.textContent = stage.label;

    step.appendChild(dot);
    step.appendChild(label);
    bar.appendChild(step);
  });

  return bar;
}

// ── Action area ──────────────────────────────────────────────────

function mkBtn(text, variant, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = `pl-action-btn ${variant}`;
  btn.textContent = text;
  btn.addEventListener("click", onClick);
  return btn;
}

function buildActionArea(entry) {
  const area = document.createElement("div");
  area.className = "pl-action-area";

  switch (entry.status) {
    case "prep":
    case "intro_incoming": {
      const msg = document.createElement("p");
      msg.className = "pl-status-label";
      msg.textContent = "Prepping for your screening call.";
      area.appendChild(msg);
      const btns = document.createElement("div");
      btns.className = "pl-action-btns";
      const prepBtn = document.createElement("button");
      prepBtn.type = "button";
      prepBtn.className = "pl-action-btn primary";
      prepBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:13px;height:13px;margin-right:5px"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>Generate prep document`;
      prepBtn.addEventListener("click", () => {
        advanceStatus(entry.id, "screening");
        openBriefingModal(entry.company, entry.role, entry.id);
      });
      btns.appendChild(prepBtn);
      area.appendChild(btns);
      break;
    }

    case "screening":
    case "post_interview_sent": {
      const interviewDone = entry.screeningDate && daysFromToday(entry.screeningDate) <= 0;

      if (!interviewDone) {
        const msg = document.createElement("p");
        msg.className = "pl-status-label";
        if (entry.screeningDate) {
          const formatted = new Date(entry.screeningDate + "T00:00:00").toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
          msg.textContent = `Interview on ${formatted}.`;
        } else {
          msg.textContent = "Interview date not set — add it from upcoming events on your dashboard.";
        }
        area.appendChild(msg);

        const reschedRow = document.createElement("div");
        reschedRow.className = "pl-action-btns";
        const reschedBtn = document.createElement("button");
        reschedBtn.type = "button";
        reschedBtn.className = "pl-action-btn ghost";
        reschedBtn.textContent = "Rescheduled?";
        const reschedInput = document.createElement("input");
        reschedInput.type = "date";
        reschedInput.className = "pl-form-input";
        reschedInput.value = entry.screeningDate || "";
        reschedInput.style.display = "none";
        reschedBtn.addEventListener("click", () => {
          reschedInput.style.display = reschedInput.style.display === "none" ? "" : "none";
          if (reschedInput.style.display !== "none") reschedInput.focus();
        });
        reschedInput.addEventListener("change", () => {
          const e = pipelineCache.find((p) => p.id === entry.id);
          if (e) { e.screeningDate = reschedInput.value; apiUpdateEntry(e); renderPipeline(); }
        });
        reschedRow.appendChild(reschedBtn);
        reschedRow.appendChild(reschedInput);
        area.appendChild(reschedRow);
      } else {
        const msg = document.createElement("p");
        msg.className = "pl-status-label";
        msg.textContent = "Interview done — did you send a follow-up?";
        area.appendChild(msg);
        const btns = document.createElement("div");
        btns.className = "pl-action-btns";
        btns.appendChild(mkBtn("Yes, sent follow-up →", "primary", () => advanceStatus(entry.id, "followup")));
        btns.appendChild(mkBtn("No, skip to waiting →", "ghost", () => advanceStatus(entry.id, "waiting")));
        area.appendChild(btns);
      }
      break;
    }

    case "followup":
    case "followup_sent": {
      const msg = document.createElement("p");
      msg.className = "pl-status-label";
      msg.textContent = "Follow-up sent — waiting to hear back.";
      area.appendChild(msg);
      const btns = document.createElement("div");
      btns.className = "pl-action-btns";
      btns.appendChild(mkBtn("Now waiting →", "primary", () => advanceStatus(entry.id, "waiting")));
      area.appendChild(btns);
      break;
    }

    case "waiting":
    case "waiting_response": {
      const msg = document.createElement("p");
      msg.className = "pl-status-label";
      msg.textContent = "Waiting for their response.";
      area.appendChild(msg);
      const btns = document.createElement("div");
      btns.className = "pl-action-btns";
      btns.appendChild(mkBtn("Response received →", "primary", () => advanceStatus(entry.id, "next_step")));
      area.appendChild(btns);
      break;
    }

    case "next_step":
    case "response_received": {
      const msg = document.createElement("p");
      msg.className = "pl-status-label";
      msg.textContent = "Response received — what's the next step?";
      area.appendChild(msg);
      const btns = document.createElement("div");
      btns.className = "pl-action-btns";
      btns.appendChild(mkBtn("🎉 Next round", "success", () => advanceStatus(entry.id, "next_round")));
      btns.appendChild(mkBtn("✕ No further rounds", "danger", () => advanceStatus(entry.id, "rejected")));
      area.appendChild(btns);
      break;
    }

    case "next_round": {
      const topRow = document.createElement("div");
      topRow.className = "pl-action-btns";
      const badge = document.createElement("span");
      badge.className = "pl-outcome-badge next-round";
      badge.textContent = "🎉 Next round secured!";
      topRow.appendChild(badge);
      area.appendChild(topRow);
      area.appendChild(buildRoundsSection(entry));
      break;
    }

    case "rejected": {
      const topRow = document.createElement("div");
      topRow.className = "pl-action-btns";
      const badge = document.createElement("span");
      badge.className = "pl-outcome-badge rejected";
      badge.textContent = "No further rounds.";
      topRow.appendChild(badge);
      area.appendChild(topRow);
      const btns = document.createElement("div");
      btns.className = "pl-action-btns";
      btns.appendChild(mkBtn("Re-open", "ghost", () => advanceStatus(entry.id, "next_step")));
      area.appendChild(btns);
      break;
    }
  }

  return area;
}

// ── Rounds section ───────────────────────────────────────────────

function buildRoundRow(entry, round, num) {
  const row = document.createElement("div");
  row.className = "pl-round-row";

  const numLabel = document.createElement("span");
  numLabel.className = "pl-round-num";
  numLabel.textContent = `Round ${num}`;

  const typeSelect = document.createElement("select");
  typeSelect.className = "pl-round-select";
  [["", "Round type"], ["intro_call", "Intro call"], ["behavioral", "Behavioral"],
   ["technical", "Technical"], ["roleplay", "Roleplay / demo"], ["panel", "Panel"],
   ["final", "Final round"]].forEach(([val, text]) => {
    const opt = document.createElement("option");
    opt.value = val;
    opt.textContent = text;
    if (round.type === val) opt.selected = true;
    typeSelect.appendChild(opt);
  });
  typeSelect.addEventListener("change", () => {
    const p = pipelineCache.find((p) => p.id === entry.id);
    const r = p?.rounds?.find((r) => r.id === round.id);
    if (r) { r.type = typeSelect.value; apiUpdateEntry(p); }
  });

  const dateInput = document.createElement("input");
  dateInput.type = "date";
  dateInput.className = "pl-round-date-input";
  dateInput.value = round.date || "";
  dateInput.addEventListener("change", () => {
    const p = pipelineCache.find((p) => p.id === entry.id);
    const r = p?.rounds?.find((r) => r.id === round.id);
    if (r) { r.date = dateInput.value; apiUpdateEntry(p); }
  });

  const briefingBtn = document.createElement("button");
  briefingBtn.type = "button";
  briefingBtn.className = "pl-round-briefing-btn";
  briefingBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:12px;height:12px"><path d="M12 5v14"/><path d="M5 12h14"/></svg> Briefing`;
  briefingBtn.addEventListener("click", () => openBriefingModal(entry.company, entry.role, entry.id));

  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "pl-card-delete";
  delBtn.textContent = "×";
  delBtn.addEventListener("click", () => {
    const p = pipelineCache.find((p) => p.id === entry.id);
    if (p?.rounds) { p.rounds = p.rounds.filter((r) => r.id !== round.id); apiUpdateEntry(p); }
    renderPipeline();
  });

  row.appendChild(numLabel);
  row.appendChild(typeSelect);
  row.appendChild(dateInput);
  row.appendChild(briefingBtn);
  row.appendChild(delBtn);
  return row;
}

function buildRoundsSection(entry) {
  if (!entry.rounds) entry.rounds = [];

  const section = document.createElement("div");
  section.className = "pl-rounds";

  const header = document.createElement("div");
  header.className = "pl-rounds-header";
  const title = document.createElement("span");
  title.className = "pl-rounds-title";
  title.textContent = "Rounds";
  const addBtn = document.createElement("button");
  addBtn.type = "button";
  addBtn.className = "pl-add-round-btn";
  addBtn.textContent = "+ Add round";
  addBtn.addEventListener("click", () => {
    const p = pipelineCache.find((p) => p.id === entry.id);
    if (p) {
      if (!p.rounds) p.rounds = [];
      p.rounds.push({ id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, type: "", date: "" });
      apiUpdateEntry(p);
    }
    renderPipeline();
  });
  header.appendChild(title);
  header.appendChild(addBtn);
  section.appendChild(header);

  if (entry.rounds.length === 0) {
    const empty = document.createElement("p");
    empty.className = "pl-rounds-empty";
    empty.textContent = "No rounds added yet.";
    section.appendChild(empty);
  } else {
    entry.rounds.forEach((round, i) => section.appendChild(buildRoundRow(entry, round, i + 1)));
  }

  return section;
}

// ── Build card ───────────────────────────────────────────────────

function buildCard(entry) {
  const card = document.createElement("div");
  card.className = "pl-card";

  const head = document.createElement("div");
  head.className = "pl-card-head";

  const info = document.createElement("div");
  const company = document.createElement("p");
  company.className = "pl-company";
  company.textContent = entry.company;
  const role = document.createElement("p");
  role.className = "pl-role" + (entry.role ? "" : " pl-role--empty");
  role.textContent = entry.role || "Add role…";
  role.addEventListener("click", () => {
    const input = document.createElement("input");
    input.type = "text";
    input.className = "pl-role-input";
    input.value = entry.role || "";
    input.placeholder = "Add role…";
    role.replaceWith(input);
    input.focus();
    input.select();
    function commit() {
      const val = input.value.trim();
      const p = pipelineCache.find((e) => e.id === entry.id);
      if (p) { p.role = val; apiUpdateEntry(p); }
      renderPipeline();
    }
    input.addEventListener("blur", commit);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); input.blur(); }
      if (e.key === "Escape") { input.value = entry.role || ""; input.blur(); }
    });
  });
  info.appendChild(company);
  info.appendChild(role);

  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "pl-card-delete";
  delBtn.textContent = "×";
  delBtn.addEventListener("click", () => deleteEntry(entry.id));

  head.appendChild(info);
  head.appendChild(delBtn);
  card.appendChild(head);
  card.appendChild(buildProgressBar(entry));
  card.appendChild(buildActionArea(entry));

  return card;
}

// ── Render ───────────────────────────────────────────────────────

function renderPipeline() {
  const pipeline = getPipeline();
  const listEl = document.getElementById("pipeline-list");
  const emptyEl = document.getElementById("pipeline-empty");

  listEl.innerHTML = "";
  if (pipeline.length === 0) {
    emptyEl.style.display = "block";
    return;
  }
  emptyEl.style.display = "none";
  pipeline.forEach((entry) => listEl.appendChild(buildCard(entry)));
}

// ── Add company modal ────────────────────────────────────────────

const addModalOverlay = document.getElementById("add-modal-overlay");

document.getElementById("add-company-btn").addEventListener("click", () => {
  addModalOverlay.classList.add("active");
  document.documentElement.style.overflow = "hidden";
  document.body.style.overflow = "hidden";
});

function closeAddModal() {
  addModalOverlay.classList.remove("active");
  document.documentElement.style.overflow = "";
  document.body.style.overflow = "";
}

document.getElementById("add-modal-close").addEventListener("click", closeAddModal);
document.getElementById("add-modal-cancel").addEventListener("click", closeAddModal);
addModalOverlay.addEventListener("click", (e) => { if (e.target === addModalOverlay) closeAddModal(); });

document.getElementById("add-company-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const company = document.getElementById("add-company-name").value.trim();
  const role = document.getElementById("add-company-role").value.trim();
  const status = document.getElementById("add-company-stage").value;
  if (!company) return;

  const created = await apiCreateEntry({
    company, role, status,
    screeningDate: "", calEventId: "", rounds: [], addedAt: todayStr(),
  });
  pipelineCache.push(created);
  document.getElementById("add-company-form").reset();
  closeAddModal();
  renderPipeline();
});

// ── Briefing modal ───────────────────────────────────────────────

const briefingModalOverlay = document.getElementById("briefing-modal-overlay");
const briefingModalFrame = document.getElementById("briefing-modal-frame");

function openBriefingModal(company = "", role = "", pipelineId = "") {
  const params = new URLSearchParams({ embed: "1", _: Date.now() });
  if (company) params.set("company", company);
  if (role) params.set("role", role);
  if (pipelineId) params.set("pipeline_id", pipelineId);
  briefingModalFrame.src = `/app?${params}`;
  briefingModalOverlay.classList.add("active");
  document.documentElement.style.overflow = "hidden";
  document.body.style.overflow = "hidden";
}

function closeBriefingModal() {
  briefingModalOverlay.classList.remove("active");
  document.documentElement.style.overflow = "";
  document.body.style.overflow = "";
  briefingModalFrame.src = "";
}

briefingModalOverlay.addEventListener("click", (e) => {
  if (e.target === briefingModalOverlay) closeBriefingModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (briefingModalOverlay.classList.contains("active")) closeBriefingModal();
    if (addModalOverlay.classList.contains("active")) closeAddModal();
  }
});
window.addEventListener("message", (e) => {
  if (e.origin !== window.location.origin) return;
  if (e.data?.type === "close-briefing-modal") closeBriefingModal();
});

// ── Settings dropdown ────────────────────────────────────────────

const settingsToggle = document.getElementById("settings-toggle");
const settingsMenu = document.getElementById("settings-menu");
settingsToggle.addEventListener("click", () => {
  const open = settingsMenu.classList.toggle("open");
  settingsToggle.classList.toggle("open", open);
});

// ── Cal event sync ───────────────────────────────────────────────

async function syncCalendarDates() {
  const toCheck = pipelineCache.filter(
    (e) => e.calEventId && (e.status === "prep" || e.status === "screening" || e.status === "intro_incoming" || e.status === "post_interview_sent")
  );
  if (!toCheck.length) return;

  let changed = false;
  await Promise.all(toCheck.map(async (entry) => {
    try {
      const res = await fetch(`/calendar/event/${encodeURIComponent(entry.calEventId)}`, {
        headers: { Authorization: `Bearer ${ACCESS_TOKEN}` },
      });
      if (!res.ok) return;
      const { date } = await res.json();
      if (date && date !== entry.screeningDate) {
        entry.screeningDate = date;
        apiUpdateEntry(entry);
        changed = true;
      }
    } catch { /* silent */ }
  }));

  if (changed) renderPipeline();
}

// ── Init ─────────────────────────────────────────────────────────

async function init() {
  await initPipeline();
  renderPipeline();
  syncCalendarDates();
}

init();
