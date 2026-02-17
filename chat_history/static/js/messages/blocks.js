import {
    escapeHtml,
    formatBlockType,
    formatBytes,
    formatDurationSeconds,
    formatTextWithBreaks,
} from "@app/common";

const THINKING_BLOCK_TYPES = new Set(["thinking", "thoughts", "reasoning_recap"]);
const TOOL_BLOCK_TYPES = new Set(["tool_use", "tool_result", "execution_output", "tether_browsing_display"]);
const ATTACHMENT_BLOCK_TYPES = new Set([
    "attachment",
    "file",
    "image_asset_pointer",
    "audio_asset_pointer",
    "real_time_user_audio_video_asset_pointer",
]);
const IMAGE_BLOCK_TYPES = new Set(["image_asset_pointer"]);
const AUDIO_BLOCK_TYPES = new Set(["audio_asset_pointer", "real_time_user_audio_video_asset_pointer"]);
const TRANSCRIPT_BLOCK_TYPES = new Set(["audio_transcription"]);
const SYSTEM_BLOCK_TYPES = new Set(["system_error"]);

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

function normalizeComparableFileName(value) {
    return String(value || "").trim().toLowerCase();
}

function shouldHideFileBlockAsDuplicate(block, attachmentByIndex) {
    if (!block || block.type !== "file") {
        return false;
    }
    const data = block.data && typeof block.data === "object" ? block.data : {};
    const fileIndex = Number(data.file_index);
    if (!Number.isInteger(fileIndex) || fileIndex < 0) {
        return false;
    }
    if (!attachmentByIndex.has(fileIndex)) {
        return false;
    }

    const attachment = attachmentByIndex.get(fileIndex);
    const attachmentData = attachment?.data && typeof attachment.data === "object" ? attachment.data : {};

    const fileName = normalizeComparableFileName(data.file_name || block.text);
    const attachmentName = normalizeComparableFileName(attachmentData.file_name);

    if (!fileName || !attachmentName) {
        return true;
    }
    return fileName === attachmentName;
}

function filterRenderableBlocks(blocks) {
    if (!Array.isArray(blocks) || blocks.length === 0) {
        return [];
    }

    const attachmentByIndex = new Map();
    blocks.forEach((block) => {
        if (!block || block.type !== "attachment") {
            return;
        }
        const data = block.data && typeof block.data === "object" ? block.data : {};
        const attachmentIndex = Number(data.attachment_index);
        if (!Number.isInteger(attachmentIndex) || attachmentIndex < 0) {
            return;
        }
        attachmentByIndex.set(attachmentIndex, block);
    });

    return blocks.filter((block) => !shouldHideFileBlockAsDuplicate(block, attachmentByIndex));
}

