---
title: "messages-ui"
draft: false
---

## File `messages-ui`

`Apps/UI/static/js/ui/messages-ui.js` — ASLM Chat client script.

---

## Overview

Part of `Apps\UI\static\js\ui`. See **Related** for package index and callers.

---

## Public functions

#### `function createMessagesUi(context, dependencies)`

**Purpose:** Client function `createMessagesUi` used by the chat shell.

#### `function updateSendButtons()`

**Purpose:** Client function `updateSendButtons` used by the chat shell.

#### `function syncComposerButton($button, $input)`

**Purpose:** Client function `syncComposerButton` used by the chat shell.

#### `function updateRegenButtons()`

**Purpose:** Client function `updateRegenButtons` used by the chat shell.

#### `function scrollBottom()`

**Purpose:** Client function `scrollBottom` used by the chat shell.

#### `function isEscapedAt(text, index)`

**Purpose:** Client function `isEscapedAt` used by the chat shell.

#### `function findUnescaped(text, needle, fromIndex)`

**Purpose:** Client function `findUnescaped` used by the chat shell.

#### `function nextLatexDelimiter(text, fromIndex)`

**Purpose:** Client function `nextLatexDelimiter` used by the chat shell.

#### `function renderLatexSourceToHtml(latexSource, displayMode)`

**Purpose:** Client function `renderLatexSourceToHtml` used by the chat shell.

#### `function appendLatexHtml(fragment, latexSource, displayMode)`

**Purpose:** Client function `appendLatexHtml` used by the chat shell.

#### `function replaceLatexInTextNode(textNode)`

**Purpose:** Client function `replaceLatexInTextNode` used by the chat shell.

#### `function renderLatexInHtml(html)`

**Purpose:** Client function `renderLatexInHtml` used by the chat shell.

#### `function looksLikeLatexSource(source)`

**Purpose:** Client function `looksLikeLatexSource` used by the chat shell.

#### `function normalizeLooseDisplayLatex(source)`

**Purpose:** Client function `normalizeLooseDisplayLatex` used by the chat shell.

#### `function extractLatexBlocks(source)`

**Purpose:** Client function `extractLatexBlocks` used by the chat shell.

#### `function restoreLatexPlaceholders(html, blocks)`

**Purpose:** Client function `restoreLatexPlaceholders` used by the chat shell.

#### `function markdownRawCodeLanguage(codeEl)`

**Purpose:** Client function `markdownRawCodeLanguage` used by the chat shell.

#### `function markdownCodeLanguage(codeEl)`

**Purpose:** Client function `markdownCodeLanguage` used by the chat shell.

#### `function markdownCodeHighlightLanguage(codeEl)`

**Purpose:** Client function `markdownCodeHighlightLanguage` used by the chat shell.

#### `function isMermaidCodeLanguage(codeEl)`

**Purpose:** Client function `isMermaidCodeLanguage` used by the chat shell.

#### `function safeMarkdownUrl(value)`

**Purpose:** Client function `safeMarkdownUrl` used by the chat shell.

#### `function linkifyInlineCodeUrls(template)`

**Purpose:** Client function `linkifyInlineCodeUrls` used by the chat shell.

#### `function enhanceMarkdownCodeBlocks(html)`

**Purpose:** Client function `enhanceMarkdownCodeBlocks` used by the chat shell.

#### `function renderMarkdownSegment(content, citationSources)`

**Purpose:** Client function `renderMarkdownSegment` used by the chat shell.

#### `function renderPlainTextSegment(content)`

**Purpose:** Client function `renderPlainTextSegment` used by the chat shell.

#### `function normalizeHighlightLanguage(language)`

**Purpose:** Client function `normalizeHighlightLanguage` used by the chat shell.

#### `function languageFromPath(path, fallback)`

**Purpose:** Client function `languageFromPath` used by the chat shell.

#### `function highlightCode(code, language)`

**Purpose:** Client function `highlightCode` used by the chat shell.

#### `function safeExternalUrl(value)`

**Purpose:** Client function `safeExternalUrl` used by the chat shell.

#### `function faviconDomain(source)`

**Purpose:** Client function `faviconDomain` used by the chat shell.

#### `function localFaviconUrlForDomain(domain)`

