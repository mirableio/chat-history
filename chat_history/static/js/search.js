import { escapeHtml } from "@app/common";

export async function searchConversations({
    query,
    buildInternalConversationUrl,
    openConversation,
    scrollToTop,
    unSelectConversation,
}) {
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
