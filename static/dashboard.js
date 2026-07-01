const ACCESS_TOKEN = document.body.dataset.token || "";

const STAGE_LABELS = {
  intro_call: "Intro call",
  behavioral: "Behavioral round",
  technical: "Technical round",
  roleplay: "Roleplay / demo",
  panel: "Panel round",
  final: "Final round",
};

const GOAL_APPS = 3;

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

function resetGoalsIfNewDay() {
  const lastDate = localStorage.getItem("last_goal_date");
  const today = todayStr();
  if (lastDate !== today) {
    localStorage.setItem("goal_apps_today", "0");
    localStorage.setItem("last_goal_date", today);
  }
}

function getInt(key) {
  return parseInt(localStorage.getItem(key) || "0", 10) || 0;
}

// ── In-memory caches ─────────────────────────────────────────────
let interviewsCache = [];
let followupsCache = [];

function getInterviews() { return interviewsCache; }
function getFollowUps()  { return followupsCache; }

const _apiHeaders = () => ({ Authorization: `Bearer ${ACCESS_TOKEN}`, "Content-Type": "application/json" });

async function _apiLoadInterviews() {
  try {
    const res = await fetch("/interviews", { headers: _apiHeaders() });
    return res.ok ? (await res.json()).interviews || [] : [];
  } catch { return []; }
}

async function _apiLoadFollowups() {
  try {
    const res = await fetch("/followups", { headers: _apiHeaders() });
    return res.ok ? (await res.json()).followups || [] : [];
  } catch { return []; }
}

async function _apiCreateInterview(entry) {
  try {
    const res = await fetch("/interviews", { method: "POST", headers: _apiHeaders(), body: JSON.stringify(entry) });
    return res.ok ? await res.json() : entry;
  } catch { return entry; }
}

function _apiUpdateInterview(entry) {
  fetch(`/interviews/${entry.id}`, { method: "PATCH", headers: _apiHeaders(), body: JSON.stringify(entry) }).catch(() => {});
}

function _apiDeleteInterview(id) {
  fetch(`/interviews/${id}`, { method: "DELETE", headers: _apiHeaders() }).catch(() => {});
}

async function _apiCreateFollowup(entry) {
  try {
    const res = await fetch("/followups", { method: "POST", headers: _apiHeaders(), body: JSON.stringify(entry) });
    return res.ok ? await res.json() : entry;
  } catch { return entry; }
}

function _apiUpdateFollowup(entry) {
  fetch(`/followups/${entry.id}`, { method: "PATCH", headers: _apiHeaders(), body: JSON.stringify(entry) }).catch(() => {});
}

function _apiDeleteFollowup(id) {
  fetch(`/followups/${id}`, { method: "DELETE", headers: _apiHeaders() }).catch(() => {});
}

async function initDashboardData() {
  [interviewsCache, followupsCache] = await Promise.all([_apiLoadInterviews(), _apiLoadFollowups()]);
}

function daysUntil(dateStr) {
  const today = new Date(todayStr());
  const target = new Date(dateStr);
  return Math.round((target - today) / 86400000);
}


function renderGoalBar(fillEl, count, goal) {
  const pct = Math.min(100, (count / goal) * 100);
  fillEl.style.width = `${pct}%`;
  fillEl.classList.toggle("complete", count >= goal);
}

const RING_CIRCUMFERENCE = 238.76;
let _cachedGmailCount = null;

function renderAppsGoal(gmailCount = null) {
  if (gmailCount !== null) _cachedGmailCount = gmailCount;
  const count = _cachedGmailCount !== null ? _cachedGmailCount : getInt("goal_apps_today");
  document.getElementById("goal-apps-count").textContent = count;
  const pct = Math.min(1, count / GOAL_APPS);
  const ring = document.getElementById("goal-apps-ring");
  ring.style.strokeDashoffset = RING_CIRCUMFERENCE * (1 - pct);
  ring.classList.toggle("complete", count >= GOAL_APPS);
}