function renderCollapsibleBlock(className, label, text, summaryClassName, renderBlockBody, options = {}) {
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

function renderImageAssetBlock(block) {
    const label = formatBlockType(block?.type || "image_asset_pointer");
    const text = String(block?.text || "");
    const data = block?.data && typeof block.data === "object" ? block.data : {};
    const asset = data.asset && typeof data.asset === "object" ? data.asset : {};
    const sourcePointer = String(asset.source_pointer || data.asset_pointer || "").trim();
    const assetUrl = String(asset.asset_url || "").trim();
    const safeAssetUrl = escapeHtml(assetUrl);
    const isResolved = Boolean(asset.is_resolved && assetUrl);

    const width = Number(asset.width);
    const height = Number(asset.height);
    const dimensions = Number.isFinite(width) && Number.isFinite(height)
        ? `${Math.round(width)} × ${Math.round(height)}`
        : "";
    const sizeText = formatBytes(asset.size_bytes);
    const metaParts = [dimensions, sizeText].filter(Boolean);
    const metaHtml = metaParts.length
        ? `<div class="msg-asset-meta">${escapeHtml(metaParts.join(" • "))}</div>`
        : "";

    if (isResolved) {
        const altText = text && text !== "[Image]" ? text : "Image";
        return `
            <div class="msg-block msg-block-asset msg-block-asset-image">
                <div class="msg-block-label">${label}</div>
                <a class="msg-asset-image-link" href="${safeAssetUrl}" target="_blank" rel="noopener noreferrer">
                    <img class="msg-asset-image" src="${safeAssetUrl}" alt="${escapeHtml(altText)}" loading="lazy" />
                </a>
                ${metaHtml}
            </div>
        `;
    }

    const fallbackText = sourcePointer
        ? `Unresolved image: ${sourcePointer}`
        : "Unresolved image attachment";
    return `
        <div class="msg-block msg-block-asset msg-block-asset-image">
            <div class="msg-block-label">${label}</div>
            <div class="msg-block-body">
                <div class="msg-asset-fallback">${escapeHtml(fallbackText)}</div>
            </div>
            ${metaHtml}
        </div>
    `;
}

function renderAudioAssetBlock(block) {
    const label = formatBlockType(block?.type || "audio_asset_pointer");
    const data = block?.data && typeof block.data === "object" ? block.data : {};
    const asset = data.asset && typeof data.asset === "object" ? data.asset : {};
    const sourcePointer = String(asset.source_pointer || data.asset_pointer || "").trim();
    const assetUrl = String(asset.asset_url || "").trim();
    const safeAssetUrl = escapeHtml(assetUrl);
    const isResolved = Boolean(asset.is_resolved && assetUrl);
    const formatHint = String(asset.format || "").trim();
    const durationText = formatDurationSeconds(asset.duration);
    const sizeText = formatBytes(asset.size_bytes);

    const metaParts = [];
    if (formatHint) {
        metaParts.push(formatHint.toUpperCase());
    }
    if (durationText) {
        metaParts.push(durationText);
    }
    if (sizeText) {
        metaParts.push(sizeText);
    }
    const metaHtml = metaParts.length
        ? `<div class="msg-asset-meta">${escapeHtml(metaParts.join(" • "))}</div>`
        : "";

    if (isResolved) {
        return `
            <div class="msg-block msg-block-asset msg-block-asset-audio">
                <div class="msg-block-label">${label}</div>
                <audio class="msg-asset-audio-player" controls preload="none" src="${safeAssetUrl}"></audio>
                ${metaHtml}
            </div>
        `;
    }

    let fallbackText = "Unresolved audio attachment";
    if (sourcePointer) {
        fallbackText = `Unresolved audio: ${sourcePointer}`;
    } else if (block?.type === "real_time_user_audio_video_asset_pointer") {
        fallbackText = "Realtime audio segment (no local asset pointer)";
    }

    return `
        <div class="msg-block msg-block-asset msg-block-asset-audio">
            <div class="msg-block-label">${label}</div>
            <div class="msg-block-body">
                <div class="msg-asset-fallback">${escapeHtml(fallbackText)}</div>
            </div>
            ${metaHtml}
        </div>
    `;
}

function renderTranscriptBlock(block, renderBlockBody) {
    const text = String(block?.text || "");
    const data = block?.data && typeof block.data === "object" ? block.data : {};
    const direction = String(data.direction || "").trim().toLowerCase();
    const directionClass = direction === "out" ? "is-out" : "is-in";
    const badgeHtml = direction
        ? `<span class="msg-transcript-direction ${directionClass}">${escapeHtml(direction)}</span>`
        : "";

    return `
        <div class="msg-block msg-block-transcript">
            <div class="msg-block-label">
                audio transcription
                ${badgeHtml}
            </div>
            <div class="msg-block-body">${renderBlockBody(text)}</div>
        </div>
    `;
}

function renderClaudeAttachmentBlock(block, renderBlockBody) {
    const data = block?.data && typeof block.data === "object" ? block.data : {};
    const text = String(block?.text || "");
    const hasExtracted = Boolean(data.has_extracted_content);
    const fileName = String(data.file_name || "attachment").trim() || "attachment";
    const fileType = String(data.file_type || "unknown").trim() || "unknown";
    const fileSize = formatBytes(data.file_size);

    if (hasExtracted) {
        const subtitleParts = [fileName, fileType.toUpperCase(), fileSize].filter(Boolean);
        const subtitle = subtitleParts.join(" • ");
        return `
            <details class="msg-block msg-block-attachment-text">
                <summary class="msg-block-summary msg-block-attachment-summary">
                    <span class="msg-block-summary-label">Document text</span>
                    <span class="msg-block-summary-preview">${escapeHtml(subtitle)}</span>
                </summary>
                <div class="msg-block-body">${renderBlockBody(text, { markdown: true })}</div>
            </details>
        `;
    }

    const fallbackParts = [fileName, fileType.toUpperCase(), fileSize].filter(Boolean);
    const fallback = fallbackParts.join(" • ");
    return `
        <div class="msg-block msg-block-asset msg-block-file-chip">
            <div class="msg-block-label">attachment</div>
            <div class="msg-block-body">
                <span class="msg-file-chip">${escapeHtml(fallback || text || "[Attachment]")}</span>
            </div>
        </div>
    `;
}

function renderClaudeFileBlock(block) {
    const data = block?.data && typeof block.data === "object" ? block.data : {};
    const fallbackText = String(block?.text || "");
    const fileName = String(data.file_name || "").trim();
    const chipText = fileName || fallbackText || "[File]";

    return `
        <div class="msg-block msg-block-asset msg-block-file-chip">
            <div class="msg-block-label">file</div>
            <div class="msg-block-body">
                <span class="msg-file-chip">${escapeHtml(chipText.replace(/^\[File\]\s*/i, ""))}</span>
            </div>
        </div>
    `;
}

function renderMessageBlock(block, renderBlockBody) {
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
            renderBlockBody,
            { markdown: true }
        );
    }

    if (TOOL_BLOCK_TYPES.has(type)) {
        return renderCollapsibleBlock(
            "msg-block-tool",
            label,
            text,
            "msg-block-tool-summary",
            renderBlockBody,
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

    if (IMAGE_BLOCK_TYPES.has(type)) {
        return renderImageAssetBlock(block);
    }

    if (AUDIO_BLOCK_TYPES.has(type)) {
        return renderAudioAssetBlock(block);
    }

    if (TRANSCRIPT_BLOCK_TYPES.has(type)) {
        return renderTranscriptBlock(block, renderBlockBody);
    }

    if (type === "attachment") {
        return renderClaudeAttachmentBlock(block, renderBlockBody);
    }

    if (type === "file") {
        return renderClaudeFileBlock(block);
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

export function createMessageBlocksRenderer({ renderBlockBody }) {
    return function renderMessageBlocks(blocks) {
        const filteredBlocks = filterRenderableBlocks(blocks);
        if (!filteredBlocks || filteredBlocks.length === 0) {
            return `<div class="msg-block msg-block-empty">[No renderable blocks]</div>`;
        }
        return filteredBlocks.map((block) => renderMessageBlock(block, renderBlockBody)).join("");
    };
}
