const ACCESS_TOKEN = document.body.dataset.token || "";

const STAGE_LABELS = {
  intro_call: "Intro call",
  behavioral: "Behavioral round",
  technical: "Technical round",
  roleplay: "Roleplay / demo",
  panel: "Panel round",
  final: "Final round",
};

async function loadFullList() {
  const listEl = document.getElementById("saved-briefings-full-list");
  try {
    const res = await fetch("/briefings", {
      headers: { Authorization: `Bearer ${ACCESS_TOKEN}` },
    });
    if (!res.ok) return;
    const data = await res.json();
    const briefings = data.briefings || [];

    listEl.replaceChildren();
    if (briefings.length === 0) {
      const empty = document.createElement("div");
      empty.className = "db-empty";
      const p = document.createElement("p");
      p.textContent = "No briefings yet";
      empty.appendChild(p);
      listEl.appendChild(empty);
      return;
    }

    briefings.forEach((b) => {
      const row = document.createElement("div");
      row.className = "db-saved-row";

      const main = document.createElement("div");
      const company = document.createElement("p");
      company.className = "db-saved-row-title";
      company.textContent = b.company_name;
      const role = document.createElement("p");
      role.className = "db-saved-row-sub";
      role.textContent = b.job_title;
      main.appendChild(company);
      main.appendChild(role);

      const pill = document.createElement("span");
      pill.className = "db-stage-pill";
      pill.dataset.stage = b.stage_type;
      pill.textContent = STAGE_LABELS[b.stage_type] || b.stage_type;

      const date = document.createElement("span");
      date.className = "db-saved-row-date";
      date.textContent = new Date(b.created_at).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      });

      const download = document.createElement("a");
      download.className = "db-saved-download";
      download.href = `/briefings/${encodeURIComponent(b.id)}/report.pdf?token=${encodeURIComponent(ACCESS_TOKEN)}`;
      download.textContent = "Download PDF";

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "pl-card-delete";
      delBtn.textContent = "×";
      delBtn.title = "Delete briefing";
      delBtn.addEventListener("click", async () => {
        delBtn.disabled = true;
        const res = await fetch(`/briefings/${encodeURIComponent(b.id)}`, {
          method: "DELETE",
          headers: { Authorization: `Bearer ${ACCESS_TOKEN}` },
        });
        if (res.ok) {
          row.remove();
          if (listEl.children.length === 0) {
            const empty = document.createElement("div");
            empty.className = "db-empty";
            const p = document.createElement("p");
            p.textContent = "No briefings yet";
            empty.appendChild(p);
            listEl.appendChild(empty);
          }
        } else {
          delBtn.disabled = false;
        }
      });

      row.appendChild(main);
      row.appendChild(pill);
      row.appendChild(date);
      row.appendChild(download);
      row.appendChild(delBtn);
      listEl.appendChild(row);
    });
  } catch {
    // leave existing state on network failure
  }
}

loadFullList();

const settingsToggle = document.getElementById("settings-toggle");
const settingsMenu = document.getElementById("settings-menu");
if (settingsToggle && settingsMenu) {
  settingsToggle.addEventListener("click", () => {
    const open = settingsMenu.classList.toggle("open");
    settingsToggle.classList.toggle("open", open);
  });
}
