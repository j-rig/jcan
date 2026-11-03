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
      if (button.dataset.tab === "history") loadHistory();
    });
  });
}

const GAUGE_HISTORY_LENGTH = 20;
const gaugeHistories = {};

function renderGauge(pid, value, unit) {
  let el = document.getElementById(`gauge-${pid}`);
  if (!el) {
    el = document.createElement("div");
    el.id = `gauge-${pid}`;
    el.className = "gauge";
    el.innerHTML = `
      <div class="gauge-label">${PID_LABELS[pid] || pid}</div>
      <div class="gauge-value"></div>
      <svg class="gauge-sparkline" viewBox="0 0 100 30" preserveAspectRatio="none">
        <polyline points=""></polyline>
      </svg>
    `;
    document.getElementById("gauges").appendChild(el);
  }
  el.dataset.lastUpdate = Date.now();
  el.querySelector(".gauge-value").textContent = `${value} ${unit}`;
  el.classList.remove("stale");

  const history = gaugeHistories[pid] || (gaugeHistories[pid] = []);
  history.push(value);
  if (history.length > GAUGE_HISTORY_LENGTH) history.shift();

  const min = Math.min(...history);
  const max = Math.max(...history);
  const range = max - min || 1;
  const divisor = Math.max(history.length - 1, 1);
  const points = history
    .map((v, i) => {
      const x = (i / divisor) * 100;
      const y = 30 - ((v - min) / range) * 30;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  el.querySelector(".gauge-sparkline polyline").setAttribute("points", points);
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
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";

  function connect() {
    const ws = new WebSocket(`${scheme}//${location.host}/ws`);
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "reading") {
        renderGauge(message.pid, message.value, message.unit);
      } else if (message.type === "status") {
        showConnectionStatus(message.status);
      }
    };
    ws.onclose = () => {
      showConnectionStatus("disconnected");
      setTimeout(connect, 2000);
    };
  }

  connect();
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
  const tbody = document.querySelector("#dtc-table tbody");
  if (!response.ok) {
    tbody.innerHTML = `<tr><td colspan="5">Error loading codes: ${escapeHtml(await response.text())}</td></tr>`;
    return;
  }
  const events = await response.json();
  tbody.innerHTML = "";
  for (const event of events) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(event.code)}</td>
      <td>${escapeHtml(event.description)}</td>
      <td>${escapeHtml(vehicleLabel(event))}</td>
      <td>${escapeHtml(event.first_seen)}</td>
      <td><textarea data-id="${event.id}">${escapeHtml(event.notes || "")}</textarea></td>
    `;
    tbody.appendChild(row);
  }
  tbody.querySelectorAll("textarea").forEach((textarea) => {
    textarea.addEventListener("blur", async () => {
      await fetch(`/dtcs/${encodeURIComponent(textarea.dataset.id)}/notes`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: textarea.value }),
      });
    });
  });
}

async function loadHistory() {
  const response = await fetch("/dtcs/history");
  const tbody = document.querySelector("#history-table tbody");
  if (!response.ok) {
    tbody.innerHTML = `<tr><td colspan="6">Error loading history: ${escapeHtml(await response.text())}</td></tr>`;
    return;
  }
  const events = await response.json();
  tbody.innerHTML = "";
  for (const event of events) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(event.code)}</td>
      <td>${escapeHtml(event.description)}</td>
      <td>${escapeHtml(vehicleLabel(event))}</td>
      <td>${escapeHtml(event.first_seen)}</td>
      <td>${escapeHtml(event.cleared_at || "")}</td>
      <td><textarea data-id="${event.id}">${escapeHtml(event.notes || "")}</textarea></td>
    `;
    tbody.appendChild(row);
  }
  tbody.querySelectorAll("textarea").forEach((textarea) => {
    textarea.addEventListener("blur", async () => {
      await fetch(`/dtcs/${encodeURIComponent(textarea.dataset.id)}/notes`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: textarea.value }),
      });
    });
  });
}

async function loadVehicles() {
  const response = await fetch("/vehicles");
  const tbody = document.querySelector("#vehicle-table tbody");
  if (!response.ok) {
    tbody.innerHTML = `<tr><td colspan="6">Error loading vehicles: ${escapeHtml(await response.text())}</td></tr>`;
    return;
  }
  const vehicles = await response.json();
  tbody.innerHTML = "";
  for (const vehicle of vehicles) {
    const row = document.createElement("tr");
    const decodedCell = vehicle.make
      ? ""
      : `<button class="decode-button" data-vin="${escapeHtml(vehicle.vin)}">Decode VIN</button>`;
    const rawCell = vehicle.raw
      ? `<details><summary>View</summary><pre>${escapeHtml(JSON.stringify(vehicle.raw, null, 2))}</pre></details>`
      : "";
    row.innerHTML = `
      <td>${escapeHtml(vehicle.vin)}</td>
      <td>${escapeHtml(vehicle.make || "")}</td>
      <td>${escapeHtml(vehicle.model || "")}</td>
      <td>${escapeHtml(vehicle.year || "")}</td>
      <td>${rawCell}</td>
      <td>${decodedCell}</td>
    `;
    tbody.appendChild(row);
  }
  tbody.querySelectorAll(".decode-button").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "Decoding...";
      const response = await fetch(
        `/vehicles/${encodeURIComponent(button.dataset.vin)}/decode`,
        { method: "POST" }
      );
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
    const response = await fetch("/dtcs/clear", { method: "POST" });
    if (!response.ok) {
      alert(`Failed to clear codes: ${await response.text()}`);
    }
    await loadDtcs();
  });
}

setupTabs();
setupWebSocket();
setupDiagnosticsControls();
loadDtcs();
