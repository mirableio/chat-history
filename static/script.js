let conversationData = [];
let selectedConvElem = null;
const THINKING_BLOCK_TYPES = new Set(["thinking", "thoughts", "reasoning_recap"]);
const TOOL_BLOCK_TYPES = new Set(["tool_use", "tool_result", "execution_output", "tether_browsing_display"]);
const ATTACHMENT_BLOCK_TYPES = new Set([
    "attachment",
    "file",
    "image_asset_pointer",
    "audio_asset_pointer",
    "real_time_user_audio_video_asset_pointer",
]);
const SYSTEM_BLOCK_TYPES = new Set(["system_error"]);
const statisticsState = {
    payload: null,
    viewMode: "unified",
    selectedProviders: [],
};
const MESSAGE_RENDER_MODE_MARKDOWN = "markdown";
const MESSAGE_RENDER_MODE_PLAIN = "plain";
const messageRenderState = {
    mode: MESSAGE_RENDER_MODE_MARKDOWN,
    currentConversation: null,
};
const activityDayFilterState = {
    date: null,
    provider: null,
    loading: false,
    matchedKeys: null,
};

function toConversationKey(provider, id) {
    return `${provider}::${id}`;
}

function hasActivityDayFilter() {
    return Boolean(activityDayFilterState.date);
}

function parseConversationFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const provider = params.get("provider");
    const convId = params.get("conv_id");
    if (!provider || !convId) {
        return null;
    }
    return { provider, convId };
}

function setConversationPreloadMode(active) {
    document.documentElement.classList.toggle("conversation-preload", Boolean(active));
}

function buildInternalConversationUrl(provider, convId) {
    const url = new URL(window.location.href);
    url.searchParams.set("provider", provider);
    url.searchParams.set("conv_id", convId);
    return `${url.pathname}?${url.searchParams.toString()}`;
}

function updateConversationUrl(provider, convId, { replace = false } = {}) {
    const nextUrl = buildInternalConversationUrl(provider, convId);
    const currentUrl = `${window.location.pathname}${window.location.search}`;
    if (nextUrl === currentUrl) {
        return;
    }
    if (replace) {
        window.history.replaceState({ provider, conv_id: convId }, "", nextUrl);
    } else {
        window.history.pushState({ provider, conv_id: convId }, "", nextUrl);
    }
}

function selectConversationRow(provider, convId) {
    const rowKey = toConversationKey(provider, convId);
    const row = Array.from(document.querySelectorAll("#sidebar-conversations > div"))
        .find(elem => elem.dataset && elem.dataset.key === rowKey);

    unSelectConversation();
    selectedConvElem = null;
    if (!row) {
        return;
    }

    row.classList.add("bg-gray-400");
    selectedConvElem = row;
}

function escapeSelector(value) {
    return value.replace(/[^a-zA-Z0-9_-]/g, "_");
}

