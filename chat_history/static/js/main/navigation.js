export function parseConversationFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const provider = params.get("provider");
    const convId = params.get("conv_id");
    if (!provider || !convId) {
        return null;
    }
    return { provider, convId };
}

export function setConversationPreloadMode(active) {
    document.documentElement.classList.toggle("conversation-preload", Boolean(active));
}

export function buildInternalConversationUrl(provider, convId) {
    const url = new URL(window.location.href);
    url.searchParams.set("provider", provider);
    url.searchParams.set("conv_id", convId);
    return `${url.pathname}?${url.searchParams.toString()}`;
}

export function updateConversationUrl(provider, convId, { replace = false } = {}) {
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
