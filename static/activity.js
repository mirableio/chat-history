const ACTIVITY_PROVIDER_THEME = {
  chatgpt: {
    heat: ["#eeeeee", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
    barBg: "rgba(22, 163, 74, 0.45)",
    barBorder: "rgba(21, 128, 61, 1)",
  },
  claude: {
    heat: ["#f3f4f6", "#fed7aa", "#fb923c", "#ea580c", "#c2410c"],
    barBg: "rgba(234, 88, 12, 0.45)",
    barBorder: "rgba(194, 65, 12, 1)",
  },
};

const ACTIVITY_FALLBACK_COLORS = [
  { barBg: "rgba(59, 130, 246, 0.45)", barBorder: "rgba(29, 78, 216, 1)" },
  { barBg: "rgba(168, 85, 247, 0.45)", barBorder: "rgba(126, 34, 206, 1)" },
  { barBg: "rgba(20, 184, 166, 0.45)", barBorder: "rgba(15, 118, 110, 1)" },
];
const ACTIVITY_ROLLING_PERIOD = "rolling";

const activityState = {
  payload: null,
  providers: [],
  selectedProviders: new Set(),
  selectedYear: ACTIVITY_ROLLING_PERIOD,
  viewMode: "unified",
  controlsInitialized: false,
};

let activityBarChartInstance = null;

function notifyActivitySettingsChanged() {
  window.dispatchEvent(
    new CustomEvent("activity-settings-changed", {
      detail: {
        viewMode: activityState.viewMode,
        providers: activityState.providers.slice(),
        selectedProviders: Array.from(activityState.selectedProviders),
      },
    })
  );
}

function getProviderTheme(provider, index) {
  const namedTheme = ACTIVITY_PROVIDER_THEME[provider];
  if (namedTheme) {
    return namedTheme;
  }
  const fallback = ACTIVITY_FALLBACK_COLORS[index % ACTIVITY_FALLBACK_COLORS.length];
  return {
    heat: ["#eeeeee", "#dbeafe", "#93c5fd", "#3b82f6", "#1d4ed8"],
    barBg: fallback.barBg,
    barBorder: fallback.barBorder,
  };
}

function normalizeActivityPayload(rawPayload) {
  if (rawPayload && typeof rawPayload === "object" && rawPayload.days) {
    return rawPayload;
  }

  const days = {};
  for (const [day, count] of Object.entries(rawPayload || {})) {
    days[day] = {
      total: Number(count) || 0,
      providers: {},
    };
  }
  return { providers: [], provider_totals: {}, days };
}

function resolveProvidersFromPayload(payload) {
  const providersFromTotals = Object.keys(payload.provider_totals || {});
  if (providersFromTotals.length > 0) {
    return providersFromTotals.sort();
  }

  const providerSet = new Set();
  for (const entry of Object.values(payload.days || {})) {
    for (const provider of Object.keys(entry.providers || {})) {
      providerSet.add(provider);
    }
  }
  return Array.from(providerSet).sort();
}

function getSelectedDayTotals() {
  const results = {};
  const days = activityState.payload?.days || {};
  const hasProviderDimension = activityState.providers.length > 0;

  for (const [day, entry] of Object.entries(days)) {
    if (!hasProviderDimension) {
      results[day] = Number(entry.total || 0);
      continue;
    }

    let total = 0;
    for (const provider of activityState.selectedProviders) {
      total += Number((entry.providers || {})[provider] || 0);
    }
    results[day] = total;
  }
  return results;
}

function getSelectedProviderSeries() {
  const days = activityState.payload?.days || {};
  const providers = Array.from(activityState.selectedProviders);
  const series = {};
  for (const provider of providers) {
    series[provider] = {};
  }

  for (const [day, entry] of Object.entries(days)) {
    for (const provider of providers) {
      series[provider][day] = Number((entry.providers || {})[provider] || 0);
    }
  }
  return series;
}

function extractYearsFromDayCounts(dayCounts) {
  const years = new Set();
  for (const [day, count] of Object.entries(dayCounts)) {
    if (Number(count || 0) <= 0) {
      continue;
    }
    const year = Number(String(day).slice(0, 4));
    if (Number.isInteger(year)) {
      years.add(year);
    }
  }
  return Array.from(years).sort((left, right) => left - right);
}

function renderYearBadges(dayCounts) {
  const container = document.getElementById("activity-year-badges");
  if (!container) {
    return;
  }

  const years = extractYearsFromDayCounts(dayCounts);
  if (years.length <= 1) {
    activityState.selectedYear = ACTIVITY_ROLLING_PERIOD;
    container.innerHTML = "";
    container.classList.add("hidden");
    return;
  }

  const periods = [
    ...years.map((year) => ({ value: String(year), label: String(year) })),
    { value: ACTIVITY_ROLLING_PERIOD, label: "12 months" },
  ];
  const allowed = new Set(periods.map((period) => period.value));
  if (!allowed.has(String(activityState.selectedYear))) {
    activityState.selectedYear = ACTIVITY_ROLLING_PERIOD;
  }

  container.classList.remove("hidden");
  container.innerHTML = periods
    .map(
      (period) => `
        <button
          class="activity-year-badge ${String(period.value) === String(activityState.selectedYear) ? "is-active" : ""}"
          data-period="${period.value}"
          type="button"
        >
          ${period.label}
        </button>
      `
    )
    .join("");

  container.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const period = button.dataset.period || ACTIVITY_ROLLING_PERIOD;
      const nextSelection =
        period === ACTIVITY_ROLLING_PERIOD ? ACTIVITY_ROLLING_PERIOD : Number(period);
      if (String(nextSelection) === String(activityState.selectedYear)) {
        return;
      }
      activityState.selectedYear = nextSelection;
      renderActivityDashboard();
    });
  });
}