**Purpose:** Client function `localFaviconUrlForDomain` used by the chat shell.

#### `function sourceHasExtractedPreview(source)`

**Purpose:** Client function `sourceHasExtractedPreview` used by the chat shell.

#### `function sourceFaviconUrl(source)`

**Purpose:** Client function `sourceFaviconUrl` used by the chat shell.

#### `function domainAccentStyle(value, extraStyle)`

**Purpose:** Client function `domainAccentStyle` used by the chat shell.

#### `function findOpenActivityMarker(rawText, markerPairs)`

**Purpose:** Client function `findOpenActivityMarker` used by the chat shell.

#### `function openToolPayloadInfo(rawText)`

**Purpose:** Client function `openToolPayloadInfo` used by the chat shell.

#### `function hasOpenToolPayload(rawText)`

**Purpose:** Client function `hasOpenToolPayload` used by the chat shell.

#### `function stripOpenToolPayload(rawText)`

**Purpose:** Client function `stripOpenToolPayload` used by the chat shell.

#### `function trailingPartialActivityMarkerInfo(rawText)`

**Purpose:** Client function `trailingPartialActivityMarkerInfo` used by the chat shell.

#### `function stripTrailingPartialActivityMarker(rawText)`

**Purpose:** Client function `stripTrailingPartialActivityMarker` used by the chat shell.

#### `function sharedFilePayloadFromTrailingShorthand(value)`

**Purpose:** Client function `sharedFilePayloadFromTrailingShorthand` used by the chat shell.

#### `function sharedFileSegmentFromTrailingShorthand(sharedFile)`

**Purpose:** Client function `sharedFileSegmentFromTrailingShorthand` used by the chat shell.

#### `function normalizeTrailingSharedFileShorthandSegments(rawSegments)`

**Purpose:** Client function `normalizeTrailingSharedFileShorthandSegments` used by the chat shell.

#### `function parseMessageTimeline(rawText)`

**Purpose:** Client function `parseMessageTimeline` used by the chat shell.

#### `function sanitizeVisibleText(value)`

**Purpose:** Client function `sanitizeVisibleText` used by the chat shell.

#### `function pushTextSegment(value)`

**Purpose:** Client function `pushTextSegment` used by the chat shell.

#### `function findNextReasoningStart(fromIndex)`

**Purpose:** Client function `findNextReasoningStart` used by the chat shell.

#### `function getExpandedThoughtIndices($msgRow)`

**Purpose:** Client function `getExpandedThoughtIndices` used by the chat shell.

#### `function setExpandedThoughtIndices($msgRow, expandedIndices)`

**Purpose:** Client function `setExpandedThoughtIndices` used by the chat shell.

#### `function getExpandedSearchIndices($msgRow)`

**Purpose:** Client function `getExpandedSearchIndices` used by the chat shell.

#### `function setExpandedSearchIndices($msgRow, expandedIndices)`

**Purpose:** Client function `setExpandedSearchIndices` used by the chat shell.

#### `function getExpandedSearchKeys($msgRow)`

**Purpose:** Client function `getExpandedSearchKeys` used by the chat shell.

#### `function setExpandedSearchKeys($msgRow, expandedKeys)`

**Purpose:** Client function `setExpandedSearchKeys` used by the chat shell.

#### `function getExpandedWriteIndices($msgRow)`

**Purpose:** Client function `getExpandedWriteIndices` used by the chat shell.

#### `function setExpandedWriteIndices($msgRow, expandedIndices)`

**Purpose:** Client function `setExpandedWriteIndices` used by the chat shell.

#### `function getExpandedEditIndices($msgRow)`

**Purpose:** Client function `getExpandedEditIndices` used by the chat shell.

#### `function setExpandedEditIndices($msgRow, expandedIndices)`

**Purpose:** Client function `setExpandedEditIndices` used by the chat shell.

#### `function isSearchToolSegment(segment)`

**Purpose:** Client function `isSearchToolSegment` used by the chat shell.

#### `function searchQueryFromSegment(segment)`

**Purpose:** Client function `searchQueryFromSegment` used by the chat shell.

#### `function appendUniqueSearchPart(parts, value)`

**Purpose:** Client function `appendUniqueSearchPart` used by the chat shell.

#### `function appendSearchList(parts, value)`