function escapeHtml(value) {
    return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function formatBlockType(type) {
    return String(type || "unknown").replace(/_/g, " ");
}

function formatTextWithBreaks(value) {
    return escapeHtml(value).replace(/\n/g, "<br/>");
}

function normalizeRenderMode(mode) {
    return mode === MESSAGE_RENDER_MODE_PLAIN
        ? MESSAGE_RENDER_MODE_PLAIN
        : MESSAGE_RENDER_MODE_MARKDOWN;
}

function getRenderMode() {
    return normalizeRenderMode(messageRenderState.mode);
}

function renderMarkdown(value) {
    const text = String(value || "");
    const marked = window.marked;
    if (!marked || typeof marked.parse !== "function") {
        return formatTextWithBreaks(text);
    }
    try {
        const rendered = marked.parse(text);
        const template = document.createElement("template");
        template.innerHTML = rendered;
        template.content.querySelectorAll("a[href]").forEach((link) => {
            link.setAttribute("target", "_blank");
            link.setAttribute("rel", "noopener noreferrer");
        });
        return template.innerHTML;
    } catch (error) {
        console.error("Failed to parse markdown, using plain text:", error);
        return formatTextWithBreaks(text);
    }
}

function renderBlockBody(value, { markdown = false } = {}) {
    if (markdown && getRenderMode() === MESSAGE_RENDER_MODE_MARKDOWN) {
        return renderMarkdown(value);
    }
    return formatTextWithBreaks(value);
}

function firstLinePreview(value, maxLength = 140) {
    const firstLine = String(value || "")
        .split("\n")
        .map((line) => line.trim())
        .find(Boolean) || "";
    if (!firstLine) {
        return "";
    }
    if (firstLine.length <= maxLength) {
        return firstLine;
    }
    return `${firstLine.slice(0, maxLength - 1)}…`;
}

function renderCollapsibleBlock(className, label, text, summaryClassName, options = {}) {
    const preview = firstLinePreview(text);
    const previewHtml = preview
        ? `<span class="msg-block-summary-preview">${escapeHtml(preview)}</span>`
        : "";

    return `
        <details class="msg-block ${className}">
            <summary class="msg-block-summary ${summaryClassName}">
                <span class="msg-block-summary-label">${label}</span>
                ${previewHtml}
            </summary>
            <div class="msg-block-body">${renderBlockBody(text, options)}</div>
        </details>
    `;
}

function renderCollapsibleCodeBlock(label, text) {
    const preview = firstLinePreview(text);
    const previewHtml = preview
        ? `<span class="msg-block-summary-preview">${escapeHtml(preview)}</span>`
        : "";

    return `
        <details class="msg-block msg-block-code">
            <summary class="msg-block-summary msg-block-code-summary">
                <span class="msg-block-summary-label">${label}</span>
                ${previewHtml}
            </summary>
            <div class="msg-block-body">
                <pre><code>${escapeHtml(text)}</code></pre>
            </div>
        </details>
    `;
}

function renderMessageBlock(block) {
    const type = block?.type || "unknown";
    const label = formatBlockType(type);
    const text = block?.text || "";

    if (type === "code") {
        return renderCollapsibleCodeBlock(label, text);
    }

    if (THINKING_BLOCK_TYPES.has(type)) {
        return renderCollapsibleBlock(
            "msg-block-thinking",
            label,
            text,
            "msg-block-thinking-summary",
            { markdown: true }
        );
    }

    if (TOOL_BLOCK_TYPES.has(type)) {
        return renderCollapsibleBlock(
            "msg-block-tool",
            label,
            text,
            "msg-block-tool-summary",
            { markdown: type === "tool_result" }
        );
    }

    if (type === "text") {
        return `
            <div class="msg-block msg-block-text">
                <div class="msg-block-body">${renderBlockBody(text, { markdown: true })}</div>
            </div>
        `;
    }

    if (ATTACHMENT_BLOCK_TYPES.has(type)) {
        return `
            <div class="msg-block msg-block-asset">
                <div class="msg-block-label">${label}</div>
                <div class="msg-block-body">${formatTextWithBreaks(text)}</div>
            </div>
        `;
    }

    if (SYSTEM_BLOCK_TYPES.has(type)) {
        return `
            <div class="msg-block msg-block-system">
                <div class="msg-block-label">${label}</div>
                <div class="msg-block-body">${formatTextWithBreaks(text)}</div>
            </div>
        `;
    }

    return `
        <div class="msg-block msg-block-text">
            <div class="msg-block-label">${label}</div>
            <div class="msg-block-body">${renderBlockBody(text)}</div>
        </div>
    `;
}

function renderMessageBlocks(blocks) {
    if (!blocks || blocks.length === 0) {
        return `<div class="msg-block msg-block-empty">[No renderable blocks]</div>`;
    }
    return blocks.map(block => renderMessageBlock(block)).join("");
}

async function loadConversations() {
    try {
        const response = await fetch("/api/conversations");
        conversationData = await response.json();
        populateGroupDropdown(conversationData);
        populateConversationsList();
    } catch (error) {
        console.error("Failed to load conversations:", error);
    }
}

function populateGroupDropdown(conversations) {
    const groupSet = new Set();
    conversations.forEach(conv => {
        if (conv.group) {
            groupSet.add(conv.group);
        }
    });

    const groupFilterElem = document.getElementById("groupFilter");
    const existingValues = new Set(Array.from(groupFilterElem.options).map(option => option.value));
    Array.from(groupSet).forEach(group => {
        if (existingValues.has(group)) {
            return;
        }
        const optionElem = document.createElement("option");
        optionElem.value = group;
        optionElem.textContent = group;
        groupFilterElem.appendChild(optionElem);
    });
}

function populateConversationsList() {
    const sidebar = document.getElementById("sidebar-conversations");
    sidebar.innerHTML = "";
    selectedConvElem = null;

    const selectedGroup = document.getElementById("groupFilter").value;
    const searchText = document.getElementById("textFilter").value.toLowerCase();
    const hasDayFilter = hasActivityDayFilter();
    const matchedKeys = activityDayFilterState.matchedKeys || new Set();

    const filteredData = conversationData.filter(conv => {
        const conversationKey = toConversationKey(conv.provider, conv.id);
        const matchesActivityDay = !hasDayFilter || matchedKeys.has(conversationKey);
        const matchesGroup = hasDayFilter || (!selectedGroup || (conv.group && conv.group === selectedGroup)) ||
            (selectedGroup === "*" && conv.is_favorite);
        const matchesText = !searchText ||
            (conv.title && conv.title.toLowerCase().includes(searchText)) ||
            (conv.provider && conv.provider.toLowerCase().includes(searchText));
        return matchesActivityDay && matchesGroup && matchesText;
    });

    if (filteredData.length === 0 && hasDayFilter) {
        sidebar.insertAdjacentHTML("beforeend", `
            <div class="p-2 text-gray-500">
                ${activityDayFilterState.loading ? "Filtering by day..." : "No conversations for selected day."}
            </div>
        `);
    }

    let currentGroup = null;
    filteredData.forEach((conv, index) => {
        if (conv.group !== currentGroup) {
            currentGroup = conv.group;
            sidebar.insertAdjacentHTML("beforeend", `
                <div class="p-2 text-gray-700 font-bold">
                    ${currentGroup || "No Group"}
                </div>
            `);
        }

        const safeId = escapeSelector(`${conv.provider}-${conv.id}-${index}`);
        const rowId = `conv-${safeId}`;
        const key = toConversationKey(conv.provider, conv.id);

        sidebar.insertAdjacentHTML("beforeend", `
            <div class="p-2 hover:bg-gray-300 cursor-pointer flex justify-between relative group" id="${rowId}">
                <div class="inline-flex items-center gap-2 overflow-hidden">
                    <span class="provider-badge provider-${conv.provider}">${conv.provider}</span>
                    <span class="mr-2 truncate">${conv.title}</span>
                </div>
                <small class="text-gray-500 whitespace-nowrap" title="${conv.created.split(" ")[1]}">${conv.created.split(" ")[0]}</small>
                <div class="absolute right-24 top-0 pt-1 pr-1 group-hover:opacity-100 cursor-pointer heart-div ${conv.is_favorite ? "is-favorite" : ""}" onclick="handleHeartClick(event, '${conv.provider}', '${conv.id}')">
                    <span class="material-symbols-outlined heart-icon" style="font-variation-settings: 'opsz' 48; vertical-align: middle; font-size: 24px !important;">favorite</span>
                </div>
            </div>
        `);

        const row = document.getElementById(rowId);
        row.dataset.key = key;
        row.addEventListener("click", function () {
            openConversation(conv.provider, conv.id);
        });
    });

    const currentSelection = parseConversationFromUrl();
    if (currentSelection) {
        selectConversationRow(currentSelection.provider, currentSelection.convId);
    }
}

function renderActivityDayFilterControl() {
    const groupFilter = document.getElementById("groupFilter");
    const container = document.getElementById("activity-day-filter");
    if (!groupFilter || !container) {
        return;
    }

    if (!hasActivityDayFilter()) {
        container.classList.add("hidden");
        container.innerHTML = "";
        groupFilter.classList.remove("hidden");
        return;
    }

    const provider = activityDayFilterState.provider;
    const providerBadge = provider
        ? `<span class="provider-badge provider-${escapeSelector(provider)}">${escapeHtml(provider)}</span>`
        : "";
    const loadingClass = activityDayFilterState.loading ? "is-loading" : "";
    const clearButton = activityDayFilterState.loading
        ? ""
        : `<button class="activity-day-filter-clear" id="activity-day-filter-clear" type="button">✕</button>`;

    groupFilter.classList.add("hidden");
    container.classList.remove("hidden");
    container.innerHTML = `
        <div class="activity-day-filter-chip ${loadingClass}">
            <div class="activity-day-filter-main">
                <span class="activity-day-filter-label">
                    ${activityDayFilterState.loading ? "Filtering..." : `Day: ${escapeHtml(activityDayFilterState.date)}`}
                </span>
                ${providerBadge}
            </div>
            ${clearButton}
        </div>
    `;

    const clearButtonElement = document.getElementById("activity-day-filter-clear");
    if (clearButtonElement) {
        clearButtonElement.addEventListener("click", () => {
            clearActivityDayFilter();
        });
    }
}

function clearActivityDayFilter() {
    activityDayFilterState.date = null;
    activityDayFilterState.provider = null;
    activityDayFilterState.loading = false;
    activityDayFilterState.matchedKeys = null;
    renderActivityDayFilterControl();
    populateConversationsList();
}

async function applyActivityDayFilter(date, provider = null) {
    const normalizedProvider = provider || null;
    if (!date) {
        clearActivityDayFilter();
        return;
    }
    if (
        activityDayFilterState.date === date &&
        activityDayFilterState.provider === normalizedProvider &&
        !activityDayFilterState.loading
    ) {
        return;
    }

    activityDayFilterState.date = date;
    activityDayFilterState.provider = normalizedProvider;
    activityDayFilterState.loading = true;
    activityDayFilterState.matchedKeys = new Set();
    renderActivityDayFilterControl();
    populateConversationsList();

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

        if (
            activityDayFilterState.date !== date ||
            activityDayFilterState.provider !== normalizedProvider
        ) {
            return;
        }

        const matches = new Set(
            (payload.conversations || []).map((item) => toConversationKey(item.provider, item.id))
        );
        activityDayFilterState.matchedKeys = matches;
    } catch (error) {
        console.error("Failed to filter conversations by day:", error);
        if (
            activityDayFilterState.date !== date ||
            activityDayFilterState.provider !== normalizedProvider
        ) {
            return;
        }
        activityDayFilterState.matchedKeys = new Set();
    } finally {
        if (
            activityDayFilterState.date === date &&
            activityDayFilterState.provider === normalizedProvider
        ) {
            activityDayFilterState.loading = false;
            renderActivityDayFilterControl();
            populateConversationsList();
        }
    }
}

