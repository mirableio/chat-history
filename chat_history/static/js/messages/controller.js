import { escapeHtml, formatTextWithBreaks } from "@app/common";
import { createMessageBlocksRenderer } from "@app/messages-blocks";

export const MESSAGE_RENDER_MODE_MARKDOWN = "markdown";
export const MESSAGE_RENDER_MODE_PLAIN = "plain";

function normalizeRenderMode(mode) {
    return mode === MESSAGE_RENDER_MODE_PLAIN
        ? MESSAGE_RENDER_MODE_PLAIN
        : MESSAGE_RENDER_MODE_MARKDOWN;
}

function renderMarkdown(value) {
    const text = String(value || "");
    const marked = window.marked;
    if (!marked || typeof marked.parse !== "function") {
        return formatTextWithBreaks(text);
    }
    try {
        const rendered = marked.parse(text, { breaks: true });
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

export function createMessageRenderer({ findConversation, onToggleFavorite }) {
    const state = {
        mode: MESSAGE_RENDER_MODE_MARKDOWN,
        currentConversation: null,
    };

    function getRenderMode() {
        return normalizeRenderMode(state.mode);
    }

    function getCurrentConversation() {
        return state.currentConversation;
    }

    function setCurrentConversation(conversation) {
        state.currentConversation = conversation;
    }

    function renderBlockBody(value, { markdown = false } = {}) {
        if (markdown && getRenderMode() === MESSAGE_RENDER_MODE_MARKDOWN) {
            return renderMarkdown(value);
        }
        return formatTextWithBreaks(value);
    }

    const renderMessageBlocks = createMessageBlocksRenderer({ renderBlockBody });

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

    function renderConversationFavoriteToggleHtml(provider, convId, isFavorite) {
        const favoriteClass = isFavorite ? "is-favorite" : "";
        const favoriteHeart = isFavorite ? "♥" : "♡";
        return `
            <button
                class="conversation-favorite-btn ${favoriteClass}"
                id="conversation-favorite-toggle"
                data-provider="${escapeHtml(provider)}"
                data-conv-id="${escapeHtml(convId)}"
                type="button"
                aria-pressed="${isFavorite ? "true" : "false"}"
            >
                <span class="conversation-favorite-heart" aria-hidden="true">${favoriteHeart}</span>
            </button>
        `;
    }

    function setMainFavoriteButtonState(isFavorite) {
        const favoriteButton = document.getElementById("conversation-favorite-toggle");
        if (!favoriteButton) {
            return;
        }
        favoriteButton.classList.toggle("is-favorite", Boolean(isFavorite));
        favoriteButton.setAttribute("aria-pressed", isFavorite ? "true" : "false");
        const heart = favoriteButton.querySelector(".conversation-favorite-heart");
        if (heart) {
            heart.textContent = isFavorite ? "♥" : "♡";
        }
    }

    function setCurrentConversationFavorite(isFavorite) {
        if (state.currentConversation) {
            state.currentConversation.is_favorite = Boolean(isFavorite);
        }
        setMainFavoriteButtonState(Boolean(isFavorite));
    }

    async function handleConversationFavoriteClick(event) {
        const button = event.currentTarget;
        if (!button) {
            return;
        }
        const provider = button.dataset.provider;
        const convId = button.dataset.convId;
        if (!provider || !convId || typeof onToggleFavorite !== "function") {
            return;
        }

        button.disabled = true;
        button.classList.add("is-loading");
        try {
            await onToggleFavorite(provider, convId);
        } catch (error) {
            console.error("Failed to toggle favorite status:", error);
        } finally {
            button.disabled = false;
            button.classList.remove("is-loading");
        }
    }

    function renderConversationMessages(data, { preserveScroll = false } = {}) {
        state.currentConversation = data;

        const wrapper = document.getElementById("main-content-wrapper");
        const previousScroll = preserveScroll && wrapper ? wrapper.scrollTop : 0;
        const mainContent = document.getElementById("main-content");
        const summaryConversation = findConversation(data.provider, data.conversation_id);
        const isFavorite = summaryConversation
            ? Boolean(summaryConversation.is_favorite)
            : Boolean(data.is_favorite);
        data.is_favorite = isFavorite;

        mainContent.innerHTML = `
            <div class="p-2 border-b flex items-center justify-between gap-3 flex-wrap">
                <div class="flex items-center gap-3 min-w-0">
                    <span class="provider-badge provider-${data.provider}">${data.provider}</span>
                    <a href="${data.open_url}" target="_blank" rel="noopener noreferrer" class="hover:underline">
                        Open in ${data.provider === "claude" ? "Claude" : "ChatGPT"}
                        <span class="material-symbols-outlined" style="font-variation-settings: 'opsz' 48; vertical-align: sub; font-size: 18px !important">open_in_new</span>
                    </a>
                </div>
                <div class="conversation-header-actions">
                    ${renderConversationFavoriteToggleHtml(data.provider, data.conversation_id, isFavorite)}
                    ${renderModeToggleHtml()}
                </div>
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

        const favoriteToggle = document.getElementById("conversation-favorite-toggle");
        if (favoriteToggle) {
            favoriteToggle.addEventListener("click", handleConversationFavoriteClick);
        }

        if (preserveScroll && wrapper) {
            wrapper.scrollTop = previousScroll;
        }
    }

    function setRenderMode(mode, { rerender = false } = {}) {
        state.mode = normalizeRenderMode(mode);

        if (rerender && state.currentConversation) {
            renderConversationMessages(state.currentConversation, { preserveScroll: true });
        }
    }

    return {
        getCurrentConversation,
        getRenderMode,
        renderConversationMessages,
        setCurrentConversation,
        setCurrentConversationFavorite,
        setRenderMode,
    };
}