**Purpose:** Client function `appendSearchList` used by the chat shell.

#### `function formatSearchQueryValue(value)`

**Purpose:** Client function `formatSearchQueryValue` used by the chat shell.

#### `function searchSegmentKey(segment, fallbackIndex)`

**Purpose:** Client function `searchSegmentKey` used by the chat shell.

#### `function isReadPageToolSegment(segment)`

**Purpose:** Client function `isReadPageToolSegment` used by the chat shell.

#### `function isWriteToolSegment(segment)`

**Purpose:** Client function `isWriteToolSegment` used by the chat shell.

#### `function isEditToolSegment(segment)`

**Purpose:** Client function `isEditToolSegment` used by the chat shell.

#### `function sourceFromUrl(value, rank)`

**Purpose:** Client function `sourceFromUrl` used by the chat shell.

#### `function normalizeSearchSourceItem(item, rank)`

**Purpose:** Client function `normalizeSearchSourceItem` used by the chat shell.

#### `function collectSourceCandidates(container)`

**Purpose:** Client function `collectSourceCandidates` used by the chat shell.

#### `function searchSourcesFromSegment(segment)`

**Purpose:** Client function `searchSourcesFromSegment` used by the chat shell.

#### `function readPageSourcesFromSegment(segment)`

**Purpose:** Client function `readPageSourcesFromSegment` used by the chat shell.

#### `function addSearchSourcesToCitationRegistry(registry, segment)`

**Purpose:** Client function `addSearchSourcesToCitationRegistry` used by the chat shell.

#### `function addAllSearchSourcesToCitationRegistry(registry, segments)`

**Purpose:** Client function `addAllSearchSourcesToCitationRegistry` used by the chat shell.

#### `function renderSourceChip(chip)`

**Purpose:** Client function `renderSourceChip` used by the chat shell.

#### `function dedupeSearchSources(sources)`

**Purpose:** Client function `dedupeSearchSources` used by the chat shell.

#### `function renderSearchSourcesWithOverflow(sources, maxVisible)`

**Purpose:** Client function `renderSearchSourcesWithOverflow` used by the chat shell.

#### `function renderSearchToolCard(segment, toolSegmentIndex, options)`

**Purpose:** Client function `renderSearchToolCard` used by the chat shell.

#### `function renderSearchToolGroup(searchItems, options)`

**Purpose:** Client function `renderSearchToolGroup` used by the chat shell.

#### `function renderReadPageToolCard(readItems)`

**Purpose:** Client function `renderReadPageToolCard` used by the chat shell.

#### `function writePathFromSegment(segment)`

**Purpose:** Client function `writePathFromSegment` used by the chat shell.

#### `function writeContentFromSegment(segment)`

**Purpose:** Client function `writeContentFromSegment` used by the chat shell.

#### `function renderWritePreviewLines(content, isExpanded, path)`

**Purpose:** Client function `renderWritePreviewLines` used by the chat shell.

#### `function renderWriteToolCard(segment, toolSegmentIndex, options)`

**Purpose:** Client function `renderWriteToolCard` used by the chat shell.

#### `function parseToolResultObject(segment)`

**Purpose:** Client function `parseToolResultObject` used by the chat shell.

#### `function formatByteSize(bytes)`

**Purpose:** Client function `formatByteSize` used by the chat shell.

#### `function normalizeSharedFilePayload(candidate)`

**Purpose:** Client function `normalizeSharedFilePayload` used by the chat shell.

#### `function asScalarText(value)`

**Purpose:** Client function `asScalarText` used by the chat shell.

#### `function sharedFileFromSegment(segment)`

**Purpose:** Client function `sharedFileFromSegment` used by the chat shell.

#### `function isSharedFileToolSegment(segment)`

**Purpose:** Client function `isSharedFileToolSegment` used by the chat shell.

#### `function isCompressionContextSegment(segment)`

**Purpose:** Client function `isCompressionContextSegment` used by the chat shell.

#### `function compressionContextText(segment)`

**Purpose:** Client function `compressionContextText` used by the chat shell.

#### `function renderCompressionContextCard(segment, toolSegmentIndex)`

**Purpose:** Client function `renderCompressionContextCard` used by the chat shell.

#### `function buildCompressionPendingRow()`