async function handleHeartClick(event, provider, convId) {
    event.stopPropagation();
    try {
        const response = await fetch(
            `/api/toggle_favorite?provider=${encodeURIComponent(provider)}&conv_id=${encodeURIComponent(convId)}`,
            { method: "POST" }
        );
        const data = await response.json();

        const conversation = conversationData.find(
            conv => conv.provider === provider && conv.id === convId
        );
        if (conversation) {
            conversation.is_favorite = data.is_favorite;
        }

        const rowKey = toConversationKey(provider, convId);
        const row = Array.from(document.querySelectorAll("#sidebar-conversations > div"))
            .find(elem => elem.dataset && elem.dataset.key === rowKey);
        if (!row) {
            return;
        }
        const heartContainer = row.querySelector(".heart-div");
        if (!heartContainer) {
            return;
        }
        if (data.is_favorite) {
            heartContainer.classList.add("is-favorite");
        } else {
            heartContainer.classList.remove("is-favorite");
        }
    } catch (error) {
        console.error("Failed to toggle favorite status:", error);
    }
}

async function openConversation(provider, convId, options = {}) {
    const updateUrl = options.updateUrl !== false;
    const replaceUrl = options.replaceUrl === true;

    const loaded = await loadChatMessages(provider, convId);
    if (!loaded) {
        return false;
    }

    selectConversationRow(provider, convId);
    if (updateUrl) {
        updateConversationUrl(provider, convId, { replace: replaceUrl });
    }
    return true;
}

