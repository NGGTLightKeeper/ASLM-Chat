'use strict';

$(function () {

  /* ── DOM ─────────────────────────────────────────────────── */
  const $newChatBtn = $('#newChatBtn');
  const $historyList = $('#historyList');
  const $chatTitle = $('#chatTitle');
  const $messagesArea = $('#messagesArea');
  const $messagesInner = $('#messagesInner');
  const $welcomeScreen = $('#welcomeScreen');
  const $chatInput = $('#chatInput');
  const $sendBtn = $('#sendBtn');
  const $chatInputConv = $('#chatInputConv');
  const $sendBtnConv = $('#sendBtnConv');
  const $conversationInput = $('#conversationInput');
  const $modelSelector = $('#modelSelector');

  // Tracking current active chat
  let currentChatId = null;

  /* ── New Chat ────────────────────────────────────────────── */
  $newChatBtn.on('click', function (e) {
    e.preventDefault();
    startNewChat();
  });

  function startNewChat() {
    $chatTitle.text('New Chat');
    $messagesInner.find('.msg').remove();
    $conversationInput.hide();
    $welcomeScreen.show();
    $chatInput.val('').css('height', 'auto').trigger('input').focus();
    currentChatId = null; // Reset current chat ID
    $('#historyList .chat-item').removeClass('active'); // Deactivate all history items
    $messagesArea.show(); // Ensure messages area is visible
  }

  /* ── Model Selector ──────────────────────────────────────── */
  $modelSelector.on('change', async function () {
    const model = $(this).val();
    if (!model) return;

    try {
      const response = await fetch(`/api/model_info/?model=${encodeURIComponent(model)}`);
      if (response.ok) {
        const data = await response.json();
        if (data.context_length) {
          const $maxTokensInput = $('#maxTokens');
          const $maxTokensValue = $('#maxTokensValue');

          // Set the new max capability
          $maxTokensInput.attr('max', data.context_length);

          // Set the default if it exists, otherwise just clamp
          if (data.defaults && data.defaults.num_ctx) {
            $maxTokensInput.val(data.defaults.num_ctx);
            $maxTokensValue.text(data.defaults.num_ctx);
          } else {
            const currentVal = parseInt($maxTokensInput.val(), 10);
            if (currentVal > data.context_length) {
              $maxTokensInput.val(data.context_length);
              $maxTokensValue.text(data.context_length);
            }
          }
        }

        // Map parsed defaults to the sliders
        if (data.defaults) {
          const mapping = {
            'temperature': { id: '#temperature', valId: '#temperatureValue', decimals: 1 },
            'top_p': { id: '#topP', valId: '#topPValue', decimals: 2 },
            'top_k': { id: '#topK', valId: '#topKValue', decimals: 0 },
            'presence_penalty': { id: '#presencePenalty', valId: '#presencePenaltyValue', decimals: 1 },
            'frequency_penalty': { id: '#frequencyPenalty', valId: '#frequencyPenaltyValue', decimals: 1 }
          };

          for (const [key, mappingData] of Object.entries(mapping)) {
            if (data.defaults[key] !== undefined) {
              const val = data.defaults[key];
              $(mappingData.id).val(val);
              $(mappingData.valId).text(Number(val).toFixed(mappingData.decimals));
            }
          }
        }
      }
    } catch (err) {
      console.error("Failed to load model parameters", err);
    }
  });

  // Trigger it once on load to configure the default selected model
  if ($modelSelector.val()) {
    $modelSelector.trigger('change');
  }


  /* ── Input wiring ────────────────────────────────────────── */
  function wireInput($input, $btn) {
    $input.on('input', function () {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 200) + 'px';
      $btn.prop('disabled', !this.value.trim());
    });

    $input.on('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!$btn.prop('disabled')) sendMessage($input.val().trim(), $input);
      }
    });

    $btn.on('click', function () {
      if (!$btn.prop('disabled')) sendMessage($input.val().trim(), $input);
    });
  }

  wireInput($chatInput, $sendBtn);
  wireInput($chatInputConv, $sendBtnConv);

  /* ── Send / Receive ──────────────────────────────────────── */
  function sendMessage(text, $input) {
    if (!text) return;

    // Switch from welcome → conversation view
    if ($welcomeScreen.is(':visible')) {
      $welcomeScreen.hide();
      $conversationInput.show();
      $chatInputConv.val('').css('height', 'auto').trigger('input').focus();
    }

    appendMessage('user', text);
    $input.val('').css('height', 'auto').trigger('input');

    // 2. Prepare assistant message bubble for streaming
    const $msgBubble = appendTyping();
    const $bubbleContent = $msgBubble.find('.msg-bubble');
    scrollBottom();

    // 3. Prepare options & send to API via Fetch for streaming
    async function streamChat() {
      try {
        const payload = {
          message: text,
          model: $modelSelector.val(),
          system_prompt: $('#systemPrompt').val(),
          chat_id: currentChatId,
          options: {
            temperature: parseFloat($('#temperature').val()),
            num_ctx: parseInt($('#maxTokens').val(), 10),
            top_p: parseFloat($('#topP').val()),
            top_k: parseInt($('#topK').val(), 10),
            presence_penalty: parseFloat($('#presencePenalty').val()),
            frequency_penalty: parseFloat($('#frequencyPenalty').val())
          }
        };

        const response = await fetch('/api/chat/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
          },
          body: JSON.stringify(payload)
        });

        // Remove typing indicator immediately once request is resolved
        $msgBubble.removeClass('typing-indicator');
        $bubbleContent.empty(); // clear the dots

        if (!response.ok) {
          try {
            const errData = await response.json();
            $bubbleContent.html(`[Error: ${errData.error || 'Server error'}]`);
          } catch (e) {
            $bubbleContent.html(`[Error: ${response.status} ${response.statusText}]`);
          }
          return;
        }

        // Process Chat ID header
        const returnedChatId = response.headers.get('X-Chat-ID');
        if (returnedChatId && currentChatId !== returnedChatId) {
          currentChatId = returnedChatId;

          // Check if we already have it in sidebar to avoid duplicates
          if ($(`#historyList .chat-item[data-chat-id="${currentChatId}"]`).length === 0) {
            $('#historyList .empty-state').remove();

            // Add new chat to the top of the history list
            const title = text.substring(0, 30) + (text.length > 30 ? '...' : '');
            const $newItem = $(`
                <div class="chat-item active" data-chat-id="${currentChatId}">
                    <span class="chat-title">${escHtml(title)}</span>
                </div>
            `);

            $('#historyList .chat-item').removeClass('active');
            $('#historyList').prepend($newItem);
          }
        }

        // Stream reader
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let fullText = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          fullText += chunk;

          // Re-encode HTML and parse newlines so it renders nicely in the div
          $bubbleContent.html(escHtml(fullText));

          // Only auto-scroll if user is near the bottom
          const area = $messagesArea[0];
          const isScrolledToBottom = area.scrollHeight - area.clientHeight <= area.scrollTop + 50;
          if (isScrolledToBottom) scrollBottom();
        }

      } catch (err) {
        $msgBubble.removeClass('typing-indicator');
        $bubbleContent.html(`[Error: failed to connect to server - ${err.message}]`);
      }
    }

    streamChat();
  }

  /* ── Message rendering ───────────────────────────────────── */
  function appendMessage(role, text) {
    const isUser = role === 'user';
    const label = isUser ? 'You' : 'ASLM';
    const $row = $(`
      <div class="msg ${role}">
        <div class="msg-avatar">${isUser ? 'U' : 'A'}</div>
        <div class="msg-body">
          <div class="msg-meta">
            <span>${label}</span>
            <span>${timeNow()}</span>
          </div>
          <div class="msg-bubble">${escHtml(text)}</div>
        </div>
      </div>`);
    $messagesInner.append($row);
    scrollBottom();
  }

  function appendTyping() {
    const $row = $(`
      <div class="msg assistant">
        <div class="msg-avatar">A</div>
        <div class="msg-body">
          <div class="msg-bubble">
            <div class="typing-indicator">
              <div class="typing-dot"></div>
              <div class="typing-dot"></div>
              <div class="typing-dot"></div>
            </div>
          </div>
        </div>
      </div>`);
    $messagesInner.append($row);
    return $row;
  }

  function scrollBottom() {
    $messagesArea.scrollTop($messagesArea[0].scrollHeight);
  }

  /* ── Model Settings sliders ──────────────────────────────── */
  const sliders = [
    { id: '#temperature', valueId: '#temperatureValue', decimals: 1 },
    { id: '#maxTokens', valueId: '#maxTokensValue', decimals: 0 },
    { id: '#topP', valueId: '#topPValue', decimals: 2 },
    { id: '#topK', valueId: '#topKValue', decimals: 0 },
    { id: '#presencePenalty', valueId: '#presencePenaltyValue', decimals: 1 },
    { id: '#frequencyPenalty', valueId: '#frequencyPenaltyValue', decimals: 1 },
  ];

  sliders.forEach(function (s) {
    const $slider = $(s.id);
    const $val = $(s.valueId);
    $slider.on('input', function () {
      $val.text(parseFloat(this.value).toFixed(s.decimals));
    });
  });

  /* ── Chat Switching History ───────────────────────────────────────────── */
  $(document).on('click', '#historyList .chat-item', function () {
    const chatId = $(this).data('chat-id');
    if (!chatId || currentChatId === chatId) return;

    // Update UI selection
    $('#historyList .chat-item').removeClass('active');
    $(this).addClass('active');

    // Load historical chats
    $.ajax({
      url: `/api/chat/${chatId}/`,
      method: 'GET',
      success: function (data) {
        if (data.messages) {
          currentChatId = chatId;

          // Clear current view
          $messagesInner.find('.msg').remove();
          $welcomeScreen.hide();
          $messagesArea.show();
          $conversationInput.show();

          // Append historical messages
          data.messages.forEach(msg => {
            appendMessage(msg.role, msg.content);
          });

          scrollBottom();
        }
      },
      error: function (err) {
        console.error("Failed to load chat history:", err);
      }
    });
  });

  // Handling 'New Chat' click
  $newChatBtn.on('click', function (e) {
    if ($(this).attr('href') === '/') {
      // If we're on the main view, just reset UI instead of full reload.
      e.preventDefault();
      startNewChat();
    }
  });

  /* ── Utilities ───────────────────────────────────────────── */
  function timeNow() {
    return new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  }

  function escHtml(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n/g, '<br>');
  }

  function getCsrfToken() {
    // Read directly from the DOM element generated by {% csrf_token %}
    const tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
    if (tokenInput) {
      return tokenInput.value;
    }
    // Fallback exactly as before just in case
    return getCookie('csrftoken');
  }

  function getCookie(name) {
    const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : null;
  }

});