function buildInterviewRow(interview) {
  const row = document.createElement("div");
  row.className = "db-interview-row";

  const main = document.createElement("div");
  main.className = "db-interview-main";
  const company = document.createElement("p");
  company.className = "db-interview-company";
  company.textContent = interview.company;
  const role = document.createElement("p");
  role.className = "db-interview-role";
  role.textContent = interview.role;
  main.appendChild(company);
  main.appendChild(role);

  const pill = document.createElement("span");
  pill.className = "db-stage-pill";
  pill.dataset.stage = interview.stage || "";
  pill.textContent = STAGE_LABELS[interview.stage] || "";

  const dateEl = document.createElement("span");
  dateEl.className = "db-interview-date";
  dateEl.textContent = new Date(interview.date + "T00:00:00").toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });

  const days = daysUntil(interview.date);
  const daysEl = document.createElement("span");
  daysEl.className = "db-interview-days";
  daysEl.textContent = days === 0 ? "Today" : days < 0 ? `${-days}d ago` : `in ${days}d`;

  const isPast = days < 0;
  const isReviewed = !!interview.reviewed;

  const midSlot = document.createElement("span");
  if (!isPast) {
    const preppedBtn = document.createElement("button");
    preppedBtn.type = "button";
    preppedBtn.className = "db-prepped-toggle";
    preppedBtn.classList.toggle("is-prepped", !!interview.prepped);
    preppedBtn.textContent = interview.prepped ? "✓ Prepped" : "Mark prepped";
    preppedBtn.addEventListener("click", () => togglePrepped(interview.id));
    midSlot.appendChild(preppedBtn);
  }

  const actions = document.createElement("div");
  actions.className = "db-interview-actions";

  if (isPast) {
    if (isReviewed) {
      const reviewedLabel = document.createElement("span");
      reviewedLabel.className = "db-reviewed-label";
      reviewedLabel.textContent = "✓ Reviewed";
      actions.appendChild(reviewedLabel);
    } else {
      const reviewBtn = document.createElement("button");
      reviewBtn.type = "button";
      reviewBtn.className = "db-review-btn";
      reviewBtn.textContent = "Review";
      reviewBtn.addEventListener("click", () => openReviewModal(interview));
      actions.appendChild(reviewBtn);
    }
  } else {
    const prepBtn = document.createElement("button");
    prepBtn.type = "button";
    prepBtn.className = "db-prep-btn";
    prepBtn.textContent = "Prep now";
    prepBtn.addEventListener("click", () => openBriefingModal(interview.company, interview.role));
    actions.appendChild(prepBtn);
  }

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "db-delete-btn";
  deleteBtn.textContent = "×";
  deleteBtn.addEventListener("click", () => deleteInterview(interview.id));
  actions.appendChild(deleteBtn);

  row.appendChild(main);
  row.appendChild(pill);
  row.appendChild(dateEl);
  row.appendChild(daysEl);
  row.appendChild(midSlot);
  row.appendChild(actions);
  return row;
}

