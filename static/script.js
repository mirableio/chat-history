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

function toConversationKey(provider, id) {
    return `${provider}::${id}`;
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

function renderMessageBlock(block) {
    const type = block?.type || "unknown";
    const label = formatBlockType(type);
    const text = block?.text || "";

    if (type === "code") {
        return `
            <div class="msg-block msg-block-code">
                <div class="msg-block-label">${label}</div>
                <pre><code>${escapeHtml(text)}</code></pre>
            </div>
        `;
    }

    if (THINKING_BLOCK_TYPES.has(type)) {
        return `
            <details class="msg-block msg-block-thinking" open>
                <summary>${label}</summary>
                <div class="msg-block-body">${formatTextWithBreaks(text)}</div>
            </details>
        `;
    }

    if (TOOL_BLOCK_TYPES.has(type)) {
        return `
            <div class="msg-block msg-block-tool">
                <div class="msg-block-label">${label}</div>
                <div class="msg-block-body">${formatTextWithBreaks(text)}</div>
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
            <div class="msg-block-body">${formatTextWithBreaks(text)}</div>
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

    const selectedGroup = document.getElementById("groupFilter").value;
    const searchText = document.getElementById("textFilter").value.toLowerCase();

    const filteredData = conversationData.filter(conv => {
        const matchesGroup = (!selectedGroup || (conv.group && conv.group === selectedGroup)) ||
            (selectedGroup === "*" && conv.is_favorite);
        const matchesText = !searchText ||
            (conv.title && conv.title.toLowerCase().includes(searchText)) ||
            (conv.provider && conv.provider.toLowerCase().includes(searchText));
        return matchesGroup && matchesText;
    });

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
                    <small class="text-gray-500 whitespace-nowrap">${conv.total_length}</small>
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
            loadChatMessages(conv.provider, conv.id);
            unSelectConversation();
            this.classList.add("bg-gray-400");
            selectedConvElem = this;
        });
    });
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

async function loadChatMessages(provider, convId) {
    try {
        const response = await fetch(
            `/api/conversations/${encodeURIComponent(provider)}/${encodeURIComponent(convId)}/messages`
        );
        const data = await response.json();
        const mainContent = document.getElementById("main-content");
        mainContent.innerHTML = `
            <div class="p-2 border-b text-right flex items-center justify-end gap-3">
                <span class="provider-badge provider-${data.provider}">${data.provider}</span>
                <a href="${data.open_url}" target="_blank" rel="noopener noreferrer" class="hover:underline">
                    Open in ${data.provider === "claude" ? "Claude" : "ChatGPT"}
                    <span class="material-symbols-outlined" style="font-variation-settings: 'opsz' 48; vertical-align: sub; font-size: 18px !important">open_in_new</span>
                </a>
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

        scrollToTop();
    } catch (error) {
        console.error("Failed to load messages:", error);
    }
}

async function loadActivityStats() {
    try {
        const response = await fetch("/api/activity");
        const data = await response.json();
        buildActivityGraph(document.getElementById("activity-graph"), { data });
        buildActivityBarChart(data);
    } catch (error) {
        console.error("Failed to load activity graph:", error);
    }
}

async function loadChatStatistics() {
    try {
        const response = await fetch("/api/statistics");
        const data = await response.json();
        const tableContainer = document.getElementById("chat-statistics");
        tableContainer.innerHTML = "";

        let tableHTML = `<table class="min-w-full bg-white"><tbody>`;
        for (const [key, value] of Object.entries(data)) {
            tableHTML += `
                <tr>
                    <td class="py-2 px-4 border-b">${key}</td>
                    <td class="py-2 px-4 border-b">${value}</td>
                </tr>
            `;
        }
        tableHTML += `</tbody></table>`;
        tableContainer.insertAdjacentHTML("beforeend", tableHTML);
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
                mainContent.insertAdjacentHTML("beforeend", `
                    <div class="p-2 border-b pb-12 ${bgColorClass}">
                        <div class="flex items-center gap-2">
                            <span class="provider-badge provider-${providerLabel}">${providerLabel}</span>
                            <a href="${msg.open_url}" target="_blank" rel="noopener noreferrer" class="hover:underline">
                                ${msg.title}
                                <span class="material-symbols-outlined" style="font-variation-settings: 'opsz' 48; vertical-align: middle; font-size: 18px !important">open_in_new</span>
                            </a>
                        </div>
                        <strong>${msg.role}:</strong>
                        <span>${msg.text}</span>
                        <small class="text-gray-500">${msg.created}</small>
                    </div>
                `);
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
    loadConversations();
    loadActivityStats();
    loadChatStatistics();

    document.getElementById("search-input").addEventListener("keydown", handleSearchInput);
    document.getElementById("groupFilter").addEventListener("change", populateConversationsList);
    document.getElementById("textFilter").addEventListener("input", populateConversationsList);
});
