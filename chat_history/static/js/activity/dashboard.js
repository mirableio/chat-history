import {
  buildActivityBarChart,
  buildActivityBarChartByProvider,
  buildActivityGraph,
} from "@app/activity-charts";
import {
  ACTIVITY_ROLLING_PERIOD,
  extractYearsFromDayCounts,
  filterDayCountsByYear,
  filterProviderSeriesByYear,
  getProviderTheme,
  getSelectedDayTotals,
  getSelectedProviderSeries,
  totalActivityCount,
} from "@app/activity-state";

function renderYearBadges({ activityState, onRerenderRequested }) {
  const container = document.getElementById("activity-year-badges");
  if (!container) {
    return;
  }

  const dayCounts = getSelectedDayTotals(activityState);
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
      if (typeof onRerenderRequested === "function") {
        onRerenderRequested();
      }
    });
  });
}

function showActivityEmptyState() {
  const graphContainer = document.getElementById("activity-graph");
  graphContainer.innerHTML = `<div class="activity-empty-state">No provider selected.</div>`;
  buildActivityBarChart({});
}

function renderUnifiedActivityView(dayCounts, year, onDaySelected) {
  const graphContainer = document.getElementById("activity-graph");
  graphContainer.innerHTML = "";
  buildActivityGraph(graphContainer, {
    data: dayCounts,
    year,
    click: (date, count) => {
      if (Number(count || 0) <= 0) {
        return;
      }
      onDaySelected(date, null);
    },
  });
  buildActivityBarChart(dayCounts, year);
}

function renderProviderActivityView(providerSeries, year, onDaySelected) {
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
      click: (date, count) => {
        if (Number(count || 0) <= 0) {
          return;
        }
        onDaySelected(date, provider);
      },
    });
  });

  buildActivityBarChartByProvider(providerSeries, year, getProviderTheme);
}

export function renderActivityDashboard({
  activityState,
  onDaySelected,
  onRerenderRequested,
}) {
  if (!activityState.payload) {
    return;
  }

  renderYearBadges({ activityState, onRerenderRequested });

  const dayTotals = getSelectedDayTotals(activityState);
  const filteredDayTotals = filterDayCountsByYear(dayTotals, activityState.selectedYear);
  if (totalActivityCount(filteredDayTotals) === 0) {
    showActivityEmptyState();
    return;
  }

  if (activityState.viewMode === "provider" && activityState.selectedProviders.size > 0) {
    const providerSeries = filterProviderSeriesByYear(
      getSelectedProviderSeries(activityState),
      activityState.selectedYear
    );
    renderProviderActivityView(providerSeries, activityState.selectedYear, onDaySelected);
    return;
  }

  renderUnifiedActivityView(filteredDayTotals, activityState.selectedYear, onDaySelected);
}