function buildFollowupRow(followup) {
  const row = document.createElement("div");
  row.className = "db-interview-row db-followup-row";

  const main = document.createElement("div");
  main.className = "db-interview-main";
  const company = document.createElement("p");
  company.className = "db-interview-company";
  company.textContent = followup.company;
  const sub = document.createElement("p");
  sub.className = "db-interview-role";
  sub.textContent = followup.person ? `Follow up: ${followup.person}` : "Follow up reminder";
  main.appendChild(company);
  main.appendChild(sub);

  const typePill = document.createElement("span");
  typePill.className = "db-followup-pill";
  typePill.textContent = "Follow up";

  const dateEl = document.createElement("span");
  dateEl.className = "db-interview-date";
  dateEl.textContent = new Date(followup.date + "T00:00:00").toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });

  const days = daysUntil(followup.date);
  const daysEl = document.createElement("span");
  daysEl.className = "db-interview-days";
  daysEl.textContent = days === 0 ? "Today" : days < 0 ? `${-days}d ago` : `in ${days}d`;

  const isDone = !!followup.completed;
  if (isDone) row.classList.add("is-done");

  const checkBtn = document.createElement("button");
  checkBtn.type = "button";
  checkBtn.className = "db-followup-check";
  checkBtn.classList.toggle("is-done", isDone);
  checkBtn.textContent = isDone ? "✓ Done" : "Mark done";
  checkBtn.addEventListener("click", () => toggleFollowupComplete(followup.id));

  const actions = document.createElement("div");
  actions.className = "db-interview-actions";
  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "db-delete-btn";
  deleteBtn.textContent = "×";
  deleteBtn.addEventListener("click", () => deleteFollowup(followup.id));
  actions.appendChild(deleteBtn);

  row.appendChild(main);
  row.appendChild(typePill);
  row.appendChild(dateEl);
  row.appendChild(daysEl);
  row.appendChild(checkBtn);
  row.appendChild(actions);
  return row;
}

function renderEventList() {
  const interviews = getInterviews().map((i) => ({ ...i, _type: "interview" }));
  const followups = getFollowUps().map((f) => ({ ...f, _type: "followup" }));
  const allEvents = [...interviews, ...followups]
    .filter((ev) => daysUntil(ev.date) >= 0)
    .sort((a, b) => a.date.localeCompare(b.date));

  const listEl = document.getElementById("interview-list");
  const emptyEl = document.getElementById("interview-empty");

  if (allEvents.length === 0) {
    emptyEl.style.display = "block";
    listEl.innerHTML = "";
    return;
  }
  emptyEl.style.display = "none";
  listEl.innerHTML = "";

  for (const ev of allEvents) {
    listEl.appendChild(ev._type === "followup" ? buildFollowupRow(ev) : buildInterviewRow(ev));
  }
}

function togglePrepped(id) {
  const target = interviewsCache.find((i) => i.id === id);
  if (target) { target.prepped = !target.prepped; _apiUpdateInterview(target); }
  renderAll();
}

function deleteInterview(id) {
  interviewsCache = interviewsCache.filter((i) => i.id !== id);
  _apiDeleteInterview(id);
  renderAll();
}

function toggleFollowupComplete(id) {
  const target = followupsCache.find((f) => f.id === id);
  if (target) { target.completed = !target.completed; _apiUpdateFollowup(target); }
  renderAll();
}

function deleteFollowup(id) {
  followupsCache = followupsCache.filter((f) => f.id !== id);
  _apiDeleteFollowup(id);
  renderAll();
}

function _apiPatchPipelineRole(id, role) {
  fetch(`/pipeline/entries/${id}`, {
    method: "PATCH", headers: _apiHeaders(), body: JSON.stringify({ role }),
  }).catch(() => {});
}

async function fetchPipelineEntries() {
  try {
    const res = await fetch("/pipeline/entries", { headers: { Authorization: `Bearer ${ACCESS_TOKEN}` } });
    if (!res.ok) return [];
    const data = await res.json();
    return data.entries || [];
  } catch { return []; }
}

function renderActiveConversations(pipelineEntries) {
  const active = new Set();

  getInterviews().forEach((iv) => {
    if (iv.company && daysUntil(iv.date) >= 0) active.add(iv.company.toLowerCase().trim());
  });

  pipelineEntries.forEach((p) => {
    if (p.company && p.status !== "rejected") active.add(p.company.toLowerCase().trim());
  });

  const count = active.size;
  document.getElementById("stat-active-count").textContent = count || "—";
  document.getElementById("stat-active-hint").textContent =
    count === 1 ? "Active company" : count > 1 ? "Active companies" : "No active conversations";
}