**Purpose:** Client function `buildCompressionPendingRow` used by the chat shell.

#### `function appendCompressionPending()`

**Purpose:** Client function `appendCompressionPending` used by the chat shell.

#### `function removeCompressionPending($row)`

**Purpose:** Client function `removeCompressionPending` used by the chat shell.

#### `function isCompressionOnlyActivitySegments(segments)`

**Purpose:** Client function `isCompressionOnlyActivitySegments` used by the chat shell.

#### `function sharedFileDownloadUrl(file, options)`

**Purpose:** Client function `sharedFileDownloadUrl` used by the chat shell.

#### `function sharedFileImageRender(file)`

**Purpose:** Client function `sharedFileImageRender` used by the chat shell.

#### `function normalizeAttachmentCardFile(file, options)`

**Purpose:** Client function `normalizeAttachmentCardFile` used by the chat shell.

#### `function attachmentFilename(file)`

**Purpose:** Client function `attachmentFilename` used by the chat shell.

#### `function attachmentMimeType(file)`

**Purpose:** Client function `attachmentMimeType` used by the chat shell.

#### `function attachmentTypeLabel(file)`

**Purpose:** Client function `attachmentTypeLabel` used by the chat shell.

#### `function attachmentSizeBytes(file)`

**Purpose:** Client function `attachmentSizeBytes` used by the chat shell.

#### `function attachmentSourceUrl(file, options)`

**Purpose:** Client function `attachmentSourceUrl` used by the chat shell.

#### `function attachmentDownloadUrl(file, options)`

**Purpose:** Client function `attachmentDownloadUrl` used by the chat shell.

#### `function attachmentDisplayKind(file)`

**Purpose:** Client function `attachmentDisplayKind` used by the chat shell.

#### `function isAudioAttachment(file)`

**Purpose:** Client function `isAudioAttachment` used by the chat shell.

#### `function isVideoAttachment(file)`

**Purpose:** Client function `isVideoAttachment` used by the chat shell.

#### `function isImageAttachment(file)`

**Purpose:** Client function `isImageAttachment` used by the chat shell.

#### `function mediaMetaText(file)`

**Purpose:** Client function `mediaMetaText` used by the chat shell.

#### `function renderAttachmentDownloadButton(file, options, className)`

**Purpose:** Client function `renderAttachmentDownloadButton` used by the chat shell.

#### `function renderImageAttachmentCard(file, options)`

**Purpose:** Client function `renderImageAttachmentCard` used by the chat shell.

#### `function renderGenericAttachmentCard(file, options)`

**Purpose:** Client function `renderGenericAttachmentCard` used by the chat shell.

#### `function inferredAttachmentDisplayKind(file)`

**Purpose:** Client function `inferredAttachmentDisplayKind` used by the chat shell.

#### `function renderUserUploadAttachmentChip(file)`

**Purpose:** Client function `renderUserUploadAttachmentChip` used by the chat shell.

#### `function renderAudioAttachmentCard(file, options)`

**Purpose:** Client function `renderAudioAttachmentCard` used by the chat shell.

#### `function renderVideoAttachmentCard(file, options)`

**Purpose:** Client function `renderVideoAttachmentCard` used by the chat shell.

#### `function renderAttachmentCard(file, options)`

**Purpose:** Client function `renderAttachmentCard` used by the chat shell.

#### `function renderMessageAttachments(attachments, options)`

**Purpose:** Client function `renderMessageAttachments` used by the chat shell.

#### `function formatMediaTime(seconds)`

**Purpose:** Client function `formatMediaTime` used by the chat shell.

#### `function mediaElementFromCard(card)`

**Purpose:** Client function `mediaElementFromCard` used by the chat shell.

#### `function bufferedProgressPercent(media, duration, progressPercent)`

**Purpose:** Client function `bufferedProgressPercent` used by the chat shell.

#### `function stopMediaFrameSync(card)`

**Purpose:** Client function `stopMediaFrameSync` used by the chat shell.

#### `function startMediaFrameSync(card)`

**Purpose:** Client function `startMediaFrameSync` used by the chat shell.

#### `function syncFrame()`

**Purpose:** Client function `syncFrame` used by the chat shell.

#### `function syncMediaCard(card)`

**Purpose:** Client function `syncMediaCard` used by the chat shell.