async function openConversationFromUrl(options = {}) {
    const selection = parseConversationFromUrl();
    if (!selection) {
        return false;
    }
    return openConversation(selection.provider, selection.convId, {
        updateUrl: false,
        replaceUrl: options.replaceUrl === true,
    });
}

function renderModeToggleHtml() {
    const currentMode = getRenderMode();
    const markdownActive = currentMode === MESSAGE_RENDER_MODE_MARKDOWN ? "is-active is-markdown" : "";
    const plainActive = currentMode === MESSAGE_RENDER_MODE_PLAIN ? "is-active is-plain" : "";
    return `
        <div class="render-mode-toggle" id="render-mode-toggle">
            <button class="render-mode-btn ${markdownActive}" data-render-mode="${MESSAGE_RENDER_MODE_MARKDOWN}" type="button">
                Markdown
            </button>
            <button class="render-mode-btn ${plainActive}" data-render-mode="${MESSAGE_RENDER_MODE_PLAIN}" type="button">
                Plain text
            </button>
        </div>
    `;
}

function renderConversationMessages(data, { preserveScroll = false } = {}) {
    const wrapper = document.getElementById("main-content-wrapper");
    const previousScroll = preserveScroll && wrapper ? wrapper.scrollTop : 0;
    const mainContent = document.getElementById("main-content");

    mainContent.innerHTML = `
        <div class="p-2 border-b flex items-center justify-between gap-3 flex-wrap">
            <div class="flex items-center gap-3 min-w-0">
                <span class="provider-badge provider-${data.provider}">${data.provider}</span>
                <a href="${data.open_url}" target="_blank" rel="noopener noreferrer" class="hover:underline">
                    Open in ${data.provider === "claude" ? "Claude" : "ChatGPT"}
                    <span class="material-symbols-outlined" style="font-variation-settings: 'opsz' 48; vertical-align: sub; font-size: 18px !important">open_in_new</span>
                </a>
            </div>
            ${renderModeToggleHtml()}
        </div>
    `;

    let bgColorIndex = 0;
    data.messages.forEach((msg) => {
        const bgColorClass = bgColorIndex % 2 === 0 ? "" : "bg-gray-200";
        const renderedBlocks = msg.role === "internal"
            ? `<span class="text-gray-400">${escapeHtml(msg.text || "")}</span>`
            : renderMessageBlocks(msg.blocks || []);

        mainContent.insertAdjacentHTML("beforeend", `
            <div class="p-2 border-b ${bgColorClass}">
                <small class="text-gray-500">${msg.role === "internal" ? "" : msg.created}</small>
                <br/>
                <strong>${msg.role === "internal" ? "" : msg.role + ":"}</strong>
                <div class="${msg.role === "internal" ? "text-gray-400" : ""}">${renderedBlocks}</div>
            </div>
        `);
        if (msg.role !== "internal") {
            bgColorIndex++;
        }
    });

    const toggle = document.getElementById("render-mode-toggle");
    if (toggle) {
        toggle.querySelectorAll("button[data-render-mode]").forEach((button) => {
            button.addEventListener("click", () => {
                const nextMode = normalizeRenderMode(button.dataset.renderMode);
                if (nextMode === getRenderMode()) {
                    return;
                }
                setRenderMode(nextMode, { rerender: true });
            });
        });
    }

    if (preserveScroll && wrapper) {
        wrapper.scrollTop = previousScroll;
    }
}

