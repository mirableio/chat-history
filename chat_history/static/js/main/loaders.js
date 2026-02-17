export async function loadConversationsData() {
    const response = await fetch("/api/conversations");
    if (!response.ok) {
        throw new Error(`Failed to fetch conversations: ${response.status}`);
    }
    return response.json();
}

export async function loadConversationMessages(provider, convId) {
    const response = await fetch(
        `/api/conversations/${encodeURIComponent(provider)}/${encodeURIComponent(convId)}/messages`
    );
    if (!response.ok) {
        return null;
    }
    return response.json();
}

export async function loadActivityData() {
    const response = await fetch("/api/activity");
    if (!response.ok) {
        throw new Error(`Failed to fetch activity: ${response.status}`);
    }
    return response.json();
}

export async function loadStatisticsData() {
    const response = await fetch("/api/statistics");
    if (!response.ok) {
        throw new Error(`Failed to fetch statistics: ${response.status}`);
    }
    return response.json();
}

export async function loadTokenStatsData() {
    const response = await fetch("/api/ai-cost");
    if (!response.ok) {
        throw new Error(`Failed to fetch token stats: ${response.status}`);
    }
    return response.json();
}