function filterDayCountsByYear(dayCounts) {
  if (!Number.isInteger(activityState.selectedYear)) {
    return dayCounts;
  }
  const yearPrefix = `${activityState.selectedYear}-`;
  const filtered = {};
  for (const [day, count] of Object.entries(dayCounts)) {
    if (day.startsWith(yearPrefix)) {
      filtered[day] = Number(count || 0);
    }
  }
  return filtered;
}

function filterProviderSeriesByYear(providerSeries) {
  if (!Number.isInteger(activityState.selectedYear)) {
    return providerSeries;
  }
  const yearPrefix = `${activityState.selectedYear}-`;
  const filtered = {};
  for (const [provider, dayCounts] of Object.entries(providerSeries)) {
    filtered[provider] = {};
    for (const [day, count] of Object.entries(dayCounts)) {
      if (day.startsWith(yearPrefix)) {
        filtered[provider][day] = Number(count || 0);
      }
    }
  }
  return filtered;
}

function totalActivityCount(dayCounts) {
  return Object.values(dayCounts).reduce((sum, count) => sum + Number(count || 0), 0);
}

function showActivityEmptyState() {
  const graphContainer = document.getElementById("activity-graph");
  graphContainer.innerHTML = `<div class="activity-empty-state">No provider selected.</div>`;
  buildActivityBarChart({});
}

function renderUnifiedActivityView(dayCounts, year) {
  const graphContainer = document.getElementById("activity-graph");
  graphContainer.innerHTML = "";
  buildActivityGraph(graphContainer, { data: dayCounts, year });
  buildActivityBarChart(dayCounts, year);
}

function renderProviderActivityView(providerSeries, year) {
  const graphContainer = document.getElementById("activity-graph");
  graphContainer.innerHTML = "";
  const providers = Object.keys(providerSeries);

  if (providers.length === 0) {
    showActivityEmptyState();
    return;
  }

  providers.forEach((provider, index) => {
    const panel = document.createElement("div");
    panel.className = "activity-provider-panel";

    const heading = document.createElement("div");
    heading.className = "activity-provider-heading";
    heading.innerHTML = `
      <span class="provider-badge provider-${provider}">${provider}</span>
      <span>Activity</span>
    `;

    const chartContainer = document.createElement("div");
    panel.appendChild(heading);
    panel.appendChild(chartContainer);
    graphContainer.appendChild(panel);

    buildActivityGraph(chartContainer, {
      data: providerSeries[provider],
      colorRanges: getProviderTheme(provider, index).heat,
      year,
    });
  });

  buildActivityBarChartByProvider(providerSeries, year);
}

