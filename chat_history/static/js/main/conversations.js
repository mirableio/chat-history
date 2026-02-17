import { loadConversationMessages } from "@app/main-loaders";

export function createConversationsController({
    messageRenderer,
    parseConversationFromUrl,
    sidebarController,
    updateConversationUrl,
    onConversationLoaded,
}) {
    function setConversationFavoriteState(provider, convId, isFavorite) {
        const conversation = sidebarController.findConversation(provider, convId);
        if (conversation) {
            conversation.is_favorite = Boolean(isFavorite);
        }

        const currentConversation = messageRenderer.getCurrentConversation();
        if (
            currentConversation
            && currentConversation.provider === provider
            && currentConversation.conversation_id === convId
        ) {
            messageRenderer.setCurrentConversationFavorite(Boolean(isFavorite));
        }

        sidebarController.setConversationRowFavorite(provider, convId, isFavorite);
    }

    async function toggleFavorite(provider, convId) {
        const response = await fetch(
            `/api/toggle_favorite?provider=${encodeURIComponent(provider)}&conv_id=${encodeURIComponent(convId)}`,
            { method: "POST" }
        );
        if (!response.ok) {
            throw new Error(`Failed to toggle favorite: ${response.status}`);
        }
        const data = await response.json();
        const isFavorite = Boolean(data.is_favorite);
        setConversationFavoriteState(provider, convId, isFavorite);
        return isFavorite;
    }

    async function handleHeartClick(event, provider, convId) {
        event.stopPropagation();
        try {
            await toggleFavorite(provider, convId);
        } catch (error) {
            console.error("Failed to toggle favorite status:", error);
        }
    }

    async function loadChatMessages(provider, convId) {
        try {
            const data = await loadConversationMessages(provider, convId);
            if (!data) {
                return false;
            }
            messageRenderer.setCurrentConversation(data);
            messageRenderer.renderConversationMessages(data);
            if (typeof onConversationLoaded === "function") {
                onConversationLoaded();
            }
            return true;
        } catch (error) {
            console.error("Failed to load messages:", error);
            return false;
        }
    }

    async function openConversation(provider, convId, options = {}) {
        const updateUrl = options.updateUrl !== false;
        const replaceUrl = options.replaceUrl === true;

        const loaded = await loadChatMessages(provider, convId);
        if (!loaded) {
            return false;
        }

        sidebarController.selectConversationRow(provider, convId);
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

    return {
        handleHeartClick,
        openConversation,
        openConversationFromUrl,
        toggleFavorite,
    };
}
