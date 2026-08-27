// Copyright NEXTGGTECH. Elastic License 2.0.

import { deleteJson, getCsrfToken, getJson, patchJson, postJson } from './api.js';
import { intlLocaleTag, t } from './i18n.js';
import { confirmDialog, largeTextDialog, textDialog } from '../ui/dialogs.js';

// Chat controller.
// Create the chat workflow controller for sending, loading, and mutating chats.
export function createChatController(context, dependencies) {
  const {
    attachmentUi,
    engineManager,
    historyUi,
    messagesUi,
    parametersUi,
    skillsUi
  } = dependencies;
  const { dom, state } = context;
  const contextUsagePollIntervalMs = 2000;
  let contextUsageTimer = null;
  let contextUsagePollTimer = null;
  let contextUsageRefreshPromise = null;
  let contextAutoCompressionAt = 0;
  let contextCompressionInFlight = false;
  let activeGenerationId = '';
  let hideCompressedIndicator = false;
  let clearCompressedIndicatorAfterNextAssistant = false;
  let sendCooldownUntil = 0;
  const sendCooldownMs = 1500;
  const slashPalette = {
    $input: null,
    $panel: null,
    entries: [],
    activeIndex: 0,
    query: '',
    tokenStart: -1,
    tokenEnd: -1
  };

  // Chat lifecycle helpers.
  // Build a short title from the first user prompt.
  function buildChatTitle(text, hasAttachments) {
    if (text) {
      return text.substring(0, 40) + (text.length > 40 ? '...' : '');
    }

    return hasAttachments ? t('chat.attachmentChat', {}, 'Attachment chat') : t('chat.newChat', {}, 'New Chat');
  }

  // Reset the page into a fresh chat state.
  function startNewChat(pushState) {
    dom.$chatTitle.text(t('chat.newChat', {}, 'New Chat'));
    document.title = t('meta.appTitle', {}, 'ASLM Chat');
    dom.$messagesInner.find('.msg').remove();
    dom.$conversationInput.hide();
    dom.$welcomeScreen.show();
    dom.$chatInput.val('').css('height', 'auto').focus();
    dom.$chatInputConv.val('').css('height', 'auto');
    state.currentChatId = null;
    hideCompressedIndicator = false;
    clearCompressedIndicatorAfterNextAssistant = false;
    historyUi.clearActiveChat();
    dom.$messagesArea.show();
    attachmentUi.clearPendingAttachments();
    messagesUi.updateSendButtons();
    refreshContextUsageNow();

    // Navigate to the new-chat page so the URL reflects it (mirrors loadChat's pushState).
    if (pushState === true && window.location.pathname !== '/') {
      history.pushState({ chatId: null }, '', '/');
    }
  }


  // Context usage helpers.
  // Collect both context-usage buttons that are present in the DOM.
  function contextUsageButtons() {
    return [dom.$contextUsageBtn, dom.$contextUsageBtnConv].filter(function keep($el) {
      return $el && $el.length;
    });
  }

  // Sync disabled state on context compression controls.
  function syncContextCompressionButtons() {
    const disabled = !!state.isChatGenerating || contextCompressionInFlight;
    contextUsageButtons().forEach(function syncButton($btn) {
      $btn
        .prop('disabled', disabled)
        .toggleClass('is-disabled', disabled)
        .attr('aria-disabled', disabled ? 'true' : 'false');
    });
  }

  // Format token counts in compact K/M notation for button labels.
  function formatCompactTokens(value) {
    const numericValue = Number(value) || 0;
    if (numericValue >= 1000000) {
      return `${Math.round(numericValue / 100000) / 10} M`;
    }
    if (numericValue >= 1000) {
      return `${Math.round(numericValue / 1000)} K`;
    }
    return numericValue.toLocaleString(intlLocaleTag());
  }

  // Format token counts with full locale grouping for tooltips.
  function formatDetailedTokens(value) {
    return (Number(value) || 0).toLocaleString(intlLocaleTag());
  }

  // Build the short aria-label shown on the context usage ring.
  function buildContextUsageLabel(percent, used, windowTokens) {
    const remaining = Math.max(0, 100 - percent);
    return t('context.usageLabel', {
      percent,
      remaining,
      used: formatCompactTokens(used),
      window: formatCompactTokens(windowTokens)
    }, `Context: ${percent}% used, ${remaining}% remaining. ${formatCompactTokens(used)} / ${formatCompactTokens(windowTokens)} tokens.`);
  }

  // Build the multi-line tooltip shown on hover for the context ring.
  function buildContextUsageTooltip(percent, used, windowTokens) {
    const remaining = Math.max(0, 100 - percent);
    return [
      t('context.windowTitle', {}, 'Context window:'),
      t('context.used', {}, 'Used') + `: ${percent}%`,
      t('context.remaining', {}, 'Remaining') + `: ${remaining}%`,
      `${formatDetailedTokens(used)} / ${formatDetailedTokens(windowTokens)} tokens`
    ].join('\n');
  }

  // Apply ring progress and accessibility text to one context button.
  function updateContextUsageButtonMetrics($btn, percent, label, tooltip) {
    const boundedPercent = Math.max(0, Math.min(100, percent));
    const circumference = 37.7;
    const progress = boundedPercent > 0
      ? Math.max(1.8, (boundedPercent / 100) * circumference)
      : 0;
    $btn
      .css('--context-usage-progress', progress.toFixed(2))
      .removeAttr('title')
      .removeAttr('data-tooltip')
      .attr('data-context-tooltip', tooltip)
      .attr('aria-label', label);
  }

  // Render context usage metrics and warning states on all ring buttons.
  function setContextUsageUi(payload) {
    const ratio = Math.max(0, Math.min(1, Number(payload && payload.ratio) || 0));
    const percent = Math.round(ratio * 100);
    const used = Number(payload && payload.estimated_used_tokens) || 0;
    const windowTokens = Number(payload && payload.context_window_tokens) || 0;
    state.contextUsage = payload || {};
    if (contextCompressionInFlight) {
      contextUsageButtons().forEach(function updateBusy($btn) {
        $btn
          .removeClass('is-warn is-danger is-compressed')
          .addClass('is-compressing')
          .css('--context-usage-progress', '37.7')
          .removeAttr('title')
          .removeAttr('data-tooltip')
          .attr('data-context-tooltip', `${t('context.windowTitle', {}, 'Context window:')}\n${t('context.compressing', {}, 'Compressing context')}`)
          .attr('aria-label', t('context.compressionInProgress', {}, 'Context compression in progress'));
      });
      syncContextCompressionButtons();
      return;
    }
    const compressedActive = payload && payload.compressed_context_active === true;
    const showCompressedIndicator = compressedActive && !hideCompressedIndicator;
    const label = showCompressedIndicator
      ? `${buildContextUsageLabel(percent, used, windowTokens)} ${t('context.compressedActive', {}, 'Compressed context is active.')}`
      : buildContextUsageLabel(percent, used, windowTokens);
    const tooltip = showCompressedIndicator
      ? `${buildContextUsageTooltip(percent, used, windowTokens)}\n${t('context.compressedActiveTooltip', {}, 'Compressed context active')}`
      : buildContextUsageTooltip(percent, used, windowTokens);

    contextUsageButtons().forEach(function updateOne($btn) {
      $btn.removeClass('is-warn is-danger is-compressed is-compressing');
      updateContextUsageButtonMetrics($btn, percent, label, tooltip);
      if (ratio >= 0.9) {
        $btn.addClass('is-danger');
      } else if (ratio >= 0.75) {
        $btn.addClass('is-warn');
      }
      if (showCompressedIndicator) {
        $btn.addClass('is-compressed');
      }
    });
    syncContextCompressionButtons();
  }

  // Toggle the compressing spinner state while a compression request runs.
  function setContextCompressionBusy(isBusy) {
    contextCompressionInFlight = !!isBusy;
    if (contextCompressionInFlight) {
      contextUsageButtons().forEach(function updateBusy($btn) {
        $btn
          .removeClass('is-warn is-danger is-compressed')
          .addClass('is-compressing')
          .css('--context-usage-progress', '37.7')
          .removeAttr('title')
          .removeAttr('data-tooltip')
          .attr('data-context-tooltip', `${t('context.windowTitle', {}, 'Context window:')}\n${t('context.compressing', {}, 'Compressing context')}`)
          .attr('aria-label', t('context.compressionInProgress', {}, 'Context compression in progress'));
      });
      syncContextCompressionButtons();
      return;
    }
    setContextUsageUi(state.contextUsage || {});
  }

  // Read draft text from the active composer for usage estimation.
  function getContextUsageDraftText(overrideText) {
    if (overrideText !== undefined && overrideText !== null) {
      return String(overrideText || '');
    }
    const activeInput = dom.$chatInputConv && dom.$chatInputConv.is(':visible')
      ? dom.$chatInputConv
      : dom.$chatInput;
    return String(activeInput && activeInput.length ? activeInput.val() : '');
  }

  // Fetch fresh context usage metrics from the backend.
  async function refreshContextUsageNow(options) {
    const refreshOptions = options || {};
    if (contextUsageRefreshPromise && !refreshOptions.force) {
      return contextUsageRefreshPromise;
    }

    const requestPromise = (async function refreshUsage() {
      const draftText = getContextUsageDraftText(refreshOptions.draftText);
      const systemPrompt = String(dom.$systemPrompt && dom.$systemPrompt.length ? dom.$systemPrompt.val() : '');
      const instantMode = !requestWantsReasoning(parametersUi.collectOptionsPayload());
      const payload = await getJson(`/api/context_usage/?engine=${encodeURIComponent(engineManager.getActiveEngine())}&model=${encodeURIComponent(engineManager.getSelectedModelName() || '')}&chat_id=${encodeURIComponent(state.currentChatId || '')}&draft=${encodeURIComponent(draftText)}&system_prompt=${encodeURIComponent(systemPrompt)}&instant_mode=${instantMode ? '1' : '0'}`);
      setContextUsageUi(payload || {});
      return payload || {};
    })();
    contextUsageRefreshPromise = requestPromise;

    try {
      return await requestPromise;
    } catch (_error) {
      // keep silent for UI telemetry failures
      return state.contextUsage || {};
    } finally {
      if (contextUsageRefreshPromise === requestPromise) {
        contextUsageRefreshPromise = null;
      }
    }
  }

  // Start periodic context usage refresh while the page is open.
  function startContextUsagePolling() {
    if (contextUsagePollTimer !== null) {
      return;
    }

    contextUsagePollTimer = window.setInterval(function pollContextUsage() {
      refreshContextUsageNow().catch(function ignoreContextUsagePollError() {});
    }, contextUsagePollIntervalMs);
  }

  // Run manual or forced context compression for the active chat.
  async function triggerContextCompression(force) {
    if (state.isChatGenerating || contextCompressionInFlight) {
      return { applied: false, reason: 'busy' };
    }
    if (!state.currentChatId) {
      return { applied: false };
    }
    const draftText = getContextUsageDraftText();
    const $pendingRow = messagesUi.appendCompressionPending();
    setContextCompressionBusy(true);
    try {
      const payload = await postJson('/api/context_compress/', {
        engine: engineManager.getActiveEngine(),
        model: engineManager.getSelectedModelName() || '',
        chat_id: state.currentChatId,
        system_prompt: String(dom.$systemPrompt && dom.$systemPrompt.length ? dom.$systemPrompt.val() : ''),
        draft: draftText,
        force: !!force
      });
      messagesUi.removeCompressionPending($pendingRow);
      if (payload && payload.applied && payload.message) {
        hideCompressedIndicator = false;
        clearCompressedIndicatorAfterNextAssistant = true;
        const message = payload.message;
        messagesUi.appendMessage(
          message.role,
          message.content || '',
          (message.attachments || message.images || []).map(attachmentUi.normalizeAttachment).filter(Boolean),
          message.created_at,
          {
            activitySegments: Array.isArray(message.activity_segments) ? message.activity_segments : [],
            reasoningMode: message.reasoning_mode === true,
            messageId: message.id
          }
        );
      }
      await refreshContextUsageNow({ autoCompress: false });
      return payload || { applied: false };
    } catch (error) {
      messagesUi.removeCompressionPending($pendingRow);
      throw error;
    } finally {
      setContextCompressionBusy(false);
    }
  }

  // Auto-compress context when usage crosses the server threshold before send.
  async function maybeAutoCompressContextBeforeSend(draftText) {
    const freshUsage = await refreshContextUsageNow({
      draftText,
      force: true
    });
    const usage = freshUsage && typeof freshUsage === 'object'
      ? freshUsage
      : (state.contextUsage && typeof state.contextUsage === 'object' ? state.contextUsage : {});
    const ratio = Number(usage.ratio || 0);
    const threshold = Number(usage.threshold_ratio || 0.8);
    const shouldCompress = ratio >= Math.max(0.8, threshold);
    if (!shouldCompress) {
      return;
    }
    const now = Date.now();
    if (now - contextAutoCompressionAt < 20000) {
      return;
    }
    contextAutoCompressionAt = now;
    try {
      await triggerContextCompression(false);
      await refreshContextUsageNow({ autoCompress: false });
    } catch (_error) {
      // ignore compression failures in send path
    }
  }

  // Debounce context usage refresh while the user types in the composer.
  function scheduleContextUsageRefresh() {
    if (contextUsageTimer !== null) {
      window.clearTimeout(contextUsageTimer);
    }
    contextUsageTimer = window.setTimeout(function run() {
      contextUsageTimer = null;
      refreshContextUsageNow();
    }, 250);
  }


  // Attachment payload helpers.
  // Normalize pending attachments into the request-safe shape.
  function clonePendingAttachments(attachments) {
    return (attachments || [])
      .map(attachmentUi.normalizeAttachment)
      .filter(Boolean);
  }

  // Resolve attachment metadata into the payload shape expected by the backend.
  async function buildAttachmentPayloads(attachments) {
    const payloads = [];

    for (const attachment of attachments || []) {
      const resolved = await attachmentUi.resolveAttachmentData(attachment);
      if (!resolved) {
        continue;
      }

      // URL attachments: sent without data/base64. Server will fetch content via read_page.
      if (resolved.kind === 'url' || resolved.url) {
        payloads.push({
          kind: 'url',
          name: resolved.name || resolved.url,
          url: resolved.url || resolved.name,
          mime_type: resolved.mimeType || 'text/x-url',
          size_bytes: 0
        });
        continue;
      }

      if (!resolved.base64) {
        continue;
      }
      if (resolved.fileId && resolved.kind !== 'image') {
        continue;
      }

      payloads.push({
        kind: resolved.kind,
        name: resolved.name,
        mime_type: resolved.mimeType,
        size_bytes: resolved.size,
        data: resolved.base64
      });
    }

    return payloads;
  }

  // Collect unique uploaded file ids referenced by pending attachments.
  function collectUploadedFileIds(attachments) {
    const ids = [];
    const seen = new Set();

    (attachments || []).forEach(function collectId(attachment) {
      const normalized = attachmentUi.normalizeAttachment(attachment);
      const fileId = normalized ? String(normalized.fileId || '').trim() : '';
      if (fileId && !seen.has(fileId)) {
        seen.add(fileId);
        ids.push(fileId);
      }
    });

    return ids;
  }


  // Model resolution.
  // Resolve the model that should be used for one queued request.
  async function resolveModelForRequest(request) {
    const preferredModel = String(request.model || request.preferredModel || '').trim();

    if (preferredModel) {
      return preferredModel;
    }

    if (Array.isArray(state.modelsCache[request.engine]) && state.modelsCache[request.engine].length > 0) {
      return state.modelsCache[request.engine][0] || '';
    }

    const models = await engineManager.fetchModelsForEngine(request.engine);
    state.modelsCache[request.engine] = models;
    return models[0] || '';
  }


  // Streaming requests.
  // Stream one chat request into the provided assistant row.
  async function streamChat(request, $msgRow) {
    const $bubbleContent = $msgRow.find('.msg-bubble');

    try {
      const selectedModel = await resolveModelForRequest(request);
      if (!selectedModel) {
        throw new Error(`No models available for ${request.engine}`);
      }

      request.model = selectedModel;

      const isRegenerate = !!request.regenerate;
      const targetChatId = request.chatId || state.currentChatId;

      const payload = {
        engine: request.engine,
        model: selectedModel,
        system_prompt: request.systemPrompt,
        options: request.options || {}
      };

      if (!isRegenerate) {
        payload.message = request.text;
        payload.chat_id = targetChatId;
      } else if (request.userMessageId) {
        payload.user_message_id = request.userMessageId;
      }
      if (isRegenerate && request.preserveContextCompression) {
        payload.preserve_context_compression = true;
      }

      if (request.toolServerIds && request.toolServerIds.length > 0) {
        payload.tool_server_ids = request.toolServerIds;
      }
      if (!isRegenerate && request.deepResearch === true) {
        payload.deep_research = true;
      }
      if (!isRegenerate) {
        const attachmentPayloads = await buildAttachmentPayloads(request.attachments);
        if (attachmentPayloads.length > 0) {
          payload.attachments = attachmentPayloads;
        }
        const uploadedFileIds = collectUploadedFileIds(request.attachments);
        if (uploadedFileIds.length > 0) {
          payload.uploaded_file_ids = uploadedFileIds;
        }
      }

      const url = isRegenerate
        ? `/api/chat/${targetChatId}/regenerate/`
        : '/api/chat/';

      state.currentAbortController = new AbortController();
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify(payload),
        signal: state.currentAbortController.signal
      });

      $bubbleContent.empty();

      if (!response.ok) {
        try {
          const errorData = await response.json();
          $bubbleContent.html(`[Error: ${errorData.error || 'Server error'}]`);
        } catch (_error) {
          $bubbleContent.html(`[Error: ${response.status} ${response.statusText}]`);
        }

        return;
      }

      // Stamp backend message IDs on the DOM so delete/regenerate target the
      // real DB rows instead of falling back to DOM-only removal.
      const userMessageId = response.headers.get('X-User-Message-ID');
      const assistantMessageId = response.headers.get('X-Assistant-Message-ID');
      activeGenerationId = String(response.headers.get('X-Generation-ID') || '').trim();
      if (userMessageId && request.$userRow && request.$userRow.length) {
        request.$userRow.attr('data-message-id', userMessageId);
        request.userMessageId = userMessageId;
      }
      if (assistantMessageId && $msgRow && $msgRow.length) {
        $msgRow.attr('data-message-id', assistantMessageId);
      }

      // The backend can create a chat lazily. When that happens, patch the
      // queued requests so every follow-up stays inside the same thread.
      const returnedChatId = response.headers.get('X-Chat-ID');
      if (returnedChatId && state.currentChatId !== returnedChatId) {
        state.currentChatId = returnedChatId;
        request.chatId = returnedChatId;

        state.chatRequestQueue.forEach(function patchQueuedRequest(queuedRequest) {
          if (!queuedRequest.chatId) {
            queuedRequest.chatId = returnedChatId;
          }
        });

        if (!dom.$historyList.find(`.chat-item[data-chat-id="${state.currentChatId}"]`).length) {
          const title = buildChatTitle(request.text, request.attachments.length > 0);
          historyUi.prependChatItem(state.currentChatId, title, 'just now');
        } else {
          historyUi.setActiveChat(state.currentChatId);
        }

        const chatTitle = buildChatTitle(request.text, request.attachments.length > 0);
        dom.$chatTitle.text(chatTitle);
        document.title = `${chatTitle} - ASLM`;
        history.pushState({ chatId: state.currentChatId }, chatTitle, `/chat/${state.currentChatId}/`);
      }

      // Read the response stream chunk by chunk. The custom read helper lets
      // us stop promptly when the user aborts generation.
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let fullText = '';
      let lastRenderedText = '';
      let streamRenderTimer = null;
      let streamRenderLastAt = 0;
      const streamRenderIntervalMs = 80;
      const signal = state.currentAbortController ? state.currentAbortController.signal : null;

      // Batch expensive timeline/markdown work while chunks are arriving.
      function renderStreamFrame(finalRender) {
        if (streamRenderTimer !== null) {
          window.clearTimeout(streamRenderTimer);
          streamRenderTimer = null;
        }

        if (lastRenderedText === fullText && !finalRender) {
          return;
        }

        const area = dom.$messagesArea[0];
        const isNearBottom = area.scrollHeight - area.clientHeight <= area.scrollTop + 50;

        if (finalRender) {
          messagesUi.renderMessageHtml($msgRow, fullText);
        } else {
          messagesUi.renderMessageStream($msgRow, fullText);
        }

        lastRenderedText = fullText;
        streamRenderLastAt = performance.now();

        if (isNearBottom) {
          messagesUi.scrollBottom();
        }
      }

      // Schedule a streaming paint within a small latency budget.
      function scheduleStreamRender() {
        if (streamRenderTimer !== null) {
          return;
        }

        const now = performance.now();
        const delay = Math.max(0, streamRenderIntervalMs - (now - streamRenderLastAt));

        streamRenderTimer = window.setTimeout(function onStreamRenderTimer() {
          window.requestAnimationFrame(function onStreamRenderFrame() {
            streamRenderTimer = null;
            renderStreamFrame(false);
          });
        }, delay);
      }

      // Read one chunk or fail immediately on abort.
      function readOrAbort() {
        if (!signal) {
          return reader.read();
        }

        if (signal.aborted) {
          return Promise.reject(new DOMException('Aborted', 'AbortError'));
        }

        return Promise.race([
          reader.read(),
          new Promise(function rejectOnAbort(_, reject) {
            signal.addEventListener('abort', function abortListener() {
              reject(new DOMException('Aborted', 'AbortError'));
            }, { once: true });
          })
        ]);
      }

      try {
        while (true) {
          const { done, value } = await readOrAbort();
          if (done) {
            break;
          }

          const chunk = decoder.decode(value, { stream: true });
          fullText += chunk;
          scheduleStreamRender();
        }
        // Flush decoder tail so split multibyte UTF-8 chars
        // are not dropped at the end of the stream.
        const tail = decoder.decode();
        if (tail) {
          fullText += tail;
        }
      } catch (readError) {
        if (readError.name !== 'AbortError') {
          throw readError;
        }
      } finally {
        renderStreamFrame(true);
        try {
          await reader.cancel();
        } catch (_error) {
          // Ignore cancellation races after the stream has already closed.
        }
        reader.releaseLock();
      }
      return {
        restartAfterCompression: /"restart_generation"\s*:\s*true/.test(fullText)
      };
    } catch (error) {
      if (error.name !== 'AbortError') {
        $bubbleContent.html(`[Error: failed to connect to server - ${error.message}]`);
      }
    } finally {
      state.currentAbortController = null;
      activeGenerationId = '';
    }
    return { restartAfterCompression: false };
  }

  // Process the next queued request if generation is idle.
  async function processChatQueue() {
    if (state.isChatGenerating || state.chatRequestQueue.length === 0) {
      return;
    }

    const request = state.chatRequestQueue.shift();
    if (!request) {
      return;
    }

    state.isChatGenerating = true;
    messagesUi.setQueuedMessageState(request.$userRow, false);
    messagesUi.updateSendButtons();
    syncContextCompressionButtons();

    const $assistantRow = messagesUi.appendTyping();
    $assistantRow.data('reasoningModeEnabled', !!request.reasoningModeEnabled);
    messagesUi.scrollBottom();

    try {
      const streamResult = await streamChat(request, $assistantRow);
      if (streamResult && streamResult.restartAfterCompression && request.$userRow && request.$userRow.length) {
        const continuationRequest = buildQueuedRequest('', []);
        continuationRequest.regenerate = true;
        continuationRequest.preserveContextCompression = true;
        continuationRequest.chatId = state.currentChatId;
        continuationRequest.userMessageId = request.userMessageId || request.$userRow.attr('data-message-id') || null;
        continuationRequest.$userRow = request.$userRow;
        state.chatRequestQueue.unshift(continuationRequest);
      }
    } finally {
      if ($assistantRow.find('.msg-actions').length === 0) {
        $assistantRow.find('.msg-body').append(context.icons.buildMessageActionsHtml());
      }
      messagesUi.syncMessageSourcesButton($assistantRow);

      messagesUi.updateRegenButtons();
      state.isChatGenerating = false;
      messagesUi.updateSendButtons();
      syncContextCompressionButtons();
      if (clearCompressedIndicatorAfterNextAssistant) {
        hideCompressedIndicator = true;
        clearCompressedIndicatorAfterNextAssistant = false;
        refreshContextUsageNow();
      }

      if (state.chatRequestQueue.length > 0) {
        processChatQueue();
      }
    }
  }


  // Request building.
  // Return whether one thinking option value means reasoning should be shown.
  function isReasoningOptionEnabled(value) {
    if (value === undefined || value === null) {
      return false;
    }

    if (typeof value === 'boolean') {
      return value;
    }

    const normalized = String(value).trim().toLowerCase();
    return !!normalized && !['false', '0', 'off', 'no', 'none', 'disabled'].includes(normalized);
  }

  // Snapshot whether the current request is expected to produce reasoning.
  // The assistant row receives this before the first stream chunk, so early
  // tool events render inside the reasoning shell immediately.
  function requestWantsReasoning(options) {
    if (!state.thinkState.supported) {
      return false;
    }

    const safeOptions = options && typeof options === 'object' ? options : {};

    if (state.thinkState.levelSupported) {
      if (Object.prototype.hasOwnProperty.call(safeOptions, state.thinkState.levelParamName)) {
        return isReasoningOptionEnabled(safeOptions[state.thinkState.levelParamName]);
      }
      return isReasoningOptionEnabled(state.thinkState.level);
    }

    if (state.thinkState.toggleSupported) {
      if (Object.prototype.hasOwnProperty.call(safeOptions, state.thinkState.paramName)) {
        return isReasoningOptionEnabled(safeOptions[state.thinkState.paramName]);
      }
      return !!state.thinkState.enabled;
    }

    return false;
  }

  // Snapshot the current UI state into one queued chat request.
  function buildQueuedRequest(text, attachmentsToSend) {
    const options = parametersUi.collectOptionsPayload();
    const deepResearch = state.deepResearchEnabled === true;

    return {
      id: `queued-${++state.queuedMessageCounter}`,
      text,
      attachments: clonePendingAttachments(attachmentsToSend),
      engine: engineManager.getActiveEngine(),
      preferredModel: engineManager.getSelectedModelName(),
      systemPrompt: dom.$systemPrompt.val(),
      options,
      reasoningModeEnabled: requestWantsReasoning(options),
      toolServerIds: !deepResearch && state.toolState.supported ? parametersUi.getSelectedToolServerIds() : [],
      deepResearch,
      chatId: state.currentChatId
    };
  }

  // Queue one user message for generation.
  async function sendMessage(text, $input) {
    if (Date.now() < sendCooldownUntil) {
      return;
    }
    const rawText = String(text || '');
    const messageText = rawText.trim() ? rawText : '';
    if (!messageText && state.attachmentState.pending.length === 0) {
      return;
    }
    if (state.attachmentState.pending.some(function isBlocked(attachment) {
      return attachment && (attachment.status === 'uploading' || attachment.status === 'error');
    })) {
      return;
    }

    sendCooldownUntil = Date.now() + sendCooldownMs;
    if (state.contextUsage && state.contextUsage.compressed_context_active === true) {
      // UI rule: compression highlight is one-shot. Once the user sends the
      // next message, return the indicator to normal immediately.
      hideCompressedIndicator = true;
      clearCompressedIndicatorAfterNextAssistant = false;
      setContextUsageUi(state.contextUsage || {});
    }
    await maybeAutoCompressContextBeforeSend(messageText);

    const attachmentsToSend = clonePendingAttachments(state.attachmentState.pending);
    const queued = state.isChatGenerating || state.chatRequestQueue.length > 0;

    if (dom.$welcomeScreen.is(':visible')) {
      dom.$welcomeScreen.hide();
      dom.$conversationInput.show();
      dom.$chatInputConv.val('').css('height', 'auto').focus();
    }

    const request = buildQueuedRequest(messageText, attachmentsToSend);
    request.$userRow = messagesUi.appendMessage('user', messageText, attachmentsToSend, null, {
      queued,
      messageKey: request.id
    });

    $input.val('').css('height', 'auto');
    attachmentUi.clearPendingAttachments();
    messagesUi.updateSendButtons();
    refreshContextUsageNow();

    state.chatRequestQueue.push(request);
    processChatQueue();
  }

  // Abort the active generation locally and on the backend.
  function abortGeneration() {
    if (state.currentAbortController) {
      state.currentAbortController.abort();
    }

    state.isChatGenerating = false;
    messagesUi.updateSendButtons();
    syncContextCompressionButtons();

    fetch('/api/chat/abort/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify({
        engine: engineManager.getActiveEngine(),
        generation_id: activeGenerationId || ''
      })
    }).catch(function ignoreAbortError() {});
  }

  // Queue a regeneration request that targets an existing user message in the chat.
  function queueRegenerationRequest($userRow, $assistantRow) {
    const request = buildQueuedRequest('', []);
    request.regenerate = true;
    request.chatId = state.currentChatId;
    request.userMessageId = $userRow && $userRow.length ? $userRow.attr('data-message-id') : null;
    request.$userRow = $userRow && $userRow.length ? $userRow : { length: 0 };
    request.$existingAssistantRow = $assistantRow && $assistantRow.length ? $assistantRow : null;
    state.chatRequestQueue.push(request);
    processChatQueue();
  }


  // Regeneration helpers.
  // Regenerate the most recent assistant response.
  function regenerateLastResponse() {
    if (!state.currentChatId) {
      return;
    }

    function startRegen() {
      const $lastUser = dom.$messagesInner.find('.msg.user').last();
      const $lastAssistant = dom.$messagesInner.find('.msg.assistant').last();
      if (!$lastUser.length) {
        return;
      }
      if ($lastAssistant.length) {
        $lastAssistant.remove();
      }
      messagesUi.updateSendButtons();
      queueRegenerationRequest($lastUser, null);
    }

    if (state.isChatGenerating) {
      abortGeneration();
      setTimeout(startRegen, 300);
      return;
    }

    startRegen();
  }

  // Regenerate the assistant response attached to one user row.
  function regenerateFromUserMessage($userMsg) {
    if (!state.currentChatId || state.isChatGenerating) {
      return;
    }

    const $nextAssistant = $userMsg.next('.msg.assistant');
    if (!$nextAssistant.length) {
      return;
    }

    $nextAssistant.remove();
    messagesUi.updateRegenButtons();
    queueRegenerationRequest($userMsg, null);
  }


  // Composer wiring.
  // Slash command palette helpers.
  function closeSlashPalette() {
    if (slashPalette.$panel) {
      slashPalette.$panel.remove();
    }
    slashPalette.$panel = null;
    slashPalette.$input = null;
    slashPalette.entries = [];
    slashPalette.activeIndex = 0;
    slashPalette.query = '';
    slashPalette.tokenStart = -1;
    slashPalette.tokenEnd = -1;
  }

  // Shared icon resolver for tool server rows in the slash palette.
  function toolServerIconClass(server) {
    const text = `${server && server.id ? server.id : ''} ${server && server.name ? server.name : ''}`.toLowerCase();
    if (text.includes('browser')) {
      return 'is-browser-agent';
    }
    if (text.includes('sandbox')) {
      return 'is-sandbox';
    }
    if (text.includes('web') || text.includes('search')) {
      return 'is-web-search';
    }
    if (server && server.user_mcp) {
      return 'is-mcp';
    }
    return 'is-generic-tool';
  }

  // Read the current slash token from a textarea caret position.
  function getSlashToken($input) {
    const inputEl = $input && $input[0];
    if (!inputEl) {
      return null;
    }
    const value = String($input.val() || '');
    const caret = Number(inputEl.selectionStart || 0);
    const before = value.slice(0, caret);
    const match = before.match(/(?:^|\s)\/([^\s]*)$/);
    if (!match) {
      return null;
    }
    const tokenStart = caret - match[0].trimStart().length;
    return {
      query: String(match[1] || '').toLowerCase(),
      tokenStart,
      tokenEnd: caret
    };
  }

  // Read the server list embedded in the page before async model state arrives.
  function readToolServersFromPage() {
    try {
      const raw = document.getElementById('availableToolServersData')?.textContent || '[]';
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (_error) {
      return [];
    }
  }

  // Return bundled tools and user MCP servers from live state or page fallback.
  function getSlashToolSources() {
    const bundledTools = Array.isArray(state.availableToolServers) && state.availableToolServers.length
      ? state.availableToolServers
      : (Array.isArray(state.defaultAvailableToolServers) ? state.defaultAvailableToolServers : []);
    const userMcpTools = Array.isArray(state.userMcpToolServers) && state.userMcpToolServers.length
      ? state.userMcpToolServers
      : (Array.isArray(state.defaultUserMcpToolServers) ? state.defaultUserMcpToolServers : []);
    const allTools = [...bundledTools, ...userMcpTools];
    const pageTools = allTools.length ? [] : readToolServersFromPage();
    const source = allTools.length ? allTools : pageTools;
    return {
      tools: source.filter(function filterTool(server) {
        return server && !server.user_mcp;
      }),
      mcp: source.filter(function filterMcp(server) {
        return server && server.user_mcp;
      })
    };
  }

  // Check whether the selected engine/model can receive tool definitions.
  function modelSupportsToolsForSlash() {
    if (!state.toolState || state.toolState.supported !== true) {
      return false;
    }
    if (state.currentModelInfo && state.currentModelInfo.supports_tool_calling === false) {
      return false;
    }
    return true;
  }

  // Explain why a tool row cannot be applied from the slash palette.
  function slashToolUnavailableReason(server) {
    if (!modelSupportsToolsForSlash()) {
      return t('tools.unsupportedByModel', null, 'Model does not support tools');
    }
    if (server && server.requires_docker && server.docker_available === false) {
      return t('tools.dockerRequiredShort', null, 'Docker required');
    }
    return '';
  }

  // Build the canonical slash command for one tool server id.
  function slashToolCommand(serverId) {
    return serverId === 'web_search' ? '/search ' : `/tool ${serverId} `;
  }

  // Build the small right-side status chip for one tool row.
  function slashEntryStatus(server, unavailableReason) {
    const serverId = String(server && server.id || '').trim();
    if (unavailableReason) {
      return '';
    }
    if (serverId && state.selectedToolServerIds && state.selectedToolServerIds.has(serverId)) {
      return t('common.enabled', null, 'Enabled');
    }
    if (server && server.user_mcp) {
      const count = Number(server.tool_count || (server.tools || []).length || 0);
      return count > 0 ? t('mcp.toolCountShort', { count }, `${count} tools`) : '';
    }
    return '';
  }

  // Convert one tool or MCP server into a slash palette entry.
  function buildSlashToolEntry(server, section) {
    const serverId = String(server && server.id || '').trim();
    if (!serverId || serverId.toLowerCase() === 'deep_research') {
      return null;
    }
    const unavailableReason = slashToolUnavailableReason(server);
    const command = slashToolCommand(serverId);
    return {
      kind: section,
      section,
      command,
      iconClass: toolServerIconClass(server),
      title: String(server && server.name || serverId),
      detail: command.trim(),
      status: slashEntryStatus(server, unavailableReason),
      disabled: Boolean(unavailableReason),
      serverId,
      requiresDocker: Boolean(server && server.requires_docker),
      dockerUnavailable: Boolean(server && server.requires_docker && server.docker_available === false),
      keywords: `${command} ${serverId} ${server && server.name ? server.name : ''}`
    };
  }

  // Match slash entries by prefix only, like command autocomplete.
  function slashMatchesQuery(entry, needle) {
    if (!needle) {
      return true;
    }
    const haystack = `${entry.command} ${entry.title} ${entry.detail} ${entry.keywords}`
      .toLowerCase()
      .split(/[^a-z0-9_.-]+/)
      .filter(Boolean);
    return haystack.some(function matchToken(token) {
      return token.startsWith(needle);
    });
  }

  // Build all visible slash entries for the current token.
  function buildSlashEntries(query) {
    const entries = [];
    const sources = getSlashToolSources();

    sources.tools.forEach(function addTool(server) {
      const entry = buildSlashToolEntry(server, 'tools');
      if (entry) {
        entries.push(entry);
      }
    });

    sources.mcp.forEach(function addMcp(server) {
      const entry = buildSlashToolEntry(server, 'mcp');
      if (entry) {
        entries.push(entry);
      }
    });

    const folders = skillsUi && typeof skillsUi.getSkillFolders === 'function'
      ? skillsUi.getSkillFolders()
      : [];
    (Array.isArray(folders) ? folders : []).forEach(function addSkill(folder) {
      if (!folder) {
        return;
      }
      const name = String(folder.name || '').trim();
      if (!name) {
        return;
      }
      const skillDisabled = folder.enabled === false;
      entries.push({
        kind: 'skill',
        section: 'skills',
        command: `/skill ${name} `,
        iconClass: 'is-skills-file',
        title: String(folder.title || name),
        skillName: name,
        detail: `/skill ${name}`,
        status: skillDisabled ? t('skills.disabledShort', null, 'Disabled') : '',
        disabled: skillDisabled,
        keywords: `/skill ${name} ${folder.title || ''}`
      });
    });

    // The palette scrolls, so every matching entry stays visible.
    const needle = String(query || '').trim().toLowerCase();
    return entries.filter(function matchEntry(entry) {
      return slashMatchesQuery(entry, needle);
    });
  }

  // Find the first command that can actually be inserted.
  function firstEnabledSlashEntryIndex(entries) {
    return Math.max(0, entries.findIndex(function findEnabled(entry) {
      return !entry.disabled;
    }));
  }

  // Keep keyboard focus on an enabled row when possible.
  function clampSlashActiveIndex(entries, currentIndex) {
    if (!entries.length) {
      return 0;
    }
    const currentEntry = entries[currentIndex];
    if (currentEntry && !currentEntry.disabled) {
      return currentIndex;
    }
    return firstEnabledSlashEntryIndex(entries);
  }

  // Move the active keyboard row while skipping disabled commands.
  function moveSlashActive(delta) {
    const entries = slashPalette.entries;
    if (!entries.length || entries.every(function allDisabled(entry) { return entry.disabled; })) {
      return;
    }
    let index = slashPalette.activeIndex;
    for (let step = 0; step < entries.length; step += 1) {
      index = (index + delta + entries.length) % entries.length;
      if (!entries[index].disabled) {
        slashPalette.activeIndex = index;
        return;
      }
    }
  }

  // Return the visual section title for one slash entry group.
  function slashSectionLabel(section) {
    if (section === 'mcp') {
      return t('settings.mcp', null, 'MCP');
    }
    if (section === 'skills') {
      return t('settings.skills', null, 'Skills');
    }
    return t('settings.tools', null, 'Tools');
  }

  // Re-check Docker availability and refresh tool metadata in place.
  async function refreshDockerForSlash(ev) {
    ev.preventDefault();
    ev.stopPropagation();
    const $btn = $(ev.currentTarget);
    if ($btn.hasClass('is-loading')) {
      return;
    }
    $btn.addClass('is-loading');
    try {
      await postJson('/api/docker_status/refresh/', {});
      if (parametersUi && typeof parametersUi.reloadAvailableToolServers === 'function') {
        await parametersUi.reloadAvailableToolServers();
      }
    } catch (_error) {
      // The next render reflects the current server-side status if it changed.
    } finally {
      $btn.removeClass('is-loading');
      if (slashPalette.$input && slashPalette.$input.length) {
        updateSlashPalette(slashPalette.$input);
      }
    }
  }

  // Render one slash palette row.
  function renderSlashEntry(entry, index) {
    const $row = $('<div class="slash-command-row" role="option" tabindex="-1">')
      .toggleClass('is-active', index === slashPalette.activeIndex)
      .toggleClass('is-disabled', Boolean(entry.disabled))
      .attr('aria-selected', index === slashPalette.activeIndex ? 'true' : 'false')
      .attr('aria-disabled', entry.disabled ? 'true' : 'false');
    $row.append($('<span class="composer-tool-icon slash-command-icon" aria-hidden="true">').addClass(entry.iconClass));

    const $text = $('<span class="slash-command-text">');
    const $main = $('<span class="slash-command-main">');
    $main.append($('<span class="slash-command-title">').text(entry.title));
    if (entry.status) {
      $main.append($('<span class="slash-command-status">')
        .toggleClass('is-warning', Boolean(entry.disabled))
        .toggleClass('is-enabled', !entry.disabled && state.selectedToolServerIds && state.selectedToolServerIds.has(entry.serverId))
        .text(entry.status));
    }
    $text.append($main);
    $text.append($('<span class="slash-command-detail">').text(entry.detail));
    $row.append($text);

    if (entry.dockerUnavailable) {
      const $refresh = $('<button type="button" class="slash-command-refresh" aria-label="Re-check Docker" title="Re-check Docker">');
      $refresh.append('<span class="composer-tool-refresh-icon" aria-hidden="true"></span>');
      $refresh.on('mousedown click', function stopRefreshPointer(pointerEv) {
        pointerEv.stopPropagation();
      });
      $refresh.on('click', refreshDockerForSlash);
      $row.append($refresh);
    }

    $row.on('mousedown', function onMouseDown(ev) {
      ev.preventDefault();
    });
    $row.on('click', function onClick(ev) {
      ev.preventDefault();
      applySlashEntry(index);
    });
    return $row;
  }

  // Render one slash palette section with its divider and rows.
  function renderSlashSection($panel, section, entries) {
    if (!entries.length) {
      return;
    }
    const $section = $('<div class="slash-command-section">');
    $section.append($('<div class="slash-command-section-title">').text(slashSectionLabel(section)));
    entries.forEach(function appendEntry(entry) {
      const index = slashPalette.entries.indexOf(entry);
      $section.append(renderSlashEntry(entry, index));
    });
    $panel.append($section);
  }

  // Render or update the slash palette for the current composer token.
  function renderSlashPalette($input, token) {
    const entries = buildSlashEntries(token.query);
    if (!entries.length) {
      closeSlashPalette();
      return;
    }

    const queryChanged = slashPalette.query !== token.query;
    slashPalette.$input = $input;
    slashPalette.entries = entries;
    slashPalette.query = token.query;
    slashPalette.activeIndex = queryChanged
      ? firstEnabledSlashEntryIndex(entries)
      : clampSlashActiveIndex(entries, Math.min(slashPalette.activeIndex, entries.length - 1));
    slashPalette.tokenStart = token.tokenStart;
    slashPalette.tokenEnd = token.tokenEnd;

    if (!slashPalette.$panel) {
      slashPalette.$panel = $('<div class="slash-command-palette" role="listbox" aria-label="Slash commands">');
      $input.closest('.input-wrapper').append(slashPalette.$panel);
    }

    slashPalette.$panel.empty();
    ['tools', 'mcp', 'skills'].forEach(function renderSection(section) {
      renderSlashSection(
        slashPalette.$panel,
        section,
        entries.filter(function filterBySection(entry) {
          return entry.section === section;
        })
      );
    });
  }

  // Open, update, or close the slash palette after composer input changes.
  function updateSlashPalette($input) {
    const token = getSlashToken($input);
    if (!token) {
      closeSlashPalette();
      return;
    }
    renderSlashPalette($input, token);
  }

  // Insert the selected slash command as inline text at the typed token.
  // The command stays part of the message, so the backend sees it at the
  // exact position where the user wrote it.
  function applySlashEntry(index) {
    const entry = slashPalette.entries[index];
    const $input = slashPalette.$input;
    if (!entry || !$input || !$input.length) {
      closeSlashPalette();
      return;
    }
    if (entry.disabled) {
      return;
    }
    const value = String($input.val() || '');
    const before = value.slice(0, slashPalette.tokenStart);
    const after = value.slice(slashPalette.tokenEnd).replace(/^[ \t]+/, '');
    const insertion = String(entry.command || '');
    const nextValue = `${before}${insertion}${after}`;
    const caret = before.length + insertion.length;
    $input.val(nextValue);
    const inputEl = $input[0];
    if (inputEl && inputEl.setSelectionRange) {
      inputEl.setSelectionRange(caret, caret);
    }
    closeSlashPalette();
    $input.trigger('input').trigger('focus');
  }

  // Handle keyboard navigation while the slash palette is open.
  function handleSlashPaletteKeydown(event) {
    if (!slashPalette.$panel || !slashPalette.entries.length) {
      return false;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      moveSlashActive(1);
      renderSlashPalette(slashPalette.$input, {
        query: slashPalette.query,
        tokenStart: slashPalette.tokenStart,
        tokenEnd: slashPalette.tokenEnd
      });
      return true;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      moveSlashActive(-1);
      renderSlashPalette(slashPalette.$input, {
        query: slashPalette.query,
        tokenStart: slashPalette.tokenStart,
        tokenEnd: slashPalette.tokenEnd
      });
      return true;
    }
    if (event.key === 'Enter' || event.key === 'Tab') {
      event.preventDefault();
      applySlashEntry(slashPalette.activeIndex);
      return true;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      closeSlashPalette();
      return true;
    }
    return false;
  }

  // Bind one textarea and send button pair to the chat workflow.
  function wireInput($input, $button) {
    $input.on('input', function onInput() {
      this.style.height = 'auto';
      this.style.height = `${Math.min(this.scrollHeight, 200)}px`;
      messagesUi.updateSendButtons();
      scheduleContextUsageRefresh();
      updateSlashPalette($input);
    });

    $input.on('keydown', function onKeyDown(event) {
      if (handleSlashPaletteKeydown(event)) {
        return;
      }
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();

        if (!$button.prop('disabled')) {
          closeSlashPalette();
          void sendMessage($input.val(), $input);
        }
      }
    });

    $input.on('blur', function onBlur() {
      // Row clicks keep focus because the palette swallows mousedown, so a
      // real blur means the user moved on and the palette should close.
      if (slashPalette.$input && slashPalette.$input[0] === this) {
        closeSlashPalette();
      }
    });

    $input.on('paste', function onPaste(event) {
      const clipboardData = event.originalEvent && event.originalEvent.clipboardData
        ? event.originalEvent.clipboardData
        : event.clipboardData;
      if (attachmentUi.handleClipboardPaste(clipboardData)) {
        event.preventDefault();
      }
    });

    $button.on('click', function onClick() {
      if ($button.hasClass('stop-btn') && state.isChatGenerating && state.currentAbortController) {
        abortGeneration();
        return;
      }

      if (!$button.prop('disabled')) {
        closeSlashPalette();
        void sendMessage($input.val(), $input);
      }
    });
  }


  // Chat history loading.
  // Load one stored chat into the current page.
  async function loadChat(chatId, pushState, forceReload) {
    if (!chatId || (state.currentChatId === chatId && !forceReload)) {
      return;
    }

    try {
      const data = await getJson(`/api/chat/${chatId}/`);
      if (data.messages === undefined) {
        return;
      }

      state.currentChatId = chatId;
      hideCompressedIndicator = false;
      clearCompressedIndicatorAfterNextAssistant = false;
      historyUi.setActiveChat(chatId);
      parametersUi.applySelectedToolServerIds(data.active_tool_server_ids || []);

      const title = data.title || 'Chat';
      dom.$chatTitle.text(title);
      document.title = `${title} - ASLM`;

      if (pushState !== false) {
        history.pushState({ chatId }, title, `/chat/${chatId}/`);
      }

      dom.$messagesInner.find('.msg').remove();
      dom.$welcomeScreen.hide();
      dom.$messagesArea.show();
      dom.$conversationInput.show();

      const storedMessages = data.messages.map(function buildStoredMessage(message) {
        return {
          role: message.role,
          text: message.content,
          attachments: (message.attachments || message.images || []).map(attachmentUi.normalizeAttachment).filter(Boolean),
          timestamp: message.created_at,
          options: {
            activitySegments: Array.isArray(message.activity_segments) ? message.activity_segments : [],
            reasoningMode: message.reasoning_mode === true,
            messageId: message.id,
            branchLinks: Array.isArray(message.branch_links) ? message.branch_links : []
          }
        };
      });

      messagesUi.appendMessages(storedMessages);
      refreshContextUsageNow();
    } catch (error) {
      console.error('Failed to load chat history:', error);
    }
  }


  // Chat mutations.
  // Rename the chat currently targeted by the history menu.
  async function renameActiveMenuChat() {
    const $item = historyUi.getActiveMenuTarget();
    if (!$item) {
      return;
    }

    const chatId = $item.data('chat-id');
    const currentTitle = $item.find('.chat-item-title').text();
    historyUi.closeChatMenu();

    const newTitle = await textDialog({
      title: t('chat.renameTitle', null, 'Rename chat'),
      label: t('chat.renameLabel', null, 'Chat name'),
      value: currentTitle,
      confirmText: t('sidebar.rename', null, 'Rename')
    });
    if (!newTitle || !newTitle.trim() || newTitle.trim() === currentTitle) {
      return;
    }

    try {
      const data = await patchJson(`/api/chat/${chatId}/rename/`, {
        title: newTitle.trim()
      });
      if (!data.ok) {
        return;
      }

      $item.find('.chat-item-title').text(data.title);
      if (chatId === state.currentChatId) {
        dom.$chatTitle.text(data.title);
        document.title = `${data.title} - ASLM`;
      }
    } catch (error) {
      console.error('Failed to rename chat:', error);
    }
  }

  // Delete the chat currently targeted by the history menu.
  async function deleteActiveMenuChat() {
    const $item = historyUi.getActiveMenuTarget();
    if (!$item) {
      return;
    }

    const chatId = $item.data('chat-id');
    const title = $item.find('.chat-item-title').text();
    historyUi.closeChatMenu();

    const confirmed = await confirmDialog({
      title: t('confirm.deleteChatTitle', null, 'Delete chat'),
      message: t('confirm.deleteChatNamed', { title }, `Delete "${title}"?`),
      confirmText: t('sidebar.delete', null, 'Delete'),
      danger: true
    });
    if (!confirmed) {
      return;
    }

    try {
      const data = await deleteJson(`/api/chat/${chatId}/delete/`);
      if (!data.ok) {
        return;
      }

      historyUi.removeChatItem(chatId);
      if (chatId === state.currentChatId) {
        startNewChat();
      }
    } catch (error) {
      console.error('Failed to delete chat:', error);
    }
  }

  // Download the chat selected in the sidebar as a portable ZIP archive.
  function downloadActiveMenuChat() {
    const $item = historyUi.getActiveMenuTarget();
    if (!$item) {
      return;
    }
    const chatId = String($item.data('chat-id') || '');
    historyUi.closeChatMenu();
    if (!chatId) {
      return;
    }
    const link = document.createElement('a');
    link.href = `/api/chat/${chatId}/export/`;
    link.download = '';
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  // Create and immediately open a linked conversation branch.
  async function branchFromMessage($message) {
    if (state.isChatGenerating) {
      return;
    }
    const messageId = $message && $message.length ? $message.attr('data-message-id') : '';
    if (!messageId) {
      return;
    }
    try {
      const data = await postJson(`/api/message/${messageId}/branch/`, {});
      if (!data.ok || !data.chat_id) {
        return;
      }
      historyUi.prependChatItem(data.chat_id, data.title || 'Branch', 'just now');
      await loadChat(data.chat_id, true);
    } catch (error) {
      console.error('Failed to create chat branch:', error);
    }
  }

  // Replace a user message, truncate its stale continuation, then regenerate.
  async function editUserMessage($message) {
    if (!state.currentChatId || state.isChatGenerating || !$message || !$message.hasClass('user')) {
      return;
    }
    const messageId = $message.attr('data-message-id');
    if (!messageId) {
      return;
    }
    const currentText = String($message.find('.msg-bubble').attr('data-raw') || '');
    const editedText = await largeTextDialog({
      title: t('messages.editTitle', null, 'Edit message'),
      label: t('messages.editHint', null, 'The later conversation will be regenerated.'),
      value: currentText,
      confirmText: t('messages.saveAndRegenerate', null, 'Save and regenerate')
    });
    if (editedText === null || editedText === currentText) {
      return;
    }
    try {
      const data = await patchJson(`/api/message/${messageId}/edit/`, { content: editedText });
      if (!data.ok) {
        return;
      }
      const chatId = state.currentChatId;
      await loadChat(chatId, false, true);
      const $updatedRow = dom.$messagesInner.find(`.msg.user[data-message-id="${messageId}"]`).first();
      if ($updatedRow.length) {
        queueRegenerationRequest($updatedRow, null);
      }
    } catch (error) {
      console.error('Failed to edit user message:', error);
    }
  }

  // Delete one message row and keep the local UI in sync.
  async function deleteMessage($message) {
    const messageId = $message.data('message-id');
    if (!messageId) {
      $message.remove();
      messagesUi.updateRegenButtons();
      return;
    }

    try {
      const data = await deleteJson(`/api/message/${messageId}/delete/`);
      if (data.ok) {
        $message.remove();
        messagesUi.updateRegenButtons();
      }
    } catch (error) {
      console.error('Failed to delete message', messageId, error);
    }
  }

  return {
    abortGeneration,
    branchFromMessage,
    deleteActiveMenuChat,
    deleteMessage,
    downloadActiveMenuChat,
    editUserMessage,
    loadChat,
    processChatQueue,
    regenerateFromUserMessage,
    regenerateLastResponse,
    renameActiveMenuChat,
    sendMessage,
    startNewChat,
    wireInput,
    refreshContextUsageNow,
    startContextUsagePolling,
    triggerContextCompression
  };
}

