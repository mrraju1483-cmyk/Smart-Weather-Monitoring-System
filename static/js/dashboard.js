(() => {
  const $ = (selector) => document.querySelector(selector);
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);

  window.Atmos = {
    escapeHtml,
    async api(url, options = {}) {
      const response = await fetch(url, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
      });
      let payload;
      try {
        payload = await response.json();
      } catch {
        throw new Error(`The server returned an unreadable response (${response.status}).`);
      }
      if (!response.ok || payload.success === false) {
        throw new Error(payload.error || `Request failed (${response.status}).`);
      }
      return payload.data;
    },
    toast(message, type = "success") {
      const region = $("#toast-region");
      if (!region) return;
      const toast = document.createElement("div");
      toast.className = `toast-message toast-${type}`;
      toast.textContent = message;
      region.append(toast);
      window.setTimeout(() => toast.remove(), 4200);
    },
    formatDate(value) {
      if (!value) return "—";
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? value : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
    },
  };

  const themeToggle = $("#theme-toggle");
  if (themeToggle) {
    const storedTheme = localStorage.getItem("atmos-theme");
    if (storedTheme === "dark") document.documentElement.dataset.theme = "dark";
    themeToggle.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      localStorage.setItem("atmos-theme", next);
      themeToggle.innerHTML = next === "dark" ? '<i class="fa-regular fa-sun"></i>' : '<i class="fa-regular fa-moon"></i>';
    });
    if (document.documentElement.dataset.theme === "dark") themeToggle.innerHTML = '<i class="fa-regular fa-sun"></i>';
  }

  const menuToggle = $("#menu-toggle");
  if (menuToggle) menuToggle.addEventListener("click", () => $("#sidebar")?.classList.toggle("sidebar-open"));

  async function updateLive() {
    try {
      const result = await Atmos.api("/api/live");
      const reading = result.reading;
      const serial = result.arduino;
      const display = (selector, value, suffix = "") => {
        const element = $(selector);
        if (element) element.textContent = value === null || value === undefined ? "--" : `${value}${suffix}`;
      };
      display("#temperature-value", reading?.temperature, "");
      display("#humidity-value", reading?.humidity, "");
      display("#air-value", reading?.air_quality, "");
      display("#rain-value", reading?.rain_value, "");
      const sensorState = serial.state || (serial.connected ? "connected" : "disconnected");
      const isConnected = sensorState === "connected";
      if ($("#temperature-note")) {
        $("#temperature-note").textContent = !reading
          ? "Waiting for sensor data"
          : !isConnected
            ? "Last known value · sensor data is stale"
            : reading.temperature == null
              ? "DHT11 temperature unavailable"
              : "DHT11 local measurement";
      }
      if ($("#rain-note")) $("#rain-note").textContent = reading ? "Raw analog reading · see Settings for threshold" : "Raw analog reading";
      if ($("#last-updated")) $("#last-updated").textContent = reading ? Atmos.formatDate(reading.timestamp) : "Waiting for Arduino…";
      updateArduinoStatus(serial);
      const portName = serial.port || "configured port";
      const stateLabels = { connected: "Connected", connecting: "Connecting", disconnected: "Disconnected" };
      if ($("#sidebar-serial-status")) $("#sidebar-serial-status").textContent = `${stateLabels[sensorState] || "Disconnected"} · ${portName}`;
      if ($("#arduino-status-detail")) {
        $("#arduino-status-detail").textContent = serial.last_error
          ? `Serial error: ${serial.last_error}`
          : isConnected
            ? `Valid JSON received on ${portName} · 9600 baud`
            : sensorState === "connecting"
              ? `Waiting for valid sensor JSON on ${portName}`
              : `No recent valid data. Check ${portName} and close Serial Monitor.`;
      }
      const sensorError = $("#sensor-error-note");
      if (sensorError) {
        const dhtError = reading && (reading.temperature == null || reading.humidity == null);
        sensorError.hidden = Boolean(reading && isConnected && !dhtError && !serial.last_error);
        if (serial.last_error) sensorError.textContent = `Arduino serial message: ${serial.last_error}`;
        else if (!isConnected && sensorState === "disconnected") sensorError.textContent = `No recent valid sensor data. Check ${portName}, then close Arduino Serial Monitor so Flask can reconnect.`;
        else if (dhtError) sensorError.textContent = "The DHT11 returned no temperature or humidity value. Check its wiring; the analog sensors may still be working.";
        else if (sensorState === "connecting") sensorError.textContent = `Waiting for a valid JSON sensor line from ${portName}.`;
      }
    } catch (error) {
      console.error("Could not update live sensor readings:", error);
      updateArduinoStatus({ state: "disconnected", port: "COM3" });
      if ($("#arduino-status-detail")) $("#arduino-status-detail").textContent = `Cannot reach the dashboard API: ${error.message}`;
      const sensorError = $("#sensor-error-note");
      if (sensorError) {
        sensorError.hidden = false;
        sensorError.textContent = "Cannot reach the Flask server. Sensor connection status is unavailable; check that python app.py is running.";
      }
    }
  }

  function updateArduinoStatus(serial) {
    const state = ["connected", "connecting", "disconnected"].includes(serial.state)
      ? serial.state
      : serial.connected ? "connected" : "disconnected";
    const label = { connected: "Connected", connecting: "Connecting", disconnected: "Disconnected" }[state];
    const badge = $("#arduino-state");
    if (badge) {
      badge.classList.toggle("online", state === "connected");
      badge.classList.toggle("connecting", state === "connecting");
      badge.classList.toggle("offline", state === "disconnected");
      badge.innerHTML = `<i class="status-dot dot-${state === "connected" ? "online" : state === "connecting" ? "connecting" : "offline"}"></i> ${label}`;
    }
    const dot = $("#sidebar-status-dot");
    if (dot) {
      dot.classList.toggle("dot-online", state === "connected");
      dot.classList.toggle("connecting", state === "connecting");
      dot.classList.toggle("offline", state === "disconnected");
    }
  }

  function setConnection(selector, connected, label) {
    const element = $(selector);
    if (!element) return;
    element.classList.toggle("online", connected);
    element.classList.toggle("offline", !connected);
    const dot = element.querySelector(".status-dot");
    if (dot) dot.classList.toggle("dot-online", connected);
    if (label) {
      const text = [...element.childNodes].find((node) => node.nodeType === Node.TEXT_NODE);
      if (text) text.textContent = ` ${label}`;
    }
  }

  async function updateStatus() {
    try {
      const status = await Atmos.api("/api/status");
      setConnection("#database-state", status.database.connected, status.database.connected ? "Online" : "Error");
      if ($("#database-status-detail")) $("#database-status-detail").textContent = status.database.message;
      setConnection("#weather-state", status.weather.status === "online", status.weather.status === "online" ? "Online" : status.weather.status === "offline" ? "Offline" : "Checking");
    } catch (error) {
      console.error("Could not check system status:", error);
    }
  }

  async function updateWeather(force = false) {
    const content = $("#weather-content");
    if (!content) return;
    try {
      const weather = await Atmos.api(`/api/weather${force ? "?refresh=true" : ""}`);
      const current = weather.current || {};
      if ($("#weather-location")) $("#weather-location").textContent = weather.location?.name || "Configured location";
      content.innerHTML = `<div class="weather-current"><div><div class="weather-temperature">${escapeHtml(current.temperature ?? "--")}<span>°</span></div><div class="weather-condition">${escapeHtml(current.condition || "Conditions unavailable")}</div></div><span class="weather-symbol"><i class="fa-solid fa-cloud-sun"></i></span></div>`;
      const details = [
        ["Humidity", current.humidity, "%", "fa-droplet"],
        ["Feels like", current.apparent_temperature, "°C", "fa-temperature-half"],
        ["Wind speed", current.wind_speed, "km/h", "fa-wind"],
        ["Precipitation", current.precipitation, "mm", "fa-cloud-rain"],
        ["Rain chance", current.precipitation_probability, "%", "fa-umbrella"],
      ];
      const detailsElement = $("#weather-details");
      if (detailsElement) detailsElement.innerHTML = details.map(([label, value, unit, icon]) => `<div class="weather-detail"><i class="fa-solid ${icon}"></i><span>${label}</span><strong>${escapeHtml(value ?? "—")}${value == null ? "" : unit}</strong></div>`).join("");
      const hourlyElement = $("#hourly-forecast");
      if (hourlyElement) hourlyElement.innerHTML = (weather.hourly || []).slice(0, 6).map((item) => `<div class="hour-item"><span>${escapeHtml(new Date(item.time).toLocaleTimeString([], { hour: "numeric" }))}</span><i class="fa-solid fa-cloud${item.precipitation_probability > 40 ? "-rain" : "-sun"}"></i><strong>${escapeHtml(item.temperature ?? "—")}°</strong><small>${escapeHtml(item.precipitation_probability ?? "—")}% rain</small></div>`).join("");
      const dailyElement = $("#daily-forecast");
      if (dailyElement) dailyElement.innerHTML = (weather.daily || []).map((item) => `<div class="day-item"><span>${escapeHtml(new Date(`${item.date}T12:00:00`).toLocaleDateString([], { weekday: "short" }))}</span><i class="fa-solid fa-cloud${item.precipitation_probability > 40 ? "-rain" : "-sun"}"></i><strong>${escapeHtml(item.temperature_max ?? "—")}° <small>${escapeHtml(item.temperature_min ?? "—")}°</small></strong><small>${escapeHtml(item.precipitation_probability ?? "—")}%</small></div>`).join("");
      setConnection("#weather-state", true, "Online");
    } catch (error) {
      content.innerHTML = `<div class="weather-error"><i class="fa-solid fa-cloud-bolt"></i><span>${escapeHtml(error.message)}<small>Weather is external API data; local sensor readings remain available.</small></span></div>`;
      setConnection("#weather-state", false, "Offline");
    }
  }

  async function updateAlerts() {
    const container = $("#recent-alerts");
    if (!container) return;
    try {
      const result = await Atmos.api("/api/alerts?limit=4");
      container.innerHTML = result.alerts.length ? result.alerts.map((alert) => `<div class="recent-alert"><span class="alert-icon"><i class="fa-solid fa-triangle-exclamation"></i></span><div><strong>${escapeHtml(alert.alert_type.replaceAll("_", " "))}</strong><small>${escapeHtml(alert.message)}</small></div><time>${escapeHtml(new Date(alert.timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }))}</time></div>`).join("") : '<div class="empty-state">No alerts yet. Your sensor readings will be checked against configured thresholds.</div>';
    } catch (error) {
      container.textContent = `Alert history unavailable: ${error.message}`;
    }
  }

  $("#weather-refresh")?.addEventListener("click", () => updateWeather(true));
  updateLive();
  window.setInterval(updateLive, 2000);
  if ($("#temperature-value")) {
    updateStatus();
    updateWeather();
    updateAlerts();
    window.setInterval(updateStatus, 15000);
    window.setInterval(updateAlerts, 30000);
  }
})();