#### `function previewMediaSeek(card, value)`

**Purpose:** Client function `previewMediaSeek` used by the chat shell.

#### `function forcePauseMedia(card, media)`

**Purpose:** Client function `forcePauseMedia` used by the chat shell.

#### `function forcePlayMedia(card, media)`

**Purpose:** Client function `forcePlayMedia` used by the chat shell.

#### `function toggleMediaCard(card)`

**Purpose:** Client function `toggleMediaCard` used by the chat shell.

#### `function commitMediaSeek(range)`

**Purpose:** Client function `commitMediaSeek` used by the chat shell.

#### `function syncFullscreenControls(card)`

**Purpose:** Client function `syncFullscreenControls` used by the chat shell.

#### `function ensureFloatingMediaRoot()`

**Purpose:** Client function `ensureFloatingMediaRoot` used by the chat shell.

#### `function openFloatingVideoCard(card)`

**Purpose:** Client function `openFloatingVideoCard` used by the chat shell.

#### `function dockFloatingVideoCard(card)`

**Purpose:** Client function `dockFloatingVideoCard` used by the chat shell.

#### `function closeFloatingVideoCard(card)`

**Purpose:** Client function `closeFloatingVideoCard` used by the chat shell.

#### `function bindAttachmentMediaEvents()`

**Purpose:** Client function `bindAttachmentMediaEvents` used by the chat shell.

#### `function renderSharedImageFileCard(file)`

**Purpose:** Client function `renderSharedImageFileCard` used by the chat shell.

#### `function renderSharedFileCard(segment)`

**Purpose:** Client function `renderSharedFileCard` used by the chat shell.

#### `function collectPinnedSharedFileCards(segments)`

**Purpose:** Client function `collectPinnedSharedFileCards` used by the chat shell.

#### `function isImageViewToolSegment(segment)`

**Purpose:** Client function `isImageViewToolSegment` used by the chat shell.

#### `function imageResultFromSegment(segment)`

**Purpose:** Client function `imageResultFromSegment` used by the chat shell.

#### `function sandboxImageDataUrl(imageResult)`

**Purpose:** Client function `sandboxImageDataUrl` used by the chat shell.

#### `function editModeFromSegment(segment)`

**Purpose:** Client function `editModeFromSegment` used by the chat shell.

#### `function editPathFromSegment(segment, result)`

**Purpose:** Client function `editPathFromSegment` used by the chat shell.

#### `function parseUnifiedDiffRows(diffText)`

**Purpose:** Client function `parseUnifiedDiffRows` used by the chat shell.

#### `function fallbackEditRows(segment)`

**Purpose:** Client function `fallbackEditRows` used by the chat shell.

#### `function editRowsFromSegment(segment, result)`

**Purpose:** Client function `editRowsFromSegment` used by the chat shell.

#### `function renderEditRows(rows, isExpanded, language)`

**Purpose:** Client function `renderEditRows` used by the chat shell.

#### `function renderEditToolCard(segment, toolSegmentIndex, options)`

**Purpose:** Client function `renderEditToolCard` used by the chat shell.

#### `function truncateInlineText(value, maxLength)`

**Purpose:** Client function `truncateInlineText` used by the chat shell.

#### `function compactToolValue(value)`

**Purpose:** Client function `compactToolValue` used by the chat shell.

#### `function utf8ByteLength(value)`

**Purpose:** Client function `utf8ByteLength` used by the chat shell.

#### `function textLineCount(value)`

**Purpose:** Client function `textLineCount` used by the chat shell.

#### `function truncateTextPreview(value, maxChars)`

**Purpose:** Client function `truncateTextPreview` used by the chat shell.

#### `function heavyToolKeysForSegment(segment)`

**Purpose:** Client function `heavyToolKeysForSegment` used by the chat shell.

#### `function toolIdentityText(segment)`

**Purpose:** Client function `toolIdentityText` used by the chat shell.

#### `function toolServerId(segment)`

**Purpose:** Client function `toolServerId` used by the chat shell.

#### `function isMcpSandboxToolSegment(segment)`

**Purpose:** Client function `isMcpSandboxToolSegment` used by the chat shell.

#### `function isSandboxPythonToolSegment(segment)`

**Purpose:** Client function `isSandboxPythonToolSegment` used by the chat shell.

