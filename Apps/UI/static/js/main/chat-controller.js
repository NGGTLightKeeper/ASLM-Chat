// Copyright NGGT.LightKeeper. All Rights Reserved.

import { deleteJson, getCsrfToken, getJson, patchJson } from './api.js';

export function createChatController(context, dependencies) {
  const {
    attachmentUi,
    engineManager,
    historyUi,
    messagesUi,
    parametersUi
  } = dependencies;
  const { dom, state } = context;

  function buildChatTitle(text, hasAttachments) {
    if (text) {
      return text.substring(0, 40) + (text.length > 40 ? '...' : '');
    }
    return hasAttachments ? 'Attachment chat' : 'New Chat';
  }

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

  function clonePendingAttachments(attachments) {
    return (attachments || [])
      .map(attachmentUi.normalizeAttachment)
      .filter(Boolean);
  }

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

      if (request.attachments.length > 0) {
        payload.attachments = request.attachments.map(function toPayload(attachment) {
          return {
            kind: attachment.kind,
            name: attachment.name,
            mime_type: attachment.mimeType,
            size_bytes: attachment.size,
            data: attachment.base64
          };
        });
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

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let fullText = '';
      const signal = state.currentAbortController ? state.currentAbortController.signal : null;

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

          const area = dom.$messagesArea[0];
          const isNearBottom = area.scrollHeight - area.clientHeight <= area.scrollTop + 50;
          messagesUi.renderMessageHtml($msgRow, fullText);

          if (isNearBottom) {
            messagesUi.scrollBottom();
          }
        }
      } catch (readError) {
        if (readError.name !== 'AbortError') {
          throw readError;
        }
      } finally {
        reader.cancel();
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

  function queueRegenerationRequest(text, attachments) {
    const request = buildQueuedRequest(text, attachments);
    request.$userRow = { length: 0 };
    request.chatId = state.currentChatId;
    state.chatRequestQueue.push(request);
    processChatQueue();
  }

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

    function doUserRegen() {
      $nextAssistant.remove();
      messagesUi.updateRegenButtons();

      let userAttachments = [];
      try {
        userAttachments = JSON.parse($userMsg.find('.msg-bubble').attr('data-attachments') || '[]');
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

      data.messages.forEach(function appendStoredMessage(message) {
        messagesUi.appendMessage(
          message.role,
          message.content,
          (message.attachments || message.images || []).map(attachmentUi.normalizeAttachment).filter(Boolean),
          message.created_at,
          {
            activitySegments: Array.isArray(message.activity_segments) ? message.activity_segments : [],
            messageId: message.id
          }
        );
      });

      messagesUi.scrollBottom();
    } catch (error) {
      console.error('Failed to load chat history:', error);
    }
  }

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
