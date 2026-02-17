import { escapeHtml, escapeSelector, toConversationKey } from "@app/common";

export function createActivityDayFilterController({ onFilterStateChanged }) {
    const state = {
        date: null,
        provider: null,
        loading: false,
        matchedKeys: null,
    };

    function hasFilter() {
        return Boolean(state.date);
    }

    function getState() {
        return state;
    }

    function notifyFilterStateChanged() {
        if (typeof onFilterStateChanged === "function") {
            onFilterStateChanged();
        }
    }

    function renderControl() {
        const groupFilter = document.getElementById("groupFilter");
        const container = document.getElementById("activity-day-filter");
        if (!groupFilter || !container) {
            return;
        }

        if (!hasFilter()) {
            container.classList.add("hidden");
            container.innerHTML = "";
            groupFilter.classList.remove("hidden");
            return;
        }

        const providerBadge = state.provider
            ? `<span class="provider-badge provider-${escapeSelector(state.provider)}">${escapeHtml(state.provider)}</span>`
            : "";
        const loadingClass = state.loading ? "is-loading" : "";
        const clearButton = state.loading
            ? ""
            : `<button class="activity-day-filter-clear" id="activity-day-filter-clear" type="button">✕</button>`;

        groupFilter.classList.add("hidden");
        container.classList.remove("hidden");
        container.innerHTML = `
            <div class="activity-day-filter-chip ${loadingClass}">
                <div class="activity-day-filter-main">
                    <span class="activity-day-filter-label">
                        ${state.loading ? "Filtering..." : `Day: ${escapeHtml(state.date)}`}
                    </span>
                    ${providerBadge}
                </div>
                ${clearButton}
            </div>
        `;

        const clearButtonElement = document.getElementById("activity-day-filter-clear");
        if (clearButtonElement) {
            clearButtonElement.addEventListener("click", () => {
                clear();
            });
        }
    }

    function clear() {
        state.date = null;
        state.provider = null;
        state.loading = false;
        state.matchedKeys = null;
        renderControl();
        notifyFilterStateChanged();
    }

    async function apply(date, provider = null) {
        const normalizedProvider = provider || null;
        if (!date) {
            clear();
            return;
        }

        if (
            state.date === date
            && state.provider === normalizedProvider
            && !state.loading
        ) {
            return;
        }

        state.date = date;
        state.provider = normalizedProvider;
        state.loading = true;
        state.matchedKeys = new Set();
        renderControl();
        notifyFilterStateChanged();

        try {
            const queryParams = new URLSearchParams({ date });
            if (normalizedProvider) {
                queryParams.set("provider", normalizedProvider);
            }
            const response = await fetch(`/api/activity/day?${queryParams.toString()}`);
            if (!response.ok) {
                throw new Error(`Activity day request failed: ${response.status}`);
            }
            const payload = await response.json();

            if (state.date !== date || state.provider !== normalizedProvider) {
                return;
            }

            state.matchedKeys = new Set(
                (payload.conversations || []).map((item) => toConversationKey(item.provider, item.id))
            );
        } catch (error) {
            console.error("Failed to filter conversations by day:", error);
            if (state.date !== date || state.provider !== normalizedProvider) {
                return;
            }
            state.matchedKeys = new Set();
        } finally {
            if (state.date === date && state.provider === normalizedProvider) {
                state.loading = false;
                renderControl();
                notifyFilterStateChanged();
            }
        }
    }

    return {
        apply,
        clear,
        getState,
        hasFilter,
        renderControl,
    };
}