#### `function isSandboxShareFileToolSegment(segment)`

**Purpose:** Client function `isSandboxShareFileToolSegment` used by the chat shell.

#### `function isSandboxToolSegment(segment)`

**Purpose:** Client function `isSandboxToolSegment` used by the chat shell.

#### `function parseSandboxResult(segment)`

**Purpose:** Client function `parseSandboxResult` used by the chat shell.

#### `function sandboxInputText(segment)`

**Purpose:** Client function `sandboxInputText` used by the chat shell.

#### `function sandboxInputPreviewText(segment)`

**Purpose:** Client function `sandboxInputPreviewText` used by the chat shell.

#### `function sandboxLanguage(segment)`

**Purpose:** Client function `sandboxLanguage` used by the chat shell.

#### `function renderSandboxStreamBlock(label, content, streamClass, language)`

**Purpose:** Client function `renderSandboxStreamBlock` used by the chat shell.

#### `function sandboxStatusClass(segment, result)`

**Purpose:** Client function `sandboxStatusClass` used by the chat shell.

#### `function renderSandboxImageToolBlock(segment, toolSegmentIndex)`

**Purpose:** Client function `renderSandboxImageToolBlock` used by the chat shell.

#### `function renderSandboxToolBlock(segment, toolSegmentIndex)`

**Purpose:** Client function `renderSandboxToolBlock` used by the chat shell.

#### `function rememberLoadedSandboxImages($root)`

**Purpose:** Client function `rememberLoadedSandboxImages` used by the chat shell.

#### `function syncSandboxImageFramesForSrc(src)`

**Purpose:** Client function `syncSandboxImageFramesForSrc` used by the chat shell.

#### `function ensureSandboxImagePreload(src)`

**Purpose:** Client function `ensureSandboxImagePreload` used by the chat shell.

#### `function markSandboxImageLoaded(imageEl)`

**Purpose:** Client function `markSandboxImageLoaded` used by the chat shell.

#### `function markSandboxImageError(imageEl)`

**Purpose:** Client function `markSandboxImageError` used by the chat shell.

#### `function hydrateSandboxImages($root)`

**Purpose:** Client function `hydrateSandboxImages` used by the chat shell.

#### `function hydrateSharedImageCards($root)`

**Purpose:** Client function `hydrateSharedImageCards` used by the chat shell.

#### `function sanitizeMermaidSvg(svg)`

**Purpose:** Client function `sanitizeMermaidSvg` used by the chat shell.

#### `function readRootCssVar(name, fallback)`

**Purpose:** Client function `readRootCssVar` used by the chat shell.

#### `function buildMermaidThemeVariables()`

**Purpose:** Client function `buildMermaidThemeVariables` used by the chat shell.

#### `function parseCssColorToRgb(value)`

**Purpose:** Client function `parseCssColorToRgb` used by the chat shell.

#### `function relativeLuminance(rgb)`

**Purpose:** Client function `relativeLuminance` used by the chat shell.

#### `function contrastRatio(firstRgb, secondRgb)`

**Purpose:** Client function `contrastRatio` used by the chat shell.

#### `function getSvgShapeFill(shapeEl)`

**Purpose:** Client function `getSvgShapeFill` used by the chat shell.

#### `function applyMermaidLabelContrast(svgRoot)`

**Purpose:** Client function `applyMermaidLabelContrast` used by the chat shell.

#### `function renderMermaidLatexLabels(svgRoot)`

**Purpose:** Client function `renderMermaidLatexLabels` used by the chat shell.

#### `function enhanceMermaidSvg(canvasEl)`

**Purpose:** Client function `enhanceMermaidSvg` used by the chat shell.

#### `function getMermaidRenderer()`

**Purpose:** Client function `getMermaidRenderer` used by the chat shell.

#### `function configureMermaid()`

**Purpose:** Client function `configureMermaid` used by the chat shell.

#### `function hydrateMermaidDiagrams($root)`

**Purpose:** Client function `hydrateMermaidDiagrams` used by the chat shell.

#### `function toolDisplayName(segment)`

**Purpose:** Client function `toolDisplayName` used by the chat shell.

#### `function toolStatusText(segment)`

**Purpose:** Client function `toolStatusText` used by the chat shell.

