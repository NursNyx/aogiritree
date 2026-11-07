const API_BASE = "http://127.0.0.1:8000";

const healthStatus = document.getElementById("healthStatus");
const checklistTable = document.getElementById("checklistTable");
const saveChecklistBtn = document.getElementById("saveChecklistBtn");
const conversationPreview = document.getElementById("conversationPreview");

let checklistState = { criteria: [] };

async function fetchHealth() {
  try {
    const response = await fetch(`${API_BASE}/health`);
    const payload = await response.json();
    healthStatus.textContent = `Backend: ${payload.status}`;
  } catch (error) {
    healthStatus.textContent = "Backend: unavailable";
  }
}

function renderChecklist() {
  checklistTable.innerHTML = "";
  checklistState.criteria.forEach((criterion) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${criterion.criterion_id}</td>
      <td>${criterion.type}</td>
      <td><input type="number" step="0.01" data-id="${criterion.criterion_id}" value="${criterion.weight}" /></td>
      <td>${criterion.na_allowed ? "yes" : "no"}</td>
      <td>${criterion.scale ? criterion.scale.join(", ") : "-"}</td>
    `;
    checklistTable.appendChild(row);
  });
}

async function fetchChecklist() {
  const response = await fetch(`${API_BASE}/api/checklist`);
  checklistState = await response.json();
  renderChecklist();
}

async function fetchDemoConversation() {
  const response = await fetch(`${API_BASE}/api/conversations/demo`);
  const payload = await response.json();
  conversationPreview.textContent = JSON.stringify(payload, null, 2);
}

saveChecklistBtn.addEventListener("click", async () => {
  const weightInputs = checklistTable.querySelectorAll("input[data-id]");
  const nextCriteria = checklistState.criteria.map((criterion) => {
    const targetInput = [...weightInputs].find(
      (input) => input.dataset.id === criterion.criterion_id,
    );

    return {
      ...criterion,
      weight: targetInput ? Number(targetInput.value) : criterion.weight,
    };
  });

  const response = await fetch(`${API_BASE}/api/checklist`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ criteria: nextCriteria }),
  });

  checklistState = await response.json();
  renderChecklist();
});

(async function init() {
  await fetchHealth();
  await fetchChecklist();
  await fetchDemoConversation();
})();