function renderActivityDashboard() {
  if (!activityState.payload) {
    return;
  }

  const dayTotals = getSelectedDayTotals();
  renderYearBadges(dayTotals);

  const filteredDayTotals = filterDayCountsByYear(dayTotals);
  if (totalActivityCount(filteredDayTotals) === 0) {
    showActivityEmptyState();
    return;
  }

  if (activityState.viewMode === "provider" && activityState.selectedProviders.size > 0) {
    const providerSeries = filterProviderSeriesByYear(getSelectedProviderSeries());
    renderProviderActivityView(providerSeries, activityState.selectedYear);
    return;
  }

  renderUnifiedActivityView(filteredDayTotals, activityState.selectedYear);
}

function syncProviderSelectionsFromUI() {
  const container = document.getElementById("activity-provider-filters");
  const checkboxes = container.querySelectorAll("input[type='checkbox']");
  activityState.selectedProviders.clear();
  checkboxes.forEach((checkbox) => {
    if (checkbox.checked) {
      activityState.selectedProviders.add(checkbox.value);
    }
  });
}

function renderProviderFilters() {
  const section = document.getElementById("activity-provider-filter-section");
  const container = document.getElementById("activity-provider-filters");
  container.innerHTML = "";

  if (activityState.providers.length === 0) {
    section.classList.add("hidden");
    return;
  }

  section.classList.remove("hidden");
  activityState.providers.forEach((provider) => {
    const label = document.createElement("label");
    label.className = "activity-provider-option";
    label.innerHTML = `
      <input type="checkbox" value="${provider}" ${activityState.selectedProviders.has(provider) ? "checked" : ""} />
      <span class="provider-badge provider-${provider}">${provider}</span>
    `;
    container.appendChild(label);
  });

  container.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      syncProviderSelectionsFromUI();
      renderActivityDashboard();
      notifyActivitySettingsChanged();
    });
  });
}

function renderViewModeControls() {
  const section = document.getElementById("activity-view-mode-section");
  if (activityState.providers.length < 2) {
    activityState.viewMode = "unified";
    section.classList.add("hidden");
    return;
  }

  section.classList.remove("hidden");
  const radios = section.querySelectorAll("input[name='activity-view-mode']");
  radios.forEach((radio) => {
    radio.checked = radio.value === activityState.viewMode;
  });
}

function bindActivityControlEvents() {
  if (activityState.controlsInitialized) {
    return;
  }
  activityState.controlsInitialized = true;

  const toggleButton = document.getElementById("activity-settings-toggle");
  const menu = document.getElementById("activity-settings-menu");

  toggleButton.addEventListener("click", (event) => {
    event.stopPropagation();
    menu.classList.toggle("hidden");
  });

  document.addEventListener("click", (event) => {
    if (menu.classList.contains("hidden")) {
      return;
    }
    if (!menu.contains(event.target) && event.target !== toggleButton) {
      menu.classList.add("hidden");
    }
  });

  document
    .querySelectorAll("input[name='activity-view-mode']")
    .forEach((radio) => {
      radio.addEventListener("change", () => {
        activityState.viewMode = radio.value;
        renderActivityDashboard();
        notifyActivitySettingsChanged();
      });
    });
}

function updateActivityControlsVisibility() {
  const toggleButton = document.getElementById("activity-settings-toggle");
  const menu = document.getElementById("activity-settings-menu");
  const hasProviderData = activityState.providers.length > 0;

  if (!hasProviderData) {
    toggleButton.classList.add("hidden");
    menu.classList.add("hidden");
    return;
  }

  toggleButton.classList.remove("hidden");
}

