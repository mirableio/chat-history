import { setActivityPayload, buildAIStatsBarChart } from "@app/activity-controller";
import { createMessageRenderer } from "@app/messages-controller";
import { searchConversations as runConversationSearch } from "@app/search";
import { createStatisticsController } from "@app/statistics";
import {
    loadActivityData,
    loadConversationsData,
    loadStatisticsData,
    loadTokenStatsData,
} from "@app/main-loaders";
import {
    buildInternalConversationUrl,
    parseConversationFromUrl,
    setConversationPreloadMode,
    updateConversationUrl,
} from "@app/main-navigation";
import { createSidebarController } from "@app/main-sidebar";
import { createActivityDayFilterController } from "@app/main-day-filter";
import { createConversationsController } from "@app/main-conversations";

const statisticsController = createStatisticsController();

let sidebarController;
let conversationsController;

const dayFilterController = createActivityDayFilterController({
    onFilterStateChanged: () => {
        if (sidebarController) {
            sidebarController.populateConversationsList();
        }
    },
});

sidebarController = createSidebarController({
    hasActivityDayFilter: dayFilterController.hasFilter,
    getActivityDayFilterState: dayFilterController.getState,
    parseConversationFromUrl,
    onOpenConversation: (provider, convId) => {
        if (conversationsController) {
            conversationsController.openConversation(provider, convId);
        }
    },
    onHeartClick: (event, provider, convId) => {
        if (conversationsController) {
            conversationsController.handleHeartClick(event, provider, convId);
        }
    },
});

const messageRenderer = createMessageRenderer({
    findConversation: (provider, convId) => sidebarController.findConversation(provider, convId),
    onToggleFavorite: (provider, convId) => conversationsController.toggleFavorite(provider, convId),
});

function scrollToTop() {
    document.getElementById("main-content-wrapper").scrollTop = 0;
}

conversationsController = createConversationsController({
    messageRenderer,
    parseConversationFromUrl,
    sidebarController,
    updateConversationUrl,
    onConversationLoaded: scrollToTop,
});

async function loadConversations() {
    try {
        const conversations = await loadConversationsData();
        sidebarController.setConversationData(conversations);
        sidebarController.populateGroupDropdown();
        sidebarController.populateProviderFilter();
        sidebarController.populateConversationsList();
    } catch (error) {
        console.error("Failed to load conversations:", error);
    }
}

async function loadActivityStats() {
    try {
        const data = await loadActivityData();
        setActivityPayload(data);
    } catch (error) {
        console.error("Failed to load activity graph:", error);
    }
}

async function loadChatStatistics() {
    try {
        const data = await loadStatisticsData();
        statisticsController.setPayload(data);
    } catch (error) {
        console.error("Error fetching chat statistics:", error);
    }
}

async function searchConversations(query) {
    await runConversationSearch({
        query,
        buildInternalConversationUrl,
        openConversation: (provider, convId) => conversationsController.openConversation(provider, convId),
        scrollToTop,
        unSelectConversation: () => sidebarController.unSelectConversation(),
    });
}

async function loadTokenStats() {
    scrollToTop();
    const mainContent = document.getElementById("main-content");
    mainContent.innerHTML = `<div class="pt-10 text-center">Loading...</div>`;

    try {
        const data = await loadTokenStatsData();
        buildAIStatsBarChart(data);
    } catch (error) {
        console.error("Error fetching token stats:", error);
    }
}

async function initializeMainView() {
    const selectionFromUrl = parseConversationFromUrl();
    if (selectionFromUrl) {
        setConversationPreloadMode(true);
        await loadConversations();
        const loaded = await conversationsController.openConversation(
            selectionFromUrl.provider,
            selectionFromUrl.convId,
            { updateUrl: false }
        );
        setConversationPreloadMode(false);
        if (!loaded) {
            await Promise.all([loadActivityStats(), loadChatStatistics()]);
        }
        return;
    }

    setConversationPreloadMode(false);
    await Promise.all([loadConversations(), loadActivityStats(), loadChatStatistics()]);
}

function handleSearchInput(event) {
    if (event.key !== "Enter") {
        return;
    }

    const query = encodeURIComponent(document.getElementById("search-input").value);
    if (query) {
        searchConversations(query);
    }
}

window.addEventListener("DOMContentLoaded", () => {
    window.addEventListener("activity-settings-changed", (event) => {
        statisticsController.applyActivitySettings(event.detail || {});
    });
    window.addEventListener("activity-day-selected", (event) => {
        const detail = event.detail || {};
        if (!detail.date) {
            return;
        }
        dayFilterController.apply(String(detail.date), detail.provider || null);
    });

    window.addEventListener("popstate", () => {
        if (!parseConversationFromUrl()) {
            window.location.reload();
            return;
        }
        conversationsController.openConversationFromUrl();
    });

    initializeMainView();
    dayFilterController.renderControl();

    document.getElementById("search-input").addEventListener("keydown", handleSearchInput);
    document.getElementById("groupFilter").addEventListener("change", () => {
        sidebarController.populateConversationsList();
    });
    document.getElementById("textFilter").addEventListener("input", () => {
        sidebarController.populateConversationsList();
    });
    const tokenStatsButton = document.getElementById("token-stats-button");
    if (tokenStatsButton) {
        tokenStatsButton.addEventListener("click", () => {
            loadTokenStats();
        });
    }
});
