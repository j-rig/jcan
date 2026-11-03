const PID_LABELS = {
  rpm: "RPM",
  speed: "Speed",
  coolant_temp: "Coolant Temp",
  throttle_position: "Throttle Position",
  engine_load: "Engine Load",
  intake_air_temp: "Intake Air Temp",
};

function setupTabs() {
  const buttons = document.querySelectorAll(".tab-button");
  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      button.classList.add("active");
      document.getElementById(`tab-${button.dataset.tab}`).classList.add("active");
      if (button.dataset.tab === "diagnostics") loadDtcs();
      if (button.dataset.tab === "vehicles") loadVehicles();
    });
  });
}

function renderGauge(pid, value, unit) {
  let el = document.getElementById(`gauge-${pid}`);
  if (!el) {
    el = document.createElement("div");
    el.id = `gauge-${pid}`;
    el.className = "gauge";
    el.innerHTML = `<div class="gauge-label">${PID_LABELS[pid] || pid}</div><div class="gauge-value"></div>`;
    document.getElementById("gauges").appendChild(el);
  }
  el.dataset.lastUpdate = Date.now();
  el.querySelector(".gauge-value").textContent = `${value} ${unit}`;
  el.classList.remove("stale");
}

function markStaleGauges() {
  const now = Date.now();
  document.querySelectorAll(".gauge").forEach((el) => {
    if (now - Number(el.dataset.lastUpdate || 0) > 5000) {
      el.classList.add("stale");
    }
  });
}

function setupWebSocket() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "reading") {
      renderGauge(message.pid, message.value, message.unit);
    } else if (message.type === "status") {
      showConnectionStatus(message.status);
    }
  };
  setInterval(markStaleGauges, 1000);
}

function showConnectionStatus(status) {
  const banner = document.getElementById("connection-banner");
  if (status === "connected") {
    banner.classList.add("hidden");
    return;
  }
  banner.textContent = `Connection issue: ${status}`;
  banner.classList.remove("hidden");
}

function vehicleLabel(row) {
  if (row.make) {
    return `${row.year} ${row.make} ${row.model}`.trim();
  }
  return row.vin || "";
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

async function loadDtcs() {
  const response = await fetch("/dtcs");
  const events = await response.json();
  const tbody = document.querySelector("#dtc-table tbody");
  tbody.innerHTML = "";
  for (const event of events) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${event.code}</td>
      <td>${event.description}</td>
      <td>${vehicleLabel(event)}</td>
      <td>${event.first_seen}</td>
      <td><textarea data-id="${event.id}">${event.notes || ""}</textarea></td>
    `;
    tbody.appendChild(row);
  }
  tbody.querySelectorAll("textarea").forEach((textarea) => {
    textarea.addEventListener("blur", async () => {
      await fetch(`/dtcs/${textarea.dataset.id}/notes`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: textarea.value }),
      });
    });
  });
}

async function loadVehicles() {
  const response = await fetch("/vehicles");
  const vehicles = await response.json();
  const tbody = document.querySelector("#vehicle-table tbody");
  tbody.innerHTML = "";
  for (const vehicle of vehicles) {
    const row = document.createElement("tr");
    const decodedCell = vehicle.make
      ? ""
      : `<button class="decode-button" data-vin="${vehicle.vin}">Decode VIN</button>`;
    const rawCell = vehicle.raw
      ? `<details><summary>View</summary><pre>${escapeHtml(JSON.stringify(vehicle.raw, null, 2))}</pre></details>`
      : "";
    row.innerHTML = `
      <td>${vehicle.vin}</td>
      <td>${vehicle.make || ""}</td>
      <td>${vehicle.model || ""}</td>
      <td>${vehicle.year || ""}</td>
      <td>${rawCell}</td>
      <td>${decodedCell}</td>
    `;
    tbody.appendChild(row);
  }
  tbody.querySelectorAll(".decode-button").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "Decoding...";
      const response = await fetch(`/vehicles/${button.dataset.vin}/decode`, { method: "POST" });
      if (response.ok) {
        await loadVehicles();
      } else {
        button.disabled = false;
        button.textContent = "Decode VIN (failed, retry)";
      }
    });
  });
}

function setupDiagnosticsControls() {
  document.getElementById("refresh-dtcs").addEventListener("click", loadDtcs);
  const dialog = document.getElementById("confirm-clear-dialog");
  document.getElementById("clear-dtcs").addEventListener("click", () => dialog.showModal());
  document.getElementById("confirm-clear-no").addEventListener("click", () => dialog.close());
  document.getElementById("confirm-clear-yes").addEventListener("click", async () => {
    dialog.close();
    await fetch("/dtcs/clear", { method: "POST" });
    await loadDtcs();
  });
}

setupTabs();
setupWebSocket();
setupDiagnosticsControls();
loadDtcs();