function renderPipelineRoles(pipelineEntries) {
  const list = document.getElementById("pipeline-roles-list");
  if (!list) return;
  const entries = pipelineEntries.filter((p) => p.status !== "rejected");
  list.replaceChildren();
  if (entries.length === 0) {
    const empty = document.createElement("div");
    empty.className = "db-empty";
    const p = document.createElement("p");
    p.textContent = "No active roles";
    empty.appendChild(p);
    list.appendChild(empty);
    return;
  }
  entries.forEach((entry) => {
    const item = document.createElement("div");
    item.className = "db-pipeline-role";

    function attachRoleEl(currentVal) {
      const role = document.createElement("p");
      role.className = "db-pipeline-role-title" + (currentVal ? "" : " db-pipeline-role-title--empty");
      role.textContent = currentVal || "Add role…";
      role.addEventListener("click", () => {
        const input = document.createElement("input");
        input.type = "text";
        input.className = "db-pipeline-role-input";
        input.value = currentVal || "";
        input.placeholder = "Add role…";
        role.replaceWith(input);
        input.focus();
        input.select();
        function commit() {
          const val = input.value.trim();
          entry.role = val;
          _apiPatchPipelineRole(entry.id, val);
          input.replaceWith(attachRoleEl(val));
        }
        input.addEventListener("blur", commit);
        input.addEventListener("keydown", (e) => {
          if (e.key === "Enter") { e.preventDefault(); input.blur(); }
          if (e.key === "Escape") { input.replaceWith(attachRoleEl(currentVal)); }
        });
      });
      return role;
    }

    const company = document.createElement("p");
    company.className = "db-pipeline-role-company";
    company.textContent = entry.company || "";
    item.appendChild(attachRoleEl(entry.role));
    item.appendChild(company);
    list.appendChild(item);
  });
}

async function renderDashboardPipeline() {
  const entries = await fetchPipelineEntries();
  renderActiveConversations(entries);
  renderPipelineRoles(entries);
}

function renderAll(gmailCount = null) {
  renderAppsGoal(gmailCount);
  renderEventList();
}



const interviewForm = document.getElementById("interview-form");
const addInterviewBtn = document.getElementById("add-interview-btn");
const cancelInterviewBtn = document.getElementById("cancel-interview-btn");

function openInterviewForm() {
  interviewForm.style.display = "block";
  interviewForm.scrollIntoView({ behavior: "smooth", block: "center" });
}

addInterviewBtn.addEventListener("click", openInterviewForm);
cancelInterviewBtn.addEventListener("click", () => {
  interviewForm.style.display = "none";
  interviewForm.reset();
});

interviewForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const company = document.getElementById("interview-company").value.trim();
  const role = document.getElementById("interview-role").value.trim();
  const date = document.getElementById("interview-date").value;
  const stage = document.getElementById("interview-stage").value;
  if (!company || !role || !date) return;

  const created = await _apiCreateInterview({ company, role, date, stage, prepped: false, calEventId: "", reviewed: false });
  interviewsCache.push(created);

  interviewForm.style.display = "none";
  interviewForm.reset();
  renderAll();
});

const gmailCard = document.getElementById("gmail-card");
const gmailDismiss = document.getElementById("gmail-dismiss");

if (localStorage.getItem("gmail_banner_dismissed") === "true") {
  gmailCard.style.display = "none";
}

gmailDismiss.addEventListener("click", () => {
  localStorage.setItem("gmail_banner_dismissed", "true");
  gmailCard.style.display = "none";
});

const gmailConnectBtn = document.getElementById("gmail-connect-btn");
const gmailCardTitle = document.getElementById("gmail-card-title");
const gmailCardBody = document.getElementById("gmail-card-body");
const statApplicationsValue = document.getElementById("stat-applications-value");
const statApplicationsHint = document.getElementById("stat-applications-hint");
const rescanLink = document.getElementById("rescan-link");

gmailConnectBtn.addEventListener("click", () => {
  window.location.href = "/auth/gmail";
});