function setActivityPayload(rawPayload) {
  activityState.payload = normalizeActivityPayload(rawPayload);
  activityState.providers = resolveProvidersFromPayload(activityState.payload);
  activityState.selectedProviders = new Set(activityState.providers);
  activityState.selectedYear = ACTIVITY_ROLLING_PERIOD;
  if (activityState.providers.length < 2) {
    activityState.viewMode = "unified";
  }

  bindActivityControlEvents();
  updateActivityControlsVisibility();
  renderProviderFilters();
  renderViewModeControls();
  renderActivityDashboard();
  notifyActivitySettingsChanged();
}

window.setActivityPayload = setActivityPayload;

// Main function to create the GitHub graph
function buildActivityGraph(parentElement, options) {
  var settings = Object.assign(
    {
      colorStep: 15,
      click: null,
      data: [],
      colorRanges: ["#eeeeee", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
      year: null,
    },
    options
  );

  var objTimestamp = {};

  function prettyNumber(number) {
    return number < 10 ? "0" + number.toString() : number.toString();
  }

  function processActivityList(activityByDay) {
    for (let [timestamp, count] of Object.entries(activityByDay)) {
      const date = new Date(timestamp);
      const displayDate = getDisplayDate(date);

      if (!objTimestamp[displayDate]) {
        objTimestamp[displayDate] = count;
      } else {
        objTimestamp[displayDate] += count;
      }
    }
  }

  function getDisplayDate(date) {
    function formatString(str, args) {
      return str.replace(/{(\d+)}/g, function (match, number) {
        return typeof args[number] !== "undefined" ? args[number] : match;
      });
    }

    return formatString("{0}-{1}-{2}", [
      date.getFullYear(),
      prettyNumber(date.getMonth() + 1),
      prettyNumber(date.getDate()),
    ]);
  }

  function getCount(displayDate) {
    return objTimestamp[displayDate] || 0;
  }

  function getColor(count) {
    const colorRanges = settings.colorRanges;
    const index =
      count === 0
        ? 0
        : Math.min(Math.floor((count - 1) / settings.colorStep) + 1, colorRanges.length - 1);
    return colorRanges[index];
  }

  function start() {
    processActivityList(settings.data);
    const wrapChart = parentElement;

    const radius = 2;
    const hoverColor = "#999";
    const clickCallback = settings.click;

    let startDate;
    let endDate;
    if (Number.isInteger(settings.year)) {
      startDate = new Date(settings.year, 0, 1);
      endDate = new Date(settings.year, 11, 31);
    } else {
      startDate = new Date();
      startDate.setMonth(startDate.getMonth() - 12);
      startDate.setDate(startDate.getDate() + 1);

      endDate = new Date(startDate);
      endDate.setMonth(endDate.getMonth() + 12);
      endDate.setDate(endDate.getDate() - 1);
    }

    let loopHtml = "";
    const step = 13;

    let monthPosition = [];
    monthPosition.push({ monthIndex: startDate.getMonth(), x: 0 });
    let usingMonth = startDate.getMonth();

    let week = 0;
    let gx = week * step;
    let itemHtml = `<g transform="translate(${gx}, 0)">`;

    for (; startDate.getTime() <= endDate.getTime(); startDate.setDate(startDate.getDate() + 1)) {
      const monthInDay = startDate.getMonth();
      const dataDate = getDisplayDate(startDate);

      if (startDate.getDay() === 0 && monthInDay !== usingMonth) {
        usingMonth = monthInDay;
        monthPosition.push({ monthIndex: usingMonth, x: gx });
      }

      const count = getCount(dataDate);
      const color = getColor(count);

      const y = startDate.getDay() * step;
      itemHtml += `<rect class="day" width="11" height="11" y="${y}" fill="${color}" data-count="${count}" data-date="${dataDate}" rx="${radius}" ry="${radius}"/>`;

      if (startDate.getDay() === 6) {
        itemHtml += `</g>`;
        loopHtml += itemHtml;

        week++;
        gx = week * step;
        itemHtml = `<g transform="translate(${gx}, 0)">`;
      }
    }

    if (itemHtml !== "") {
      itemHtml += `</g>`;
      loopHtml += itemHtml;
    }

    const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    for (let i = 0; i < monthPosition.length; i++) {
      const item = monthPosition[i];
      const monthName = monthNames[item.monthIndex];
      loopHtml += `<text x="${item.x}" y="-5" class="month">${monthName}</text>`;
    }

    loopHtml += `
            <text text-anchor="middle" class="wday" dx="-10" dy="23">M</text>
            <text text-anchor="middle" class="wday" dx="-10" dy="49">W</text>
            <text text-anchor="middle" class="wday" dx="-10" dy="75">F</text>
        `;

    const wireHtml = `
          <svg width="720" height="110" viewBox="0 0 720 110" class="js-calendar-graph-svg">
            <g transform="translate(20, 20)">
              ${loopHtml}
            </g>
          </svg>
        `;

    wrapChart.innerHTML = wireHtml;

    const dayElements = wrapChart.querySelectorAll(".day");
    dayElements.forEach((dayElement) => {
      dayElement.addEventListener("click", function () {
        if (clickCallback) {
          clickCallback(this.getAttribute("data-date"), parseInt(this.getAttribute("data-count")));
        }
      });

      dayElement.addEventListener("mouseenter", function () {
        this.setAttribute("style", `stroke-width: 1; stroke: ${hoverColor}`);
      });

      dayElement.addEventListener("mouseleave", function () {
        this.setAttribute("style", "stroke-width: 0");
      });
    });

    let tooltip;
    if (!document.querySelector(".svg-tip")) {
      tooltip = document.createElement("div");
      tooltip.className = "svg-tip";
      tooltip.style.display = "none";
      document.body.appendChild(tooltip);
    } else {
      tooltip = document.querySelector(".svg-tip");
    }

    function mouseEnter(evt) {
      const targetRect = evt.target.getBoundingClientRect();
      const count = evt.target.getAttribute("data-count");
      const date = evt.target.getAttribute("data-date");

      if (count == 0) return;

      tooltip.innerHTML = `${count} messages on ${date}`;
      tooltip.style.display = "block";
      tooltip.style.top = targetRect.top - tooltip.offsetHeight - 5 + "px";
      tooltip.style.left = targetRect.left - tooltip.offsetWidth / 2 + "px";
    }

    function mouseLeave() {
      tooltip.style.display = "none";
    }

    const rects = document.querySelectorAll(".day");
    rects.forEach(function (rect) {
      rect.addEventListener("mouseenter", mouseEnter);
      rect.addEventListener("mouseleave", mouseLeave);
    });
  }

  start();
}

function prepareBarChartData(activityData, year) {
  const allDates = {};
  let startDate;
  let endDate;

  if (Number.isInteger(year)) {
    startDate = new Date(year, 0, 1);
    endDate = new Date(year, 11, 31);
  } else {
    endDate = new Date();
    startDate = new Date();
    startDate.setFullYear(endDate.getFullYear() - 1);
  }

  let currentDate = new Date(startDate);
  while (currentDate <= endDate) {
    const dateStr = currentDate.toISOString().split("T")[0];
    allDates[dateStr] = 0;
    currentDate.setDate(currentDate.getDate() + 1);
  }

  Object.keys(activityData).forEach((dateStr) => {
    if (allDates.hasOwnProperty(dateStr)) {
      allDates[dateStr] = activityData[dateStr];
    }
  });

  const labels = Object.keys(allDates);
  const data = Object.values(allDates);

  const monthLabels = labels.map((dateStr) => {
    const dateObj = new Date(dateStr);
    return dateObj.getDate() === 1 ? dateObj.toLocaleString("default", { month: "short" }) : "";
  });

  return { labels, data, monthLabels };
}

function destroyActivityBarChart() {
  if (activityBarChartInstance) {
    activityBarChartInstance.destroy();
    activityBarChartInstance = null;
  }
}

function buildActivityBarChart(data, year) {
  const preparedData = prepareBarChartData(data, year);
  const barCanvas = document.getElementById("activity-bar-chart");
  if (!barCanvas) return;
  const barCtx = barCanvas.getContext("2d");

  destroyActivityBarChart();
  activityBarChartInstance = new Chart(barCtx, {
    type: "bar",
    data: {
      labels: preparedData.labels,
      datasets: [
        {
          label: "Messages",
          data: preparedData.data,
          borderColor: "#30a14e",
          backgroundColor: "rgba(48, 161, 78, 0.35)",
          borderWidth: 1,
        },
      ],
    },
    options: {
      aspectRatio: 4,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            callback: function (value, index) {
              return preparedData.monthLabels[index];
            },
            autoSkip: false,
            maxRotation: 0,
            minRotation: 0,
          },
        },
        y: { beginAtZero: true },
      },
    },
  });
}

