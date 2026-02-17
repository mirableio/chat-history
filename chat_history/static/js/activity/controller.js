import { buildAIStatsBarChart } from "@app/activity-charts";
import {
  ACTIVITY_ROLLING_PERIOD,
  applyPersistedActivitySettings,
  normalizeActivityPayload,
  resolveProvidersFromPayload,
  savePersistedActivitySettings,
} from "@app/activity-state";
import { renderActivityDashboard } from "@app/activity-dashboard";

export { buildAIStatsBarChart };

const activityState = {
  payload: null,
  providers: [],
  selectedProviders: new Set(),
  selectedYear: ACTIVITY_ROLLING_PERIOD,
  viewMode: "unified",
  controlsInitialized: false,
};

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

function notifyActivityDaySelected(day, provider = null) {
  if (!day) {
    return;
  }
  window.dispatchEvent(
    new CustomEvent("activity-day-selected", {
      detail: {
        date: day,
        provider,
      },
    })
  );
}

function rerenderDashboard() {
  renderActivityDashboard({
    activityState,
    onDaySelected: notifyActivityDaySelected,
    onRerenderRequested: rerenderDashboard,
  });
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
      savePersistedActivitySettings(activityState);
      rerenderDashboard();
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
        savePersistedActivitySettings(activityState);
        rerenderDashboard();
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

export function setActivityPayload(rawPayload) {
  activityState.payload = normalizeActivityPayload(rawPayload);
  activityState.providers = resolveProvidersFromPayload(activityState.payload);
  activityState.selectedProviders = new Set(activityState.providers);
  activityState.selectedYear = ACTIVITY_ROLLING_PERIOD;
  applyPersistedActivitySettings(activityState);
  if (activityState.providers.length < 2) {
    activityState.viewMode = "unified";
  }
  savePersistedActivitySettings(activityState);

  bindActivityControlEvents();
  updateActivityControlsVisibility();
  renderProviderFilters();
  renderViewModeControls();
  rerenderDashboard();
  notifyActivitySettingsChanged();
}
