export function toConversationKey(provider, id) {
    return `${provider}::${id}`;
}

export function escapeSelector(value) {
    return String(value || "").replace(/[^a-zA-Z0-9_-]/g, "_");
}

export function escapeHtml(value) {
    return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

export function formatBlockType(type) {
    return String(type || "unknown").replace(/_/g, " ");
}

export function formatTextWithBreaks(value) {
    return escapeHtml(value).replace(/\n/g, "<br/>");
}

export function formatBytes(value) {
    const size = Number(value);
    if (!Number.isFinite(size) || size < 0) {
        return "";
    }
    if (size < 1024) {
        return `${size} B`;
    }
    if (size < 1024 * 1024) {
        return `${(size / 1024).toFixed(1)} KB`;
    }
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDurationSeconds(value) {
    const seconds = Number(value);
    if (!Number.isFinite(seconds) || seconds < 0) {
        return "";
    }
    if (seconds < 60) {
        return `${seconds.toFixed(1)}s`;
    }
    const totalSeconds = Math.round(seconds);
    const minutes = Math.floor(totalSeconds / 60);
    const remainingSeconds = totalSeconds % 60;
    return `${minutes}:${String(remainingSeconds).padStart(2, "0")}`;
}