function buildActivityBarChartByProvider(providerSeries, year) {
  const providers = Object.keys(providerSeries);
  if (providers.length === 0) {
    buildActivityBarChart({}, year);
    return;
  }

  const basePrepared = prepareBarChartData(providerSeries[providers[0]], year);
  const datasets = providers.map((provider, index) => {
    const prepared = prepareBarChartData(providerSeries[provider], year);
    const theme = getProviderTheme(provider, index);
    return {
      label: provider,
      data: prepared.data,
      borderColor: theme.barBorder,
      backgroundColor: theme.barBg,
      borderWidth: 1,
    };
  });

  const barCanvas = document.getElementById("activity-bar-chart");
  if (!barCanvas) return;
  const barCtx = barCanvas.getContext("2d");
  destroyActivityBarChart();

  activityBarChartInstance = new Chart(barCtx, {
    type: "bar",
    data: {
      labels: basePrepared.labels,
      datasets: datasets,
    },
    options: {
      aspectRatio: 4,
      plugins: { legend: { display: true } },
      scales: {
        x: {
          grid: { display: false },
          stacked: true,
          ticks: {
            callback: function (value, index) {
              return basePrepared.monthLabels[index];
            },
            autoSkip: false,
            maxRotation: 0,
            minRotation: 0,
          },
        },
        y: { beginAtZero: true, stacked: true },
      },
    },
  });
}