#### `function toolStatusClass(segment)`

**Purpose:** Client function `toolStatusClass` used by the chat shell.

#### `function reasoningToolDetail(segment)`

**Purpose:** Client function `reasoningToolDetail` used by the chat shell.

#### `function toolIconHtml(segment)`

**Purpose:** Client function `toolIconHtml` used by the chat shell.

#### `function renderReasoningToolRow(segment, toolSegmentIndex)`

**Purpose:** Client function `renderReasoningToolRow` used by the chat shell.

#### `function renderReasoningToolItem(item)`

**Purpose:** Client function `renderReasoningToolItem` used by the chat shell.

#### `function reasoningToolStepTitle(segment)`

**Purpose:** Client function `reasoningToolStepTitle` used by the chat shell.

#### `function reasoningToggleLabel()`

**Purpose:** Client function `reasoningToggleLabel` used by the chat shell.

#### `function hasThoughtSegments(segments)`

**Purpose:** Client function `hasThoughtSegments` used by the chat shell.

#### `function hasReasoningMarker(rawText)`

**Purpose:** Client function `hasReasoningMarker` used by the chat shell.

#### `function shouldUseReasoningShell($msgRow, segments, rawText, renderOptions)`

**Purpose:** Client function `shouldUseReasoningShell` used by the chat shell.

#### `function hasClosedReasoning(rawText)`

**Purpose:** Client function `hasClosedReasoning` used by the chat shell.

#### `function splitLongReasoningSentence(sentence, targetLength)`

**Purpose:** Client function `splitLongReasoningSentence` used by the chat shell.

#### `function splitReasoningText(content)`

**Purpose:** Client function `splitReasoningText` used by the chat shell.

#### `function renderReasoningThoughtText(content)`

**Purpose:** Client function `renderReasoningThoughtText` used by the chat shell.

#### `function renderPendingToolCallPlaceholder()`

**Purpose:** Client function `renderPendingToolCallPlaceholder` used by the chat shell.

#### `function renderReasoningGroup(items, thoughtIndex, isExpanded, toggleLabel, options)`

**Purpose:** Client function `renderReasoningGroup` used by the chat shell.

#### `function renderThoughtBlock(content, thoughtIndex, isExpanded)`

**Purpose:** Client function `renderThoughtBlock` used by the chat shell.

#### `function createActivityBlock(key, innerHtml)`

**Purpose:** Client function `createActivityBlock` used by the chat shell.

#### `function getElementMorphKey(el)`

**Purpose:** Client function `getElementMorphKey` used by the chat shell.

#### `function syncElementAttrs(fromEl, toEl)`

**Purpose:** Client function `syncElementAttrs` used by the chat shell.

#### `function morphDomNode(fromEl, toEl)`

**Purpose:** Client function `morphDomNode` used by the chat shell.

#### `function morphDomChildren(fromParent, toParent)`

**Purpose:** Client function `morphDomChildren` used by the chat shell.

#### `function applyActivityBlocks($stream, blocks)`

**Purpose:** Client function `applyActivityBlocks` used by the chat shell.

#### `function renderActivityTimeline($msgRow, segments, options)`

**Purpose:** Client function `renderActivityTimeline` used by the chat shell.

#### `function pushBlock(key, html)`

**Purpose:** Client function `pushBlock` used by the chat shell.

#### `function pushTextSegmentBlock(segment, segmentIndex)`

**Purpose:** Client function `pushTextSegmentBlock` used by the chat shell.

#### `function renderActiveReasoningBlock()`

**Purpose:** Client function `renderActiveReasoningBlock` used by the chat shell.

#### `function searchSegmentCount(segments)`

**Purpose:** Client function `searchSegmentCount` used by the chat shell.

#### `function clearSearchBatchHold($msgRow)`

**Purpose:** Client function `clearSearchBatchHold` used by the chat shell.

#### `function clearPreToolTextHold($msgRow)`

**Purpose:** Client function `clearPreToolTextHold` used by the chat shell.

#### `function shouldHoldPreToolText($msgRow, parsed, rawText)`

**Purpose:** Client function `shouldHoldPreToolText` used by the chat shell.

#### `function shouldHoldStreamingSearchBatch($msgRow, parsed, rawText)`