rescanLink.addEventListener("click", async () => {
  rescanLink.textContent = "Scanning...";
  rescanLink.style.pointerEvents = "none";
  try {
    const res = await fetch("/gmail/rescan", {
      method: "POST",
      headers: { Authorization: `Bearer ${ACCESS_TOKEN}` },
    });
    if (!res.ok) {
      window.location.href = "/auth/gmail";
      return;
    }
  } catch {
    rescanLink.textContent = "Rescan now";
    rescanLink.style.pointerEvents = "";
    return;
  }
  const pollStart = Date.now();
  const previousScannedAt = statApplicationsHint.dataset.lastScannedAt || "";
  const poll = setInterval(async () => {
    await loadGmailStatus();
    const newScannedAt = statApplicationsHint.dataset.lastScannedAt || "";
    if (newScannedAt !== previousScannedAt || Date.now() - pollStart > 90000) {
      clearInterval(poll);
      rescanLink.textContent = "Rescan now";
      rescanLink.style.pointerEvents = "";
    }
  }, 5000);
});

async function loadGmailStatus() {
  try {
    const dayStart = new Date();
    dayStart.setHours(0, 0, 0, 0);
    const res = await fetch(`/gmail/status?day_start=${encodeURIComponent(dayStart.toISOString())}`, {
      headers: { Authorization: `Bearer ${ACCESS_TOKEN}` },
    });
    if (!res.ok) return;
    const data = await res.json();

    if (!data.connected) {
      statApplicationsValue.textContent = "—";
      statApplicationsHint.textContent = "Connect Gmail to track";
      return;
    }

    statApplicationsValue.textContent = String(data.application_count);
    statApplicationsHint.textContent = "Total tracked since connecting";
    statApplicationsHint.dataset.lastScannedAt = data.last_scanned_at || "";
    renderAppsGoal(data.applications_today);

    gmailCardTitle.textContent = "Gmail connected";
    gmailCardBody.textContent = `Scanning ${data.email_address} for application confirmations.`;
    rescanLink.style.display = "inline";
    document.getElementById("gmail-reconnect-link").style.display = "block";
  } catch {
    // leave existing state on network failure
  }
}

const briefingModalOverlay = document.getElementById("briefing-modal-overlay");
const briefingModalFrame = document.getElementById("briefing-modal-frame");

function openBriefingModal(company = "", role = "") {
  const params = new URLSearchParams({ embed: "1", _: Date.now() });
  if (company) params.set("company", company);
  if (role) params.set("role", role);
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

document.getElementById("new-briefing-btn").addEventListener("click", () => openBriefingModal());
briefingModalOverlay.addEventListener("click", (event) => {
  if (event.target === briefingModalOverlay) closeBriefingModal();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && briefingModalOverlay.classList.contains("active")) {
    closeBriefingModal();
  }
});
window.addEventListener("message", (event) => {
  if (event.origin !== window.location.origin) return;
  if (event.data && event.data.type === "close-briefing-modal") closeBriefingModal();
});

// Review modal

let currentReviewInterview = null;

const reviewModalOverlay = document.getElementById("review-modal-overlay");

function openReviewModal(interview) {
  currentReviewInterview = interview;
  document.getElementById("review-modal-title").textContent = interview.company;
  const sub = [interview.role, STAGE_LABELS[interview.stage]].filter(Boolean).join(" · ");
  document.getElementById("review-modal-sub").textContent = sub;
  document.getElementById("review-notes").value = "";
  document.getElementById("review-next-date").value = "";
  document.getElementById("review-followup-person").value = "";
  const noRadio = document.querySelector('input[name="followup_sent"][value="no"]');
  if (noRadio) noRadio.checked = true;
  reviewModalOverlay.classList.add("active");
  document.documentElement.style.overflow = "hidden";
  document.body.style.overflow = "hidden";
}

function closeReviewModal() {
  reviewModalOverlay.classList.remove("active");
  document.documentElement.style.overflow = "";
  document.body.style.overflow = "";
  currentReviewInterview = null;
}