function setRenderMode(mode, { rerender = false } = {}) {
    messageRenderState.mode = normalizeRenderMode(mode);

    if (rerender && messageRenderState.currentConversation) {
        renderConversationMessages(messageRenderState.currentConversation, { preserveScroll: true });
    }
}

async function loadChatMessages(provider, convId) {
    try {
        const response = await fetch(
            `/api/conversations/${encodeURIComponent(provider)}/${encodeURIComponent(convId)}/messages`
        );
        if (!response.ok) {
            return false;
        }
        const data = await response.json();
        messageRenderState.currentConversation = data;
        renderConversationMessages(data);
        scrollToTop();
        return true;
    } catch (error) {
        console.error("Failed to load messages:", error);
        return false;
    }
}

async function loadActivityStats() {
    try {
        const response = await fetch("/api/activity");
        const data = await response.json();
        if (typeof window.setActivityPayload === "function") {
            window.setActivityPayload(data);
        } else {
            buildActivityGraph(document.getElementById("activity-graph"), { data });
            buildActivityBarChart(data);
        }
    } catch (error) {
        console.error("Failed to load activity graph:", error);
    }
}

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
    const byProvider = statisticsState.payload?.by_provider || {};
    const availableProviders = Object.keys(byProvider).sort();
    if (statisticsState.selectedProviders.length === 0) {
        return availableProviders;
    }
    const selected = new Set(statisticsState.selectedProviders);
    return availableProviders.filter((provider) => selected.has(provider));
}

