export const ACTIVITY_ROLLING_PERIOD = "rolling";

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
  gemini: {
    heat: ["#eeeeee", "#bfdbfe", "#60a5fa", "#2563eb", "#1e3a8a"],
    barBg: "rgba(37, 99, 235, 0.45)",
    barBorder: "rgba(30, 64, 175, 1)",
  },
};

const ACTIVITY_FALLBACK_COLORS = [
  { barBg: "rgba(59, 130, 246, 0.45)", barBorder: "rgba(29, 78, 216, 1)" },
  { barBg: "rgba(168, 85, 247, 0.45)", barBorder: "rgba(126, 34, 206, 1)" },
  { barBg: "rgba(20, 184, 166, 0.45)", barBorder: "rgba(15, 118, 110, 1)" },
];

const ACTIVITY_SETTINGS_STORAGE_KEY = "chat-history.activity-settings.v1";

export function loadPersistedActivitySettings() {
  try {
    const raw = window.localStorage.getItem(ACTIVITY_SETTINGS_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return null;
    }
    return parsed;
  } catch (_error) {
    return null;
  }
}

export function savePersistedActivitySettings(state) {
  try {
    window.localStorage.setItem(
      ACTIVITY_SETTINGS_STORAGE_KEY,
      JSON.stringify({
        viewMode: state.viewMode,
        selectedProviders: Array.from(state.selectedProviders),
      })
    );
  } catch (_error) {
    // Ignore storage errors; activity settings still work in-memory.
  }
}

export function applyPersistedActivitySettings(state) {
  const persisted = loadPersistedActivitySettings();
  if (!persisted) {
    return;
  }

  const persistedViewMode = persisted.viewMode;
  if (persistedViewMode === "unified" || persistedViewMode === "provider") {
    state.viewMode = persistedViewMode;
  }

  if (Array.isArray(persisted.selectedProviders)) {
    if (persisted.selectedProviders.length === 0) {
      state.selectedProviders = new Set();
      return;
    }

    const nextProviders = persisted.selectedProviders
      .map((provider) => String(provider))
      .filter((provider, index, arr) => arr.indexOf(provider) === index)
      .filter((provider) => state.providers.includes(provider));

    if (nextProviders.length > 0) {
      state.selectedProviders = new Set(nextProviders);
      return;
    }

    state.selectedProviders = new Set(state.providers);
  }
}

export function getProviderTheme(provider, index) {
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

export function normalizeActivityPayload(rawPayload) {
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

export function resolveProvidersFromPayload(payload) {
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

export function getSelectedDayTotals(state) {
  const results = {};
  const days = state.payload?.days || {};
  const hasProviderDimension = state.providers.length > 0;

  for (const [day, entry] of Object.entries(days)) {
    if (!hasProviderDimension) {
      results[day] = Number(entry.total || 0);
      continue;
    }

    let total = 0;
    for (const provider of state.selectedProviders) {
      total += Number((entry.providers || {})[provider] || 0);
    }
    results[day] = total;
  }
  return results;
}

export function getSelectedProviderSeries(state) {
  const days = state.payload?.days || {};
  const providers = Array.from(state.selectedProviders);
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

export function extractYearsFromDayCounts(dayCounts) {
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

export function filterDayCountsByYear(dayCounts, selectedYear) {
  if (!Number.isInteger(selectedYear)) {
    return dayCounts;
  }
  const yearPrefix = `${selectedYear}-`;
  const filtered = {};
  for (const [day, count] of Object.entries(dayCounts)) {
    if (day.startsWith(yearPrefix)) {
      filtered[day] = Number(count || 0);
    }
  }
  return filtered;
}

export function filterProviderSeriesByYear(providerSeries, selectedYear) {
  if (!Number.isInteger(selectedYear)) {
    return providerSeries;
  }
  const yearPrefix = `${selectedYear}-`;
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

export function totalActivityCount(dayCounts) {
  return Object.values(dayCounts).reduce((sum, count) => sum + Number(count || 0), 0);
}