document.getElementById("review-modal-close").addEventListener("click", closeReviewModal);
document.getElementById("review-cancel-btn").addEventListener("click", closeReviewModal);
reviewModalOverlay.addEventListener("click", (e) => {
  if (e.target === reviewModalOverlay) closeReviewModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && reviewModalOverlay.classList.contains("active")) closeReviewModal();
});

document.getElementById("review-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!currentReviewInterview) return;

  const notes = document.getElementById("review-notes").value.trim();
  const followupSent = document.querySelector('input[name="followup_sent"]:checked')?.value === "yes";
  const nextDate = document.getElementById("review-next-date").value;
  const followupPerson = document.getElementById("review-followup-person").value.trim();

  const target = interviewsCache.find((i) => i.id === currentReviewInterview.id);
  if (target) {
    target.reviewed = true;
    target.review = { notes, followupSent, nextDate, followupPerson };
    _apiUpdateInterview(target);
  }

  if (nextDate) {
    const created = await _apiCreateFollowup({
      type: "followup",
      company: currentReviewInterview.company,
      role: currentReviewInterview.role,
      person: followupPerson,
      date: nextDate,
      notes,
      completed: false,
    });
    followupsCache.push(created);

    if (followupPerson || notes) {
      const description = notes
        ? `${notes}\n\nFollow up regarding ${currentReviewInterview.role || "role"} at ${currentReviewInterview.company}`
        : `Follow up regarding ${currentReviewInterview.role || "role"} at ${currentReviewInterview.company}`;
      try {
        await fetch("/calendar/create-event", {
          method: "POST",
          headers: { Authorization: `Bearer ${ACCESS_TOKEN}`, "Content-Type": "application/json" },
          body: JSON.stringify({
            title: followupPerson
              ? `Follow up with ${followupPerson} — ${currentReviewInterview.company}`
              : `Follow up — ${currentReviewInterview.company}`,
            date: nextDate,
            description,
          }),
        });
      } catch {
        // local reminder already saved, calendar is best-effort
      }
    }
  }

  closeReviewModal();
  renderAll();
});

// Calendar modal
const calModalOverlay = document.getElementById("cal-modal-overlay");
const calEventsList = document.getElementById("cal-events-list");

function formatEventTime(isoStr) {
  if (!isoStr) return "";
  if (!isoStr.includes("T")) {
    return new Date(isoStr).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  }
  return new Date(isoStr).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function formatEventDate(isoStr) {
  if (!isoStr) return "";
  const d = new Date(isoStr.includes("T") ? isoStr : isoStr + "T00:00:00");
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === tomorrow.toDateString()) return "Tomorrow";
  return d.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
}