function buildAIStatsBarChart(data) {
  const mainContent = document.getElementById("main-content");
  if (!data || data.length === 0) {
    mainContent.innerHTML = `
            <div class="pt-10 text-center">No token statistics available.</div>
        `;
    return;
  }

  const labels = [];
  const inputTokens = [];
  const outputTokens = [];
  for (const entry of data) {
    labels.push(`${entry.provider}:${entry.model}`);
    inputTokens.push(entry.input_tokens || 0);
    outputTokens.push(entry.output_tokens || 0);
  }

  mainContent.innerHTML = `
        <div>
          <h1 class="pt-10 pb-4 text-center text-xl">Token usage by provider and model</h1>
          <canvas id="ai-cost-bar-chart"></canvas>
        </div>
    `;

  const barCtx = document.getElementById("ai-cost-bar-chart").getContext("2d");
  new Chart(barCtx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Input tokens",
          data: inputTokens,
          minBarLength: 5,
          backgroundColor: "rgba(75, 192, 192, 0.5)",
          borderColor: "rgba(75, 192, 192, 1)",
          borderWidth: 1,
        },
        {
          label: "Output tokens",
          data: outputTokens,
          minBarLength: 5,
          backgroundColor: "rgba(255, 99, 132, 0.5)",
          borderColor: "rgba(255, 99, 132, 1)",
          borderWidth: 1,
        },
      ],
    },
    options: {
      aspectRatio: 3,
      plugins: {
        legend: {
          display: true,
        },
      },
      scales: {
        x: {
          grid: {
            display: false,
          },
          stacked: true,
          ticks: {
            autoSkip: false,
            maxRotation: 65,
            minRotation: 65,
          },
        },
        y: {
          beginAtZero: true,
          stacked: true,
          ticks: {
            callback: function (value) {
              return value.toLocaleString();
            },
          },
        },
      },
    },
  });
}
