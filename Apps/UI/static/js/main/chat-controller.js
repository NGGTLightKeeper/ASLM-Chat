// Copyright NGGT.LightKeeper. All Rights Reserved.

import { deleteJson, getCsrfToken, getJson, patchJson } from './api.js';

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
    historyUi.clearActiveChat();
    dom.$messagesArea.show();
    attachmentUi.clearPendingAttachments();
    messagesUi.updateSendButtons();
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

      const payload = {
        engine: request.engine,
        message: request.text,
        model: selectedModel,
        system_prompt: request.systemPrompt,
        chat_id: request.chatId || state.currentChatId,
        options: request.options || {}
      };

      if (request.toolServerIds && request.toolServerIds.length > 0) {
        payload.tool_server_ids = request.toolServerIds;
      }

      const attachmentPayloads = await buildAttachmentPayloads(request.attachments);
      if (attachmentPayloads.length > 0) {
        payload.attachments = attachmentPayloads;
      }

      state.currentAbortController = new AbortController();
      const response = await fetch('/api/chat/', {
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
    } catch (error) {
      if (error.name !== 'AbortError') {
        $bubbleContent.html(`[Error: failed to connect to server - ${error.message}]`);
      }
    } finally {
      state.currentAbortController = null;
    }
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

    const $assistantRow = messagesUi.appendTyping();
    messagesUi.scrollBottom();

    try {
      await streamChat(request, $assistantRow);
    } finally {
      if ($assistantRow.find('.msg-actions').length === 0) {
        $assistantRow.find('.msg-body').append(context.icons.buildMessageActionsHtml());
      }

      messagesUi.updateRegenButtons();
      state.isChatGenerating = false;
      messagesUi.updateSendButtons();

      if (state.chatRequestQueue.length > 0) {
        processChatQueue();
      }
    }
  }


  // Request building.
  // Snapshot the current UI state into one queued chat request.
  function buildQueuedRequest(text, attachmentsToSend) {
    return {
      id: `queued-${++state.queuedMessageCounter}`,
      text,
      attachments: clonePendingAttachments(attachmentsToSend),
      engine: engineManager.getActiveEngine(),
      preferredModel: engineManager.getSelectedModelName(),
      systemPrompt: dom.$systemPrompt.val(),
      options: parametersUi.collectOptionsPayload(),
      toolServerIds: state.toolState.supported ? parametersUi.getSelectedToolServerIds() : [],
      chatId: state.currentChatId
    };
  }

  // Queue one user message for generation.
  function sendMessage(text, $input) {
    if (!text && state.attachmentState.pending.length === 0) {
      return;
    }

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

    fetch('/api/chat/abort/', {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrfToken() }
    }).catch(function ignoreAbortError() {});
  }

  // Queue a follow-up regeneration request.
  function queueRegenerationRequest(text, attachments) {
    const request = buildQueuedRequest(text, attachments);
    request.$userRow = { length: 0 };
    request.chatId = state.currentChatId;
    state.chatRequestQueue.push(request);
    processChatQueue();
  }


  // Regeneration helpers.
  // Delete the last assistant response and queue it again.
  async function doRegenerate() {
    if (!state.currentChatId) {
      return;
    }

    try {
      const data = await deleteJson(`/api/chat/${state.currentChatId}/last/`);
      if (!data.ok) {
        return;
      }

      const $assistantMessages = dom.$messagesInner.find('.msg.assistant');
      if ($assistantMessages.length) {
        $assistantMessages.last().remove();
      }

      messagesUi.updateSendButtons();

      if (!data.user_message) {
        return;
      }

      const text = data.user_message.content || '';
      const attachments = (data.user_message.attachments || [])
        .map(attachmentUi.normalizeAttachment)
        .filter(Boolean);

      queueRegenerationRequest(text, attachments);
    } catch (error) {
      console.error('Failed to delete last assistant message', error);
    }
  }

  // Regenerate the most recent assistant response.
  function regenerateLastResponse() {
    if (!state.currentChatId) {
      return;
    }

    if (state.isChatGenerating) {
      abortGeneration();
      setTimeout(function regenerateAfterAbort() {
        doRegenerate();
      }, 300);
      return;
    }

    doRegenerate();
  }

  // Regenerate the assistant response attached to one user row.
  async function regenerateFromUserMessage($userMsg) {
    if (!state.currentChatId || state.isChatGenerating) {
      return;
    }

    const userText = $userMsg.find('.msg-bubble').attr('data-raw') || $userMsg.find('.msg-bubble').text();
    if (!userText.trim()) {
      return;
    }

    const $nextAssistant = $userMsg.next('.msg.assistant');
    if (!$nextAssistant.length) {
      return;
    }

    const assistantMessageId = $nextAssistant.data('message-id');

    // Remove the rendered assistant row and rebuild the request from the
    // original user message stored in the DOM.
    function doUserRegen() {
      $nextAssistant.remove();
      messagesUi.updateRegenButtons();

      let userAttachments = [];

      try {
        const $bubble = $userMsg.find('.msg-bubble');
        const storedAttachments = $bubble.data('attachments');
        userAttachments = Array.isArray(storedAttachments)
          ? storedAttachments
          : JSON.parse($bubble.attr('data-attachments') || '[]');
      } catch (_error) {
        userAttachments = [];
      }

      queueRegenerationRequest(userText, userAttachments);
    }

    if (assistantMessageId) {
      try {
        const data = await deleteJson(`/api/message/${assistantMessageId}/delete/`);
        if (data.ok) {
          doUserRegen();
        }
      } catch (error) {
        console.error('Failed to delete assistant message for regen', assistantMessageId, error);
      }

      return;
    }

    doUserRegen();
  }


  // Composer wiring.
  // Bind one textarea and send button pair to the chat workflow.
  function wireInput($input, $button) {
    $input.on('input', function onInput() {
      this.style.height = 'auto';
      this.style.height = `${Math.min(this.scrollHeight, 200)}px`;
      messagesUi.updateSendButtons();
    });

    $input.on('keydown', function onKeyDown(event) {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();

        if (!$button.prop('disabled')) {
          sendMessage($input.val().trim(), $input);
        }
      }
    });

    $button.on('click', function onClick() {
      if (state.isChatGenerating && state.currentAbortController) {
        abortGeneration();
        return;
      }

      if (!$button.prop('disabled')) {
        sendMessage($input.val().trim(), $input);
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
            messageId: message.id
          }
        };
      });

      messagesUi.appendMessages(storedMessages);
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
    wireInput
  };
}
