---
title: "chat-controller"
draft: false
---

## File `chat-controller`

`Apps/UI/static/js/main/chat-controller.js` — ASLM Chat client script.

---

## Overview

Part of `Apps\UI\static\js\main`. See **Related** for package index and callers.

---

## Public functions

#### `function createChatController(context, dependencies)`

**Purpose:** Client function `createChatController` used by the chat shell.

#### `function buildChatTitle(text, hasAttachments)`

**Purpose:** Client function `buildChatTitle` used by the chat shell.

#### `function startNewChat()`

**Purpose:** Client function `startNewChat` used by the chat shell.

#### `function contextUsageButtons()`

**Purpose:** Client function `contextUsageButtons` used by the chat shell.

#### `function syncContextCompressionButtons()`

**Purpose:** Client function `syncContextCompressionButtons` used by the chat shell.

#### `function formatCompactTokens(value)`

**Purpose:** Client function `formatCompactTokens` used by the chat shell.

#### `function formatDetailedTokens(value)`

**Purpose:** Client function `formatDetailedTokens` used by the chat shell.

#### `function buildContextUsageLabel(percent, used, windowTokens)`

**Purpose:** Client function `buildContextUsageLabel` used by the chat shell.

#### `function buildContextUsageTooltip(percent, used, windowTokens)`

**Purpose:** Client function `buildContextUsageTooltip` used by the chat shell.

#### `function updateContextUsageButtonMetrics($btn, percent, label, tooltip)`

**Purpose:** Client function `updateContextUsageButtonMetrics` used by the chat shell.

#### `function setContextUsageUi(payload)`

**Purpose:** Client function `setContextUsageUi` used by the chat shell.

#### `function setContextCompressionBusy(isBusy)`

**Purpose:** Client function `setContextCompressionBusy` used by the chat shell.

#### `function getContextUsageDraftText(overrideText)`

**Purpose:** Client function `getContextUsageDraftText` used by the chat shell.

#### `function refreshContextUsageNow(options)`

**Purpose:** Client function `refreshContextUsageNow` used by the chat shell.

#### `function startContextUsagePolling()`

**Purpose:** Client function `startContextUsagePolling` used by the chat shell.

#### `function triggerContextCompression(force)`

**Purpose:** Client function `triggerContextCompression` used by the chat shell.

#### `function maybeAutoCompressContextBeforeSend(draftText)`

**Purpose:** Client function `maybeAutoCompressContextBeforeSend` used by the chat shell.

#### `function scheduleContextUsageRefresh()`

**Purpose:** Client function `scheduleContextUsageRefresh` used by the chat shell.

#### `function clonePendingAttachments(attachments)`

**Purpose:** Client function `clonePendingAttachments` used by the chat shell.

#### `function buildAttachmentPayloads(attachments)`

**Purpose:** Client function `buildAttachmentPayloads` used by the chat shell.

#### `function collectUploadedFileIds(attachments)`

**Purpose:** Client function `collectUploadedFileIds` used by the chat shell.

#### `function resolveModelForRequest(request)`

**Purpose:** Client function `resolveModelForRequest` used by the chat shell.

#### `function streamChat(request, $msgRow)`

**Purpose:** Client function `streamChat` used by the chat shell.

#### `function renderStreamFrame(finalRender)`

**Purpose:** Client function `renderStreamFrame` used by the chat shell.

#### `function scheduleStreamRender()`

**Purpose:** Client function `scheduleStreamRender` used by the chat shell.

#### `function readOrAbort()`

**Purpose:** Client function `readOrAbort` used by the chat shell.

#### `function processChatQueue()`

**Purpose:** Client function `processChatQueue` used by the chat shell.

#### `function isReasoningOptionEnabled(value)`

**Purpose:** Client function `isReasoningOptionEnabled` used by the chat shell.

#### `function requestWantsReasoning(options)`

**Purpose:** Client function `requestWantsReasoning` used by the chat shell.

#### `function buildQueuedRequest(text, attachmentsToSend)`

**Purpose:** Client function `buildQueuedRequest` used by the chat shell.

#### `function sendMessage(text, $input)`

**Purpose:** Client function `sendMessage` used by the chat shell.

#### `function abortGeneration()`

**Purpose:** Client function `abortGeneration` used by the chat shell.

#### `function queueRegenerationRequest($userRow, $assistantRow)`

**Purpose:** Client function `queueRegenerationRequest` used by the chat shell.

#### `function regenerateLastResponse()`

**Purpose:** Client function `regenerateLastResponse` used by the chat shell.

#### `function startRegen()`

**Purpose:** Client function `startRegen` used by the chat shell.

#### `function regenerateFromUserMessage($userMsg)`

**Purpose:** Client function `regenerateFromUserMessage` used by the chat shell.

#### `function wireInput($input, $button)`

**Purpose:** Client function `wireInput` used by the chat shell.

#### `function loadChat(chatId, pushState)`

**Purpose:** Client function `loadChat` used by the chat shell.

#### `function renameActiveMenuChat()`

**Purpose:** Client function `renameActiveMenuChat` used by the chat shell.

#### `function deleteActiveMenuChat()`

**Purpose:** Client function `deleteActiveMenuChat` used by the chat shell.

#### `function deleteMessage($message)`

**Purpose:** Client function `deleteMessage` used by the chat shell.

---

## Related

- [main/_index](../../../../../_index/)
