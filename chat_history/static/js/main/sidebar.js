import { escapeSelector, toConversationKey } from "@app/common";

export function createSidebarController({
    hasActivityDayFilter,
    getActivityDayFilterState,
    parseConversationFromUrl,
    onOpenConversation,
    onHeartClick,
}) {
    let conversationData = [];
    let selectedConvElem = null;
    let activeProvider = ""; // "" = all

    function setConversationData(conversations) {
        conversationData = Array.isArray(conversations) ? conversations : [];
    }

    function getConversationData() {
        return conversationData;
    }

    function findConversation(provider, convId) {
        return conversationData.find(
            (conv) => conv.provider === provider && conv.id === convId
        ) || null;
    }

    function unSelectConversation() {
        if (selectedConvElem) {
            selectedConvElem.classList.remove("bg-gray-400");
        }
    }

    function selectConversationRow(provider, convId) {
        const rowKey = toConversationKey(provider, convId);
        const row = Array.from(document.querySelectorAll("#sidebar-conversations > div"))
            .find((elem) => elem.dataset && elem.dataset.key === rowKey);

        unSelectConversation();
        selectedConvElem = null;
        if (!row) {
            return;
        }

        row.classList.add("bg-gray-400");
        selectedConvElem = row;
    }

    function setConversationRowFavorite(provider, convId, isFavorite) {
        const rowKey = toConversationKey(provider, convId);
        const row = Array.from(document.querySelectorAll("#sidebar-conversations > div"))
            .find((elem) => elem.dataset && elem.dataset.key === rowKey);
        if (!row) {
            return;
        }
        const heartContainer = row.querySelector(".heart-div");
        if (!heartContainer) {
            return;
        }
        heartContainer.classList.toggle("is-favorite", Boolean(isFavorite));
    }

    function populateGroupDropdown() {
        const groupSet = new Set();
        conversationData.forEach((conv) => {
            if (conv.group) {
                groupSet.add(conv.group);
            }
        });

        const groupFilterElem = document.getElementById("groupFilter");
        const existingValues = new Set(Array.from(groupFilterElem.options).map((option) => option.value));
        Array.from(groupSet).forEach((group) => {
            if (existingValues.has(group)) {
                return;
            }
            const optionElem = document.createElement("option");
            optionElem.value = group;
            optionElem.textContent = group;
            groupFilterElem.appendChild(optionElem);
        });
    }

    function populateProviderFilter() {
        const container = document.getElementById("providerFilter");
        const providers = [...new Set(conversationData.map((c) => c.provider).filter(Boolean))].sort();
        if (providers.length < 2) {
            container.classList.add("hidden");
            activeProvider = "";
            return;
        }
        container.classList.remove("hidden");
        container.innerHTML = "";

        const allBtn = document.createElement("button");
        allBtn.textContent = "All";
        allBtn.className = "provider-filter-btn" + (!activeProvider ? " active" : "");
        allBtn.addEventListener("click", () => { activeProvider = ""; refreshProviderButtons(); populateConversationsList(); });
        container.appendChild(allBtn);

        providers.forEach((p) => {
            const btn = document.createElement("button");
            btn.textContent = p;
            btn.className = `provider-filter-btn provider-filter-${p}` + (activeProvider === p ? " active" : "");
            btn.addEventListener("click", () => { activeProvider = p; refreshProviderButtons(); populateConversationsList(); });
            container.appendChild(btn);
        });

        function refreshProviderButtons() {
            container.querySelectorAll(".provider-filter-btn").forEach((b) => {
                const isAll = b.textContent === "All";
                const isActive = isAll ? !activeProvider : activeProvider === b.textContent;
                b.classList.toggle("active", isActive);
            });
        }
    }

    function populateConversationsList() {
        const sidebar = document.getElementById("sidebar-conversations");
        sidebar.innerHTML = "";
        selectedConvElem = null;

        const selectedGroup = document.getElementById("groupFilter").value;
        const searchText = document.getElementById("textFilter").value.toLowerCase();
        const hasDayFilter = hasActivityDayFilter();
        const dayFilterState = getActivityDayFilterState();
        const matchedKeys = dayFilterState.matchedKeys || new Set();

        const filteredData = conversationData.filter((conv) => {
            const conversationKey = toConversationKey(conv.provider, conv.id);
            const matchesActivityDay = !hasDayFilter || matchedKeys.has(conversationKey);
            const matchesGroup = hasDayFilter
                || (!selectedGroup || (conv.group && conv.group === selectedGroup))
                || (selectedGroup === "*" && conv.is_favorite);
            const matchesText = !searchText
                || (conv.title && conv.title.toLowerCase().includes(searchText))
                || (conv.provider && conv.provider.toLowerCase().includes(searchText));
            const matchesProvider = !activeProvider || conv.provider === activeProvider;
            return matchesActivityDay && matchesGroup && matchesText && matchesProvider;
        });

        if (filteredData.length === 0 && hasDayFilter) {
            sidebar.insertAdjacentHTML("beforeend", `
                <div class="p-2 text-gray-500">
                    ${dayFilterState.loading ? "Filtering by day..." : "No conversations for selected day."}
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
                    <div class="absolute cursor-pointer heart-div ${conv.is_favorite ? "is-favorite" : ""}">
                        <span class="heart-emoji" aria-hidden="true"></span>
                    </div>
                </div>
            `);

            const row = document.getElementById(rowId);
            row.dataset.key = key;
            row.addEventListener("click", () => {
                onOpenConversation(conv.provider, conv.id);
            });

            const heartContainer = row.querySelector(".heart-div");
            if (heartContainer) {
                heartContainer.addEventListener("click", (event) => {
                    onHeartClick(event, conv.provider, conv.id);
                });
            }
        });

        const currentSelection = parseConversationFromUrl();
        if (currentSelection) {
            selectConversationRow(currentSelection.provider, currentSelection.convId);
        }
    }

    return {
        findConversation,
        getConversationData,
        populateConversationsList,
        populateGroupDropdown,
        populateProviderFilter,
        selectConversationRow,
        setConversationData,
        setConversationRowFavorite,
        unSelectConversation,
    };
}
