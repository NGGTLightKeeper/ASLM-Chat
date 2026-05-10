// Copyright NGGT.LightKeeper. All Rights Reserved.

import { deleteJson, getCsrfToken, getJson, patchJson, postJson } from './api.js';

// Chat controller.
// Create the chat workflow controller for sending, loading, and mutating chats.
export function createChatController(context, dependencies) {
  const {
    attachmentUi,
    engineManager,
    historyUi,
    messagesUi,
    parametersUi
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

  // Chat lifecycle helpers.
  // Build a short title from the first user prompt.
  function buildChatTitle(text, hasAttachments) {
    if (text) {
      return text.substring(0, 40) + (text.length > 40 ? '...' : '');
    }

    return hasAttachments ? 'Attachment chat' : 'New Chat';
  }

  // Reset the page into a fresh chat state.
  function startNewChat() {
    dom.$chatTitle.text('New Chat');
    document.title = 'ASLM Chat';
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
  }

  function contextUsageButtons() {
    return [dom.$contextUsageBtn, dom.$contextUsageBtnConv].filter(function keep($el) {
      return $el && $el.length;
    });
  }

  function syncContextCompressionButtons() {
    const disabled = !!state.isChatGenerating || contextCompressionInFlight;
    contextUsageButtons().forEach(function syncButton($btn) {
      $btn
        .prop('disabled', disabled)
        .toggleClass('is-disabled', disabled)
        .attr('aria-disabled', disabled ? 'true' : 'false');
    });
  }

  function setContextUsageUi(payload) {
    const ratio = Math.max(0, Math.min(1, Number(payload && payload.ratio) || 0));
    const percent = Math.round(ratio * 100);
    const used = Number(payload && payload.estimated_used_tokens) || 0;
    const windowTokens = Number(payload && payload.context_window_tokens) || 0;
    const observed = payload && payload.observed_usage && typeof payload.observed_usage === 'object'
      ? payload.observed_usage
      : {};
    state.contextUsage = payload || {};
    if (contextCompressionInFlight) {
      contextUsageButtons().forEach(function updateBusy($btn) {
        $btn
          .removeClass('is-warn is-danger is-compressed')
          .addClass('is-compressing')
          .attr('title', 'Compressing context now. The model is building a structured summary.');
        $btn.find('.context-usage-text').text('compressing...');
      });
      syncContextCompressionButtons();
      return;
    }
    const observedPrompt = Number(observed.prompt_tokens || 0) || 0;
    const estimator = payload && payload.token_estimator && typeof payload.token_estimator === 'object'
      ? payload.token_estimator
      : {};
    const baseCharsPerToken = Number(estimator.base_chars_per_token || 0);
    const effectiveCharsPerToken = Number(estimator.effective_chars_per_token || 0);
    const observedCharsPerToken = Number(
      estimator.chat_observed_chars_per_token || estimator.observed_chars_per_token || 0
    );
    const compressedActive = payload && payload.compressed_context_active === true;
    const showCompressedIndicator = compressedActive && !hideCompressedIndicator;
    const compressionNote = showCompressedIndicator
      ? ' Compressed context is active; older turns are represented by a structured summary.'
      : ' Compression is not active for this chat yet.';
    let title = observedPrompt > 0
      ? `Context: ~${used.toLocaleString()} / ${windowTokens.toLocaleString()} tokens (${percent}%). Last observed prompt: ${observedPrompt.toLocaleString()} tokens.`
      : `Context: ~${used.toLocaleString()} / ${windowTokens.toLocaleString()} tokens (${percent}%).`;
    if (baseCharsPerToken > 0 || effectiveCharsPerToken > 0 || observedCharsPerToken > 0) {
      const parts = [];
      if (baseCharsPerToken > 0) {
        parts.push(`base chars/token: ${baseCharsPerToken.toFixed(2)}`);
      }
      if (effectiveCharsPerToken > 0) {
        parts.push(`effective chars/token: ${effectiveCharsPerToken.toFixed(2)}`);
      }
      if (observedCharsPerToken > 0) {
        parts.push(`observed chars/token: ${observedCharsPerToken.toFixed(2)}`);
      }
      if (parts.length) {
        title += ` Token estimator (${parts.join(', ')}).`;
      }
    }

    contextUsageButtons().forEach(function updateOne($btn) {
      $btn.removeClass('is-warn is-danger is-compressed is-compressing');
      if (ratio >= 0.9) {
        $btn.addClass('is-danger');
      } else if (ratio >= 0.75) {
        $btn.addClass('is-warn');
      }
      if (showCompressedIndicator) {
        $btn.addClass('is-compressed');
      }
      $btn.attr('title', `${title}${compressionNote}`);
      $btn.find('.context-usage-text').text(showCompressedIndicator ? `${percent}% / compressed` : `${percent}%`);
    });
    syncContextCompressionButtons();
  }

  function setContextCompressionBusy(isBusy) {
    contextCompressionInFlight = !!isBusy;
    if (contextCompressionInFlight) {
      contextUsageButtons().forEach(function updateBusy($btn) {
        $btn
          .removeClass('is-warn is-danger is-compressed')
          .addClass('is-compressing')
          .attr('title', 'Compressing context now. The model is building a structured summary.');
        $btn.find('.context-usage-text').text('compressing...');
      });
      syncContextCompressionButtons();
      return;
    }
    setContextUsageUi(state.contextUsage || {});
  }

  function getContextUsageDraftText(overrideText) {
    if (overrideText !== undefined && overrideText !== null) {
      return String(overrideText || '');
    }
    const activeInput = dom.$chatInputConv && dom.$chatInputConv.is(':visible')
      ? dom.$chatInputConv
      : dom.$chatInput;
    return String(activeInput && activeInput.length ? activeInput.val() : '');
  }

  async function refreshContextUsageNow(options) {
    const refreshOptions = options || {};
    if (contextUsageRefreshPromise && !refreshOptions.force) {
      return contextUsageRefreshPromise;
    }

    const requestPromise = (async function refreshUsage() {
      const draftText = getContextUsageDraftText(refreshOptions.draftText);
      const systemPrompt = String(dom.$systemPrompt && dom.$systemPrompt.length ? dom.$systemPrompt.val() : '');
      const payload = await getJson(`/api/context_usage/?engine=${encodeURIComponent(engineManager.getActiveEngine())}&model=${encodeURIComponent(engineManager.getSelectedModelName() || '')}&chat_id=${encodeURIComponent(state.currentChatId || '')}&draft=${encodeURIComponent(draftText)}&system_prompt=${encodeURIComponent(systemPrompt)}`);
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

  function startContextUsagePolling() {
    if (contextUsagePollTimer !== null) {
      return;
    }

    contextUsagePollTimer = window.setInterval(function pollContextUsage() {
      refreshContextUsageNow().catch(function ignoreContextUsagePollError() {});
    }, contextUsagePollIntervalMs);
  }

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

  function scheduleContextUsageRefresh() {
    if (contextUsageTimer !== null) {
      window.clearTimeout(contextUsageTimer);
    }
    contextUsageTimer = window.setTimeout(function run() {
      contextUsageTimer = null;
      refreshContextUsageNow();
    }, 250);
  }

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
      if (!resolved || !resolved.base64) {
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

    return {
      id: `queued-${++state.queuedMessageCounter}`,
      text,
      attachments: clonePendingAttachments(attachmentsToSend),
      engine: engineManager.getActiveEngine(),
      preferredModel: engineManager.getSelectedModelName(),
      systemPrompt: dom.$systemPrompt.val(),
      options,
      reasoningModeEnabled: requestWantsReasoning(options),
      toolServerIds: state.toolState.supported ? parametersUi.getSelectedToolServerIds() : [],
      chatId: state.currentChatId
    };
  }

  // Queue one user message for generation.
  async function sendMessage(text, $input) {
    if (!text && state.attachmentState.pending.length === 0) {
      return;
    }
    if (state.attachmentState.pending.some(function isBlocked(attachment) {
      return attachment && (attachment.status === 'uploading' || attachment.status === 'error');
    })) {
      return;
    }
    if (state.contextUsage && state.contextUsage.compressed_context_active === true) {
      // UI rule: compression highlight is one-shot. Once the user sends the
      // next message, return the indicator to normal immediately.
      hideCompressedIndicator = true;
      clearCompressedIndicatorAfterNextAssistant = false;
      setContextUsageUi(state.contextUsage || {});
    }
    await maybeAutoCompressContextBeforeSend(text);

    const attachmentsToSend = clonePendingAttachments(state.attachmentState.pending);
    const queued = state.isChatGenerating || state.chatRequestQueue.length > 0;

    if (dom.$welcomeScreen.is(':visible')) {
      dom.$welcomeScreen.hide();
      dom.$conversationInput.show();
      dom.$chatInputConv.val('').css('height', 'auto').focus();
    }

    const request = buildQueuedRequest(text, attachmentsToSend);
    request.$userRow = messagesUi.appendMessage('user', text, attachmentsToSend, null, {
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
  // Bind one textarea and send button pair to the chat workflow.
  function wireInput($input, $button) {
    $input.on('input', function onInput() {
      this.style.height = 'auto';
      this.style.height = `${Math.min(this.scrollHeight, 200)}px`;
      messagesUi.updateSendButtons();
      scheduleContextUsageRefresh();
    });

    $input.on('keydown', function onKeyDown(event) {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();

        if (!$button.prop('disabled')) {
          void sendMessage($input.val().trim(), $input);
        }
      }
    });

    $button.on('click', function onClick() {
      if ($button.hasClass('stop-btn') && state.isChatGenerating && state.currentAbortController) {
        abortGeneration();
        return;
      }

      if (!$button.prop('disabled')) {
        void sendMessage($input.val().trim(), $input);
      }
    });
  }


  // Chat history loading.
  // Load one stored chat into the current page.
  async function loadChat(chatId, pushState) {
    if (!chatId || state.currentChatId === chatId) {
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
            messageId: message.id
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

    const newTitle = window.prompt('Rename chat:', currentTitle);
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

    if (!window.confirm(`Delete "${title}"?`)) {
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
    deleteActiveMenuChat,
    deleteMessage,
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