function renderChatStatistics() {
    const tableContainer = document.getElementById("chat-statistics");
    tableContainer.innerHTML = "";

    if (!statisticsState.payload) {
        return;
    }

    const byProvider = statisticsState.payload.by_provider || {};
    const summary = statisticsState.payload.summary || {};
    const shouldSplitByProvider =
        statisticsState.viewMode === "provider" && Object.keys(byProvider).length > 0;

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

function applyActivitySettingsToStatistics(settings) {
    if (!settings || typeof settings !== "object") {
        return;
    }
    statisticsState.viewMode = settings.viewMode === "provider" ? "provider" : "unified";
    statisticsState.selectedProviders = Array.isArray(settings.selectedProviders)
        ? settings.selectedProviders
        : [];
    renderChatStatistics();
}

async function loadChatStatistics() {
    try {
        const response = await fetch("/api/statistics");
        const data = await response.json();
        statisticsState.payload = normalizeStatisticsPayload(data);
        renderChatStatistics();
    } catch (error) {
        console.error("Error fetching chat statistics:", error);
    }
}

async function searchConversations(query) {
    try {
        const mainContent = document.getElementById("main-content");
        mainContent.innerHTML = `
            <div class="p-2 pt-8">
                Searching...
                <span class="material-symbols-outlined" style="font-variation-settings: 'opsz' 48; vertical-align: sub; font-size: 18px !important">hourglass_top</span>
            </div>
        `;

        const response = await fetch(`/api/search?query=${query}`);
        const data = await response.json();
        mainContent.innerHTML = "";

        if (data.length === 0) {
            mainContent.insertAdjacentHTML("beforeend", `
                <div class="p-2 pt-8">No results found.</div>
            `);
        } else {
            data.forEach((msg, index) => {
                const bgColorClass = index % 2 === 0 ? "" : "bg-gray-200";
                const providerLabel = msg.provider || "unknown";
                const canOpenInternally = Boolean(msg.provider && msg.id);
                const titleHtml = escapeHtml(msg.title || "Untitled");
                const internalUrl = msg.internal_url || buildInternalConversationUrl(msg.provider, msg.id);
                const internalLinkHtml = canOpenInternally
                    ? `
                        <a
                            href="${internalUrl}"
                            class="hover:underline search-open-internal"
                            data-provider="${escapeHtml(msg.provider || "")}"
                            data-conv-id="${escapeHtml(msg.id || "")}"
                        >
                            ${titleHtml}
                        </a>
                    `
                    : `<span>${titleHtml}</span>`;
                mainContent.insertAdjacentHTML("beforeend", `
                    <div class="p-2 border-b pb-12 ${bgColorClass}">
                        <div class="flex items-center gap-2 flex-wrap">
                            <span class="provider-badge provider-${providerLabel}">${providerLabel}</span>
                            ${internalLinkHtml}
                            <a href="${msg.open_url}" target="_blank" rel="noopener noreferrer" class="hover:underline text-gray-500">
                                external
                                <span class="material-symbols-outlined" style="font-variation-settings: 'opsz' 48; vertical-align: middle; font-size: 18px !important">open_in_new</span>
                            </a>
                        </div>
                        <strong>${msg.role}:</strong>
                        <span>${msg.text}</span>
                        <small class="text-gray-500">${msg.created}</small>
                    </div>
                `);
            });

            mainContent.querySelectorAll(".search-open-internal").forEach((link) => {
                link.addEventListener("click", async (event) => {
                    const provider = link.dataset.provider;
                    const convId = link.dataset.convId;
                    if (!provider || !convId) {
                        return;
                    }
                    event.preventDefault();
                    await openConversation(provider, convId);
                });
            });
        }

        scrollToTop();
        unSelectConversation();
    } catch (error) {
        console.error("Search failed:", error);
    }
}

async function loadTokenStats() {
    scrollToTop();
    const mainContent = document.getElementById("main-content");
    mainContent.innerHTML = `<div class="pt-10 text-center">Loading...</div>`;

    try {
        const response = await fetch("/api/ai-cost");
        const data = await response.json();
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
        const loaded = await openConversation(selectionFromUrl.provider, selectionFromUrl.convId, {
            updateUrl: false,
        });
        setConversationPreloadMode(false);
        if (!loaded) {
            await Promise.all([loadActivityStats(), loadChatStatistics()]);
        }
        return;
    }

    setConversationPreloadMode(false);
    await Promise.all([loadConversations(), loadActivityStats(), loadChatStatistics()]);
}

function scrollToTop() {
    document.getElementById("main-content-wrapper").scrollTop = 0;
}

function unSelectConversation() {
    if (selectedConvElem) {
        selectedConvElem.classList.remove("bg-gray-400");
    }
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
        applyActivitySettingsToStatistics(event.detail || {});
    });
    window.addEventListener("activity-day-selected", (event) => {
        const detail = event.detail || {};
        if (!detail.date) {
            return;
        }
        applyActivityDayFilter(String(detail.date), detail.provider || null);
    });

    window.addEventListener("popstate", () => {
        if (!parseConversationFromUrl()) {
            window.location.reload();
            return;
        }
        openConversationFromUrl();
    });

    initializeMainView();
    renderActivityDayFilterControl();

    document.getElementById("search-input").addEventListener("keydown", handleSearchInput);
    document.getElementById("groupFilter").addEventListener("change", populateConversationsList);
    document.getElementById("textFilter").addEventListener("input", populateConversationsList);
});