function renderCalendarEvents(events) {
  calEventsList.innerHTML = "";
  if (!events.length) {
    calEventsList.innerHTML = '<p class="cal-empty">No upcoming events in the next 14 days.</p>';
    return;
  }

  const grouped = {};
  events.forEach((ev) => {
    const dateKey = formatEventDate(ev.start);
    if (!grouped[dateKey]) grouped[dateKey] = [];
    grouped[dateKey].push(ev);
  });

  Object.entries(grouped).forEach(([dateLabel, evs]) => {
    const groupEl = document.createElement("p");
    groupEl.className = "cal-date-group";
    groupEl.textContent = dateLabel;
    calEventsList.appendChild(groupEl);

    evs.forEach((ev) => {
      const card = document.createElement("div");
      card.className = "cal-event-card";

      const title = document.createElement("p");
      title.className = "cal-event-title";
      title.textContent = ev.title;

      const meta = document.createElement("p");
      meta.className = "cal-event-meta";
      const timeSpan = document.createElement("span");
      timeSpan.textContent = formatEventTime(ev.start);
      meta.appendChild(timeSpan);
      if (ev.company) {
        const companySpan = document.createElement("span");
        companySpan.className = "cal-event-company-tag";
        companySpan.textContent = ev.company;
        meta.appendChild(companySpan);
      }
      if (ev.attendees && ev.attendees.length) {
        const attendeeSpan = document.createElement("span");
        attendeeSpan.textContent = ev.attendees.slice(0, 2).map((a) => a.name || a.email).join(", ");
        meta.appendChild(attendeeSpan);
      }

      const actions = document.createElement("div");
      actions.className = "cal-event-actions";

      const briefingBtn = document.createElement("button");
      briefingBtn.type = "button";
      briefingBtn.className = "cal-action-briefing";
      briefingBtn.textContent = "Generate briefing";
      briefingBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const interviewer = ev.attendees && ev.attendees[0] ? ev.attendees[0].name || ev.attendees[0].email : "";
        const params = new URLSearchParams({
          embed: "1",
          _: Date.now(),
          ...(ev.company ? { company: ev.company } : {}),
          ...(interviewer ? { interviewer } : {}),
        });
        briefingModalFrame.src = `/app?${params}`;
        briefingModalOverlay.classList.add("active");
        document.documentElement.style.overflow = "hidden";
        document.body.style.overflow = "hidden";
        calModalOverlay.classList.remove("active");
      });

      const interviewBtn = document.createElement("button");
      interviewBtn.type = "button";
      interviewBtn.className = "cal-action-interview";
      interviewBtn.textContent = "Mark as interview";
      interviewBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const dateStr = ev.start ? ev.start.slice(0, 10) : todayStr();
        const created = await _apiCreateInterview({
          company: ev.company || ev.title,
          role: "",
          date: dateStr,
          stage: "",
          prepped: false,
          calEventId: ev.id || "",
          reviewed: false,
        });
        interviewsCache.push(created);
        renderAll();
        calModalOverlay.classList.remove("active");
      });

      actions.appendChild(briefingBtn);
      actions.appendChild(interviewBtn);
      card.appendChild(title);
      card.appendChild(meta);
      card.appendChild(actions);

      card.addEventListener("click", () => {
        const wasSelected = card.classList.contains("selected");
        calEventsList.querySelectorAll(".cal-event-card").forEach((c) => c.classList.remove("selected"));
        if (!wasSelected) card.classList.add("selected");
      });

      calEventsList.appendChild(card);
    });
  });
}

async function openCalendarModal() {
  calModalOverlay.classList.add("active");
  calEventsList.innerHTML = '<p class="cal-loading">Loading events...</p>';
  try {
    const res = await fetch("/calendar/events", {
      headers: { Authorization: `Bearer ${ACCESS_TOKEN}` },
    });
    if (!res.ok) {
      calEventsList.innerHTML = '<p class="cal-empty">Could not load calendar. Make sure Gmail is connected and reconnect to grant calendar access.</p>';
      return;
    }
    const data = await res.json();
    renderCalendarEvents(data.events || []);
  } catch {
    calEventsList.innerHTML = '<p class="cal-empty">Failed to load events.</p>';
  }
}

document.getElementById("import-calendar-btn").addEventListener("click", openCalendarModal);
document.getElementById("cal-modal-close").addEventListener("click", () => calModalOverlay.classList.remove("active"));
calModalOverlay.addEventListener("click", (e) => { if (e.target === calModalOverlay) calModalOverlay.classList.remove("active"); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && calModalOverlay.classList.contains("active")) calModalOverlay.classList.remove("active");
});

// Settings dropdown
const settingsToggle = document.getElementById("settings-toggle");
const settingsMenu = document.getElementById("settings-menu");
settingsToggle.addEventListener("click", () => {
  const open = settingsMenu.classList.toggle("open");
  settingsToggle.classList.toggle("open", open);
});

resetGoalsIfNewDay();
renderAll();
loadGmailStatus();

(async () => {
  await initDashboardData();
  renderAll();
  renderDashboardPipeline();
})();