**Purpose:** Client function `shouldHoldStreamingSearchBatch` used by the chat shell.

#### `function renderMessageHtml($msgRow, rawText)`

**Purpose:** Client function `renderMessageHtml` used by the chat shell.

#### `function renderMessageStream($msgRow, rawText)`

**Purpose:** Client function `renderMessageStream` used by the chat shell.

#### `function sourceMessageRowForActivityCard($card)`

**Purpose:** Client function `sourceMessageRowForActivityCard` used by the chat shell.

#### `function openToolInspectorFromCard($card)`

**Purpose:** Client function `openToolInspectorFromCard` used by the chat shell.

#### `function toggleSearchSources($button)`

**Purpose:** Client function `toggleSearchSources` used by the chat shell.

#### `function toggleWriteCard($card)`

**Purpose:** Client function `toggleWriteCard` used by the chat shell.

#### `function toggleEditCard($card)`

**Purpose:** Client function `toggleEditCard` used by the chat shell.

#### `function toggleCompressionContext($button)`

**Purpose:** Client function `toggleCompressionContext` used by the chat shell.

#### `function startWritePreviewPan(event, $preview)`

**Purpose:** Client function `startWritePreviewPan` used by the chat shell.

#### `function scrollFrame()`

**Purpose:** Client function `scrollFrame` used by the chat shell.

#### `function onMouseMove(moveEvent)`

**Purpose:** Client function `onMouseMove` used by the chat shell.

#### `function stopPan()`

**Purpose:** Client function `stopPan` used by the chat shell.

#### `function onMouseUp(upEvent)`

**Purpose:** Client function `onMouseUp` used by the chat shell.

#### `function buildMessageRow(role, text, attachments, timestamp, options)`

**Purpose:** Client function `buildMessageRow` used by the chat shell.

#### `function appendMessage(role, text, attachments, timestamp, options)`

**Purpose:** Client function `appendMessage` used by the chat shell.

#### `function appendMessages(messages, options)`

**Purpose:** Client function `appendMessages` used by the chat shell.

#### `function setQueuedMessageState($row, queued)`

**Purpose:** Client function `setQueuedMessageState` used by the chat shell.

#### `function appendTyping(timestamp)`

**Purpose:** Client function `appendTyping` used by the chat shell.

#### `function fallbackCopy(text, onSuccess)`

**Purpose:** Client function `fallbackCopy` used by the chat shell.

#### `function copyMessage($button)`

**Purpose:** Client function `copyMessage` used by the chat shell.

#### `function onCopied()`

**Purpose:** Client function `onCopied` used by the chat shell.

#### `function copyCodeBlock($button)`

**Purpose:** Client function `copyCodeBlock` used by the chat shell.

#### `function reasoningDrawerMaxWidth()`

**Purpose:** Client function `reasoningDrawerMaxWidth` used by the chat shell.

#### `function setReasoningDrawerWidth(width)`

**Purpose:** Client function `setReasoningDrawerWidth` used by the chat shell.

#### `function resetReasoningDrawerWidth()`

**Purpose:** Client function `resetReasoningDrawerWidth` used by the chat shell.

#### `function syncReasoningDrawerFromWrapper($wrapper)`

**Purpose:** Client function `syncReasoningDrawerFromWrapper` used by the chat shell.

#### `function openReasoningDrawer($wrapper)`

**Purpose:** Client function `openReasoningDrawer` used by the chat shell.

#### `function closeReasoningDrawer()`

**Purpose:** Client function `closeReasoningDrawer` used by the chat shell.

#### `function bindReasoningDrawerResize()`

**Purpose:** Client function `bindReasoningDrawerResize` used by the chat shell.

#### `function widthFromPointer(pointerEvent)`

**Purpose:** Client function `widthFromPointer` used by the chat shell.

#### `function onMove(moveEvent)`

**Purpose:** Client function `onMove` used by the chat shell.

#### `function onEnd()`

**Purpose:** Client function `onEnd` used by the chat shell.

#### `function toggleThoughtSection($toggle)`

**Purpose:** Client function `toggleThoughtSection` used by the chat shell.

#### `function configureMarkdown()`

**Purpose:** Client function `configureMarkdown` used by the chat shell.

---

## Related

- [ui/_index](../../../../../_index/)
