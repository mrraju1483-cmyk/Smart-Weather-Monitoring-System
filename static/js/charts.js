(() => {
  const api = window.Atmos.api;
  const palette = {
    temperature: "#f0785d",
    humidity: "#4b8ff6",
    air_quality: "#a276e8",
    rain_value: "#41b89b",
  };
  const historyCharts = {};
  let activeRange = "1h";
  let page = 0;
  let pageSize = 10;
  let search = "";
  let dateFilter = null;
  let searchTimer;
  const historySensors = [
    { key: "temperature", canvas: "history-temperature-chart", label: "Temperature", axis: "Temperature (°C)", unit: "°C" },
    { key: "humidity", canvas: "history-humidity-chart", label: "Relative humidity", axis: "Relative humidity (%)", unit: "%" },
    { key: "air_quality", canvas: "history-air-quality-chart", label: "MQ-135 raw reading", axis: "Raw analog value (0–1023)", unit: "raw" },
    { key: "rain_value", canvas: "history-rain-value-chart", label: "Rain sensor raw reading", axis: "Raw analog value (0–1023)", unit: "raw" },
  ];

  function chartOptions(yTitle = "", unit = "") {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#14221e",
          padding: 12,
          titleFont: { family: "DM Sans" },
          bodyFont: { family: "DM Sans" },
          callbacks: {
            label(context) {
              return `${context.dataset.label}: ${context.formattedValue}${unit ? ` ${unit}` : ""}`;
            },
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { maxTicksLimit: 8, maxRotation: 0, color: "#89938f", font: { family: "DM Sans" } } },
        y: { beginAtZero: false, title: { display: Boolean(yTitle), text: yTitle }, grid: { color: "rgba(130,145,140,.13)" }, ticks: { color: "#89938f", font: { family: "DM Sans" } } },
      },
    };
  }

  function makeSeries(readings, key, label, color, unit) {
    return {
      label,
      data: readings.map((item) => item[key]),
      borderColor: color,
      backgroundColor: `${color}18`,
      pointRadius: 2,
      pointHoverRadius: 5,
      borderWidth: 2,
      tension: 0.3,
      fill: false,
      spanGaps: true,
      unit,
    };
  }

  async function loadOverview() {
    const canvas = document.getElementById("overview-chart");
    if (!canvas || !window.Chart) return;
    try {
      const result = await api("/api/history?range=24h&limit=200");
      const readings = result.readings.slice().reverse();
      if (!readings.length) return;
      const chart = new Chart(canvas, {
        type: "line",
        data: {
          labels: readings.map((item) => new Date(item.timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })),
          datasets: [
            makeSeries(readings, "temperature", "Temperature °C", palette.temperature, "°C"),
            makeSeries(readings, "humidity", "Humidity %", palette.humidity, "%"),
          ],
        },
        options: chartOptions(),
      });
      return chart;
    } catch (error) {
      console.warn("Overview chart could not be loaded:", error);
    }
  }

  function historyQuery() {
    const params = new URLSearchParams({ limit: String(pageSize), offset: String(page * pageSize), search });
    if (dateFilter) {
      if (dateFilter.start) params.set("start", new Date(dateFilter.start).toISOString());
      if (dateFilter.end) params.set("end", new Date(dateFilter.end).toISOString());
    } else if (activeRange !== "all") {
      params.set("range", activeRange);
    }
    return params;
  }

  async function loadHistory() {
    if (!document.getElementById(historySensors[0].canvas)) return;
    const params = historyQuery();
    params.set("limit", "5000");
    params.set("offset", "0");
    try {
      const chartResult = await api(`/api/history?${params}`);
      const readings = chartResult.readings.slice().reverse();
      const labels = readings.map((item) => new Date(item.timestamp).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }));
      historySensors.forEach((sensor) => {
        const canvas = document.getElementById(sensor.canvas);
        if (!canvas) return;
        if (historyCharts[sensor.key]) historyCharts[sensor.key].destroy();
        historyCharts[sensor.key] = new Chart(canvas, {
          type: "line",
          data: {
            labels,
            datasets: [makeSeries(readings, sensor.key, sensor.label, palette[sensor.key], sensor.unit)],
          },
          options: chartOptions(sensor.axis, sensor.unit),
        });
      });
      await loadTable();
    } catch (error) {
      window.Atmos.toast(`Could not load history: ${error.message}`, "error");
    }
  }

  async function loadTable() {
    const params = historyQuery();
    const result = await api(`/api/history?${params}`);
    const body = document.getElementById("history-rows");
    const total = result.total;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const first = total ? page * pageSize + 1 : 0;
    const last = Math.min((page + 1) * pageSize, total);
    const safe = window.Atmos.escapeHtml;
    if (body) body.innerHTML = result.readings.length ? result.readings.map((item) => `<tr><td>${safe(window.Atmos.formatDate(item.timestamp))}</td><td>${safe(item.temperature ?? "—")} °C</td><td>${safe(item.humidity ?? "—")} %</td><td><span class="raw-reading">${safe(item.air_quality)}</span></td><td><span class="raw-reading">${safe(item.rain_value)}</span></td></tr>`).join("") : '<tr><td colspan="5" class="empty-state">No readings match this filter. Connect the Arduino and wait for new sensor data.</td></tr>';
    const count = document.getElementById("history-count");
    if (count) count.textContent = `${total.toLocaleString()} readings`;
    const summary = document.getElementById("page-summary");
    if (summary) summary.textContent = `Showing ${first}–${last} of ${total}`;
    const number = document.getElementById("page-number");
    if (number) number.textContent = `${page + 1} / ${totalPages}`;
    const previous = document.getElementById("previous-page");
    const next = document.getElementById("next-page");
    if (previous) previous.disabled = page <= 0;
    if (next) next.disabled = page + 1 >= totalPages;
  }

  function initializeHistory() {
    if (!document.getElementById(historySensors[0].canvas)) return;
    document.querySelectorAll(".range-button").forEach((button) => button.addEventListener("click", () => {
      document.querySelectorAll(".range-button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      activeRange = button.dataset.range;
      dateFilter = null;
      page = 0;
      loadHistory();
    }));
    document.getElementById("history-search")?.addEventListener("input", (event) => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => { search = event.target.value.trim(); page = 0; loadHistory(); }, 250);
    });
    document.getElementById("page-size")?.addEventListener("change", (event) => { pageSize = Number(event.target.value); page = 0; loadHistory(); });
    document.getElementById("previous-page")?.addEventListener("click", () => { if (page > 0) { page -= 1; loadTable(); } });
    document.getElementById("next-page")?.addEventListener("click", () => { page += 1; loadTable(); });
    document.getElementById("apply-dates")?.addEventListener("click", () => {
      const start = document.getElementById("date-from").value;
      const end = document.getElementById("date-to").value;
      if (start && end && new Date(start) > new Date(end)) {
        window.Atmos.toast("The start date must be before the end date.", "error");
        return;
      }
      dateFilter = start || end ? { start, end } : null;
      page = 0;
      document.querySelectorAll(".range-button").forEach((item) => item.classList.remove("active"));
      loadHistory();
    });
    document.getElementById("export-csv")?.addEventListener("click", () => {
      const params = new URLSearchParams(historyQuery());
      params.set("format", "csv");
      params.set("limit", "5000");
      params.set("offset", "0");
      window.location.assign(`/api/history?${params}`);
    });
    loadHistory();
  }

  const analysisCharts = {};
  function drawAnalysis(data) {
    const status = document.getElementById("model-status");
    if (!status) return;
    status.textContent = data.status === "trained" ? "Models trained" : "Collecting readings";
    document.getElementById("model-message").textContent = data.message;
    document.getElementById("dataset-size").textContent = data.dataset_size.toLocaleString();
    Object.entries(data.trends).forEach(([key, trend]) => {
      const canvas = document.getElementById(`${key}-analysis`);
      if (!canvas || trend.status !== "trained") return;
      if (analysisCharts[key]) analysisCharts[key].destroy();
      const points = trend.points || [];
      const values = points.map((point) => point.value);
      const last = values.at(-1);
      const estimate = trend.next_estimate?.value;
      analysisCharts[key] = new Chart(canvas, {
        type: "line",
        data: {
          labels: [...points.map((point) => new Date(point.timestamp).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })), "Next estimate"],
          datasets: [{
            label: trend.label,
            data: [...values, estimate],
            borderColor: palette[key],
            backgroundColor: `${palette[key]}18`,
            pointRadius: [...points.map(() => 2), 5],
            pointBackgroundColor: [...points.map(() => palette[key]), "#fff"],
            borderDash: [...points.map(() => []), [6, 4]],
            borderWidth: 2,
            tension: 0.25,
            spanGaps: true,
          }],
        },
        options: chartOptions(),
      });
      const metrics = data.metrics[key];
      document.getElementById(`${key}-metrics`).textContent = `Latest: ${Number(last).toFixed(1)} · Experimental next estimate: ${Number(estimate).toFixed(1)} · MAE ${metrics.mae.toFixed(2)} · RMSE ${metrics.rmse.toFixed(2)}`;
    });
  }

  async function loadAnalysis() {
    if (!document.getElementById("model-status")) return;
    try {
      drawAnalysis(await api("/api/analysis"));
    } catch (error) {
      document.getElementById("model-status").textContent = "Analysis unavailable";
      document.getElementById("model-message").textContent = error.message;
    }
  }

  document.getElementById("analysis-refresh")?.addEventListener("click", loadAnalysis);
  loadOverview();
  initializeHistory();
  loadAnalysis();
})();
