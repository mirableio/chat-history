import { escapeHtml } from "@app/common";

export function createStatisticsController() {
    const state = {
        payload: null,
        viewMode: "unified",
        selectedProviders: [],
    };

    function normalizeStatisticsPayload(rawPayload) {
        if (rawPayload && typeof rawPayload === "object" && rawPayload.summary) {
            return {
                summary: rawPayload.summary || {},
                by_provider: rawPayload.by_provider || {},
            };
        }
        return {
            summary: rawPayload || {},
            by_provider: {},
        };
    }

    function statisticsRowsHtml(stats) {
        let rows = "";
        for (const [key, value] of Object.entries(stats || {})) {
            rows += `
                <tr>
                    <td class="py-2 px-3 border-b border-gray-200">${escapeHtml(key)}</td>
                    <td class="py-2 px-3 border-b border-gray-200 text-right">${escapeHtml(value)}</td>
                </tr>
            `;
        }
        return rows;
    }

    function renderStatisticsTable(container, titleHtml, stats) {
        container.insertAdjacentHTML("beforeend", `
            <div class="stats-table-card">
                <div class="stats-table-title">${titleHtml}</div>
                <table class="min-w-full bg-white">
                    <tbody>${statisticsRowsHtml(stats)}</tbody>
                </table>
            </div>
        `);
    }

    function selectedStatisticsProviders() {
        const byProvider = state.payload?.by_provider || {};
        const availableProviders = Object.keys(byProvider).sort();
        if (state.selectedProviders.length === 0) {
            return availableProviders;
        }
        const selected = new Set(state.selectedProviders);
        return availableProviders.filter((provider) => selected.has(provider));
    }

    function render() {
        const tableContainer = document.getElementById("chat-statistics");
        if (!tableContainer) {
            return;
        }
        tableContainer.innerHTML = "";

        if (!state.payload) {
            return;
        }

        const byProvider = state.payload.by_provider || {};
        const summary = state.payload.summary || {};
        const shouldSplitByProvider =
            state.viewMode === "provider" && Object.keys(byProvider).length > 0;

        if (!shouldSplitByProvider) {
            renderStatisticsTable(tableContainer, "All providers", summary);
            return;
        }

        const providers = selectedStatisticsProviders();
        if (providers.length === 0) {
            tableContainer.insertAdjacentHTML(
                "beforeend",
                `<div class="activity-empty-state">No provider selected.</div>`
            );
            return;
        }

        const grid = document.createElement("div");
        grid.className = "stats-tables-grid";
        tableContainer.appendChild(grid);

        providers.forEach((provider) => {
            renderStatisticsTable(
                grid,
                `<span class="provider-badge provider-${provider}">${escapeHtml(provider)}</span>`,
                byProvider[provider] || {}
            );
        });
    }

    function setPayload(rawPayload) {
        state.payload = normalizeStatisticsPayload(rawPayload);
        render();
    }

    function applyActivitySettings(settings) {
        if (!settings || typeof settings !== "object") {
            return;
        }
        state.viewMode = settings.viewMode === "provider" ? "provider" : "unified";
        state.selectedProviders = Array.isArray(settings.selectedProviders)
            ? settings.selectedProviders
            : [];
        render();
    }

    return {
        applyActivitySettings,
        render,
        setPayload,
    };
}
