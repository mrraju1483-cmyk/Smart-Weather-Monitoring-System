(() => {
  const api = window.Atmos.api;
  const byId = (id) => document.getElementById(id);

  async function loadSettings() {
    try {
      const values = await api("/api/settings");
      byId("location-name").value = values.location.name;
      byId("latitude").value = values.location.latitude;
      byId("longitude").value = values.location.longitude;
      byId("temperature-threshold").value = values.thresholds.temperature_high;
      byId("humidity-threshold").value = values.thresholds.humidity_high;
      byId("air-threshold").value = values.thresholds.air_quality_high;
      byId("rain-threshold").value = values.thresholds.rain_wet_below;
    } catch (error) {
      window.Atmos.toast(`Could not load settings: ${error.message}`, "error");
    }
  }

  byId("location-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const location = {
      name: byId("location-name").value.trim(),
      latitude: Number(byId("latitude").value),
      longitude: Number(byId("longitude").value),
    };
    try {
      await api("/api/settings", { method: "POST", body: JSON.stringify({ location }) });
      window.Atmos.toast("Weather location saved.");
    } catch (error) {
      window.Atmos.toast(error.message, "error");
    }
  });

  byId("threshold-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const thresholds = {
      temperature_high: Number(byId("temperature-threshold").value),
      humidity_high: Number(byId("humidity-threshold").value),
      air_quality_high: Number(byId("air-threshold").value),
      rain_wet_below: Number(byId("rain-threshold").value),
    };
    try {
      await api("/api/settings", { method: "POST", body: JSON.stringify({ thresholds }) });
      window.Atmos.toast("Alert thresholds saved.");
    } catch (error) {
      window.Atmos.toast(error.message, "error");
    }
  });

  async function loadPorts() {
    try {
      const result = await api("/api/ports");
      byId("configured-port").textContent = result.selected || "Not configured";
      byId("ports-list").textContent = result.ports.length ? result.ports.map((port) => `${port.device} — ${port.description}`).join(" · ") : "No serial ports detected. Connect the Arduino and check Windows Device Manager.";
    } catch (error) {
      byId("ports-list").textContent = error.message;
    }
  }

  async function loadAlerts() {
    try {
      const result = await api("/api/alerts?limit=50");
      const safe = window.Atmos.escapeHtml;
      byId("settings-alert-rows").innerHTML = result.alerts.length ? result.alerts.map((alert) => `<tr><td>${safe(window.Atmos.formatDate(alert.timestamp))}</td><td>${safe(alert.alert_type.replaceAll("_", " "))}</td><td>${safe(alert.message)}</td><td>${safe(alert.sensor_value)}</td></tr>`).join("") : '<tr><td colspan="4" class="empty-state">No alerts recorded yet.</td></tr>';
    } catch (error) {
      byId("settings-alert-rows").innerHTML = `<tr><td colspan="4" class="empty-state">${safeMessage(error.message)}</td></tr>`;
    }
  }
  function safeMessage(message) { const cell = document.createElement("span"); cell.textContent = message; return cell.innerHTML; }

  loadSettings();
  loadPorts();
  loadAlerts();
})();
