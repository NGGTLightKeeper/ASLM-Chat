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
    currentChatId = null;
    $('#historyList .chat-item').removeClass('active');
    $messagesArea.show();
    clearPendingImages();
  }

  /* ── Vision / Image Attachment ───────────────────────────── */
  const visionState = {
    supported: false,
    // Array of { dataUrl, base64 } objects for pending images
    pending: []
  };

  function updateVisionControls() {
    const show = visionState.supported;
    $('#attachBtn').toggle(show);
    $('#attachBtnConv').toggle(show);
    $('#visionBadge').toggle(show);
    $('#visionBadgeConv').toggle(show);
  }

  function clearPendingImages() {
    visionState.pending = [];
    $('#imagePreviewStrip').empty().hide();
    $('#imagePreviewStripConv').empty().hide();
    // Reset file inputs so the same file can be selected again
    $('#imageInput').val('');
    $('#imageInputConv').val('');
  }

  function addImageToPreview(dataUrl, base64, $strip) {
    const idx = visionState.pending.push({ dataUrl, base64 }) - 1;
    const $thumb = $(`
      <div class="img-preview-thumb" data-idx="${idx}">
        <img src="${dataUrl}" alt="Attached image">
        <button class="img-preview-remove" aria-label="Remove image">
          <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>
    `);
    $strip.append($thumb).show();
    // Sync the other strip too
    const $otherStrip = $strip.is('#imagePreviewStrip') ? $('#imagePreviewStripConv') : $('#imagePreviewStrip');
    const $thumbCopy = $thumb.clone();
    $otherStrip.append($thumbCopy).show();
  }

  function rebuildPreviewStrips() {
    $('#imagePreviewStrip, #imagePreviewStripConv').empty();
    if (visionState.pending.length === 0) {
      $('#imagePreviewStrip, #imagePreviewStripConv').hide();
      return;
    }
    visionState.pending.forEach(function (img, idx) {
      const $thumb = $(`
        <div class="img-preview-thumb" data-idx="${idx}">
          <img src="${img.dataUrl}" alt="Attached image">
          <button class="img-preview-remove" aria-label="Remove image">
            <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
      `);
      $('#imagePreviewStrip, #imagePreviewStripConv').append($thumb.clone()).show();
    });
  }

  // Attach button → open file picker
  $(document).on('click', '#attachBtn', function () {
    $('#imageInput').trigger('click');
  });
  $(document).on('click', '#attachBtnConv', function () {
    $('#imageInputConv').trigger('click');
  });

  // File selected — read as DataURL and store base64 (max 20 images)
  function handleFileInput(e) {
    const MAX_IMAGES = 20;
    const files = Array.from(e.target.files);
    if (!files.length) return;
    files.forEach(function (file) {
      if (!file.type.startsWith('image/')) return;
      if (visionState.pending.length >= MAX_IMAGES) {
        console.warn(`Max ${MAX_IMAGES} images allowed`);
        return;
      }
      const reader = new FileReader();
      reader.onload = function (ev) {
        if (visionState.pending.length >= MAX_IMAGES) return;
        const dataUrl = ev.target.result;
        const base64 = dataUrl.split(',')[1];
        visionState.pending.push({ dataUrl, base64 });
        rebuildPreviewStrips();
      };
      reader.readAsDataURL(file);
    });
    $(e.target).val('');
  }

  $('#imageInput, #imageInputConv').on('change', handleFileInput);

  // Remove image from pending
  $(document).on('click', '.img-preview-remove', function (e) {
    e.stopPropagation();
    const idx = $(this).closest('.img-preview-thumb').data('idx');
    visionState.pending.splice(idx, 1);
    rebuildPreviewStrips();
  });

  /* ── Model Settings & Groupings ──────────────────────────── */
  const LLM_KNOWN_PARAMETERS = {
    // Settings Group
    'temperature': { label: 'Temperature', min: 0, max: 2, step: 0.1, decimals: 1, fallback: 0.8, group: '#group-settings .settings-section-content' },
    'num_ctx': { label: 'Max Tokens', min: 256, step: 256, decimals: 0, fallback: 2048, group: '#group-settings .settings-section-content' },
    // Sampling Group
    'top_p': { label: 'Top P', min: 0, max: 1, step: 0.05, decimals: 2, fallback: 0.9, group: '#group-sampling .settings-section-content' },
    'top_k': { label: 'Top K', min: 1, max: 100, step: 1, decimals: 0, fallback: 40, group: '#group-sampling .settings-section-content' },
    'presence_penalty': { label: 'Presence Penalty', min: -2, max: 2, step: 0.1, decimals: 1, fallback: 0.0, group: '#group-sampling .settings-section-content' },
    'frequency_penalty': { label: 'Frequency Penalty', min: -2, max: 2, step: 0.1, decimals: 1, fallback: 0.0, group: '#group-sampling .settings-section-content' }
  };

  function getParameterGroup(paramKey) {
    if (['temperature', 'num_ctx', 'num_predict', 'seed', 'num_keep'].includes(paramKey)) {
      return '#group-settings';
    } else if (['top_k', 'top_p', 'min_p', 'repeat_penalty', 'presence_penalty', 'frequency_penalty', 'mirostat', 'tfs_z', 'typical_p', 'repeat_last_n'].includes(paramKey)) {
      return '#group-sampling';
    } else if (['think', 'think_level', 'thinking', 'reasoning', 'thinking_level', 'reasoning_effort'].includes(paramKey)) {
      return '#group-custom';
    }
    return '#group-advanced';
  }

  // Accordion Toggles
  $(document).on('click', '.settings-section-header', function () {
    $(this).parent('.settings-section').toggleClass('collapsed');
  });

  /* ── Think state (shared between both input areas) ─────── */
  const thinkState = {
    supported: false,
    paramName: 'think',
    enabled: true,
    levelSupported: false,
    levelParamName: 'think_level',
    level: 'medium'
  };

  function updateThinkControls() {
    const pairs = [
      { $toggle: $('#thinkToggleBtn'), $levelSel: $('#thinkLevelSelector') },
      { $toggle: $('#thinkToggleBtnConv'), $levelSel: $('#thinkLevelSelectorConv') }
    ];

    pairs.forEach(function ({ $toggle, $levelSel }) {
      if (!thinkState.supported) {
        $toggle.hide();
        $levelSel.hide();
        return;
      }
      $toggle.show();
      $toggle.toggleClass('active', thinkState.enabled);

      if (thinkState.levelSupported && thinkState.enabled) {
        $levelSel.show();
        $levelSel.find('.think-level-btn').each(function () {
          $(this).toggleClass('active', $(this).data('value') === thinkState.level);
        });
      } else {
        $levelSel.hide();
      }
    });
  }

  // Think toggle click (both input areas via delegation)
  $(document).on('click', '.think-toggle-btn', function () {
    if (!thinkState.supported) return;
    thinkState.enabled = !thinkState.enabled;
    updateThinkControls();
  });

  // Think level button click
  $(document).on('click', '.think-level-btn', function () {
    thinkState.level = $(this).data('value');
    updateThinkControls();
  });

  $modelSelector.on('change', async function () {
    const model = $(this).val();
    if (!model) return;

    try {
      const response = await fetch(`/api/model_info/?model=${encodeURIComponent(model)}`);
      if (response.ok) {
        const data = await response.json();

        // Reset dynamic sidebar panels
        $('.settings-section').filter(function () { return this.id.startsWith('group-') && this.id !== 'group-system'; }).hide().find('.settings-section-content').empty();
        $('.settings-divider[id^="divider-"]').hide();

        // Update vision controls
        visionState.supported = !!data.supports_vision;
        updateVisionControls();
        // Clear pending images when switching models
        clearPendingImages();

        // Update think controls state
        thinkState.supported = !!data.supports_thinking;
        thinkState.paramName = data.think_param_name || 'think';
        thinkState.levelSupported = !!data.supports_think_level;
        thinkState.levelParamName = data.think_level_param_name || 'think_level';

        // Derive defaults from model data
        if (data.defaults && data.defaults[thinkState.paramName] !== undefined) {
          const raw = data.defaults[thinkState.paramName];
          thinkState.enabled = raw === true || String(raw).toLowerCase() === 'true';
        } else {
          thinkState.enabled = true;
        }
        if (data.defaults && data.defaults[thinkState.levelParamName] !== undefined) {
          thinkState.level = String(data.defaults[thinkState.levelParamName]);
        } else {
          thinkState.level = 'medium';
        }
        updateThinkControls();

        // Build Dynamic Parameters Sidebar UI
        if (data.defaults) {
          // Remove think params from defaults so they don't appear in sidebar
          delete data.defaults[thinkState.paramName];
          delete data.defaults[thinkState.levelParamName];

          // 1. Context Length needs special max handling
          LLM_KNOWN_PARAMETERS['num_ctx'].max = data.context_length || 131072;
          if (data.defaults['num_ctx'] !== undefined) {
            LLM_KNOWN_PARAMETERS['num_ctx'].fallback = data.defaults['num_ctx'];
          }

          // First pass: Known Parameters with fallbacks
          for (const [key, config] of Object.entries(LLM_KNOWN_PARAMETERS)) {
            const val = data.defaults[key] !== undefined ? data.defaults[key] : config.fallback;
            const valStr = Number(val).toFixed(config.decimals);

            const groupId = getParameterGroup(key);
            const $groupContent = $(`${groupId} .settings-section-content`);

            const html = `
                            <div class="setting-group">
                                <label class="setting-label" for="dyn_${key}">
                                    ${config.label}
                                    <span class="setting-value" id="val_${key}">${valStr}</span>
                                </label>
                                <input type="range" class="setting-range dyn-param" id="dyn_${key}" data-param="${key}" min="${config.min}" max="${config.max}" step="${config.step}" value="${val}">
                            </div>
                        `;
            $groupContent.append(html);
            $(groupId).show();

            $(document).on('input', `#dyn_${key}`, function () {
              $(`#val_${key}`).text(parseFloat(this.value).toFixed(config.decimals));
            });

            if (data.defaults[key] !== undefined) {
              delete data.defaults[key];
            }
          }

          if (data.defaults['num_predict'] !== undefined) delete data.defaults['num_predict'];

          // Second pass: Unknown experimental parameters
          const leftoverKeys = Object.keys(data.defaults);
          if (leftoverKeys.length > 0) {
            for (const key of leftoverKeys) {
              const val = data.defaults[key];
              if (typeof val === 'number') {
                const groupId = getParameterGroup(key);
                const $groupContent = $(`${groupId} .settings-section-content`);
                $(groupId).show();

                const html = `
                                <div class="setting-group">
                                    <label class="setting-label" for="dyn_${key}">
                                        ${key.replace(/_/g, ' ')}
                                    </label>
                                    <input type="number" class="setting-range dyn-param" id="dyn_${key}" data-param="${key}" value="${val}" style="width: 100%; border-radius: 4px; border: 1px solid #3A3A3C; padding: 6px; background: #2C2C2E; color: var(--text-primary); margin-top: 5px;">
                                </div>
                            `;
                $groupContent.append(html);
              }
            }
          }

          // Final layout adjustments: display dividers between *visible* groups
          let visibleCount = 0;
          ['#group-settings', '#group-sampling', '#group-advanced'].forEach(function (sel) {
            if ($(sel).is(':visible')) {
              visibleCount++;
              if (visibleCount > 1) {
                $(`#divider-${sel.replace('#group-', '')}`).show();
              }
            }
          });
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
    if (!text && visionState.pending.length === 0) return;

    // Capture images before clearing
    const imagesToSend = visionState.pending.slice();

    // Switch from welcome → conversation view
    if ($welcomeScreen.is(':visible')) {
      $welcomeScreen.hide();
      $conversationInput.show();
      $chatInputConv.val('').css('height', 'auto').trigger('input').focus();
    }

    appendMessage('user', text, imagesToSend);
    $input.val('').css('height', 'auto').trigger('input');
    clearPendingImages();

    // 2. Prepare assistant message bubble for streaming
    const $msgBubble = appendTyping();
    const $bubbleContent = $msgBubble.find('.msg-bubble');
    scrollBottom();

    // 3. Prepare options & send to API via Fetch for streaming
    async function streamChat() {
      try {
        // Build options dictionary dynamically from generated DOM
        const optionsPayload = {};
        $('#dynamicParameters .dyn-param').each(function () {
          const param = $(this).data('param');
          const val = parseFloat($(this).val());
          if (!isNaN(val)) {
            optionsPayload[param] = val;
          }
        });

        // Add think options from the input-area controls
        if (thinkState.supported) {
          optionsPayload[thinkState.paramName] = thinkState.enabled;
          if (thinkState.levelSupported) {
            optionsPayload[thinkState.levelParamName] = thinkState.level;
          }
        }

        const payload = {
          message: text,
          model: $modelSelector.val(),
          system_prompt: $('#systemPrompt').val(),
          chat_id: currentChatId,
          options: optionsPayload
        };

        // Attach images (base64 strings) if any
        if (imagesToSend.length > 0) {
          payload.images = imagesToSend.map(function (img) { return img.base64; });
        }

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
          // $bubbleContent.html(escHtml(fullText));   <-- Removed to let renderMessageHtml do the work

          // Only auto-scroll if user is near the bottom
          const area = $messagesArea[0];
          const isScrolledToBottom = area.scrollHeight - area.clientHeight <= area.scrollTop + 50;
          if (isScrolledToBottom) scrollBottom();

          const $row = $msgBubble.closest('.msg');
          renderMessageHtml($row, fullText);
        }

      } catch (err) {
        $msgBubble.removeClass('typing-indicator');
        $bubbleContent.html(`[Error: failed to connect to server - ${err.message}]`);
      }
    }

    streamChat();
  }

  /* ── Markdown & Message rendering ────────────────────────── */

  // Configure Marked to use Highlight.js
  if (typeof marked !== 'undefined' && typeof hljs !== 'undefined') {
    marked.setOptions({
      highlight: function (code, lang) {
        const language = hljs.getLanguage(lang) ? lang : 'plaintext';
        return hljs.highlight(code, { language }).value;
      },
      breaks: true
    });
  }

  function renderMessageHtml($msgRow, rawText) {
    const $thoughtsWrapper = $msgRow.find('.msg-thoughts-wrapper');
    const $thoughtsContent = $msgRow.find('.msg-thoughts-content');
    const $bubble = $msgRow.find('.msg-bubble');

    if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
      $bubble.html(escHtml(rawText));
      return;
    }

    let allThinkContent = '';
    let allMainContent = '';

    // We'll use simple indexOf parsing instead of regex loops which are fragile on unterminated strings
    let currentIndex = 0;

    while (true) {
      let thinkStart = rawText.indexOf('<think>', currentIndex);

      // No more <think> tags found, append the rest to main content
      if (thinkStart === -1) {
        allMainContent += rawText.substring(currentIndex);
        break;
      }

      // Append everything before <think> to main content
      allMainContent += rawText.substring(currentIndex, thinkStart);

      let thinkEnd = rawText.indexOf('</think>', thinkStart + 7);

      // If we found the closing tag
      if (thinkEnd !== -1) {
        allThinkContent += rawText.substring(thinkStart + 7, thinkEnd) + '\n';
        currentIndex = thinkEnd + 8; // Move past </think>
      } else {
        // Streaming / unterminated <think> block: the rest of the text is thoughts
        allThinkContent += rawText.substring(thinkStart + 7);
        break;
      }
    }

    // Update thoughts block separately so we don't destroy its toggle state
    if (allThinkContent.trim()) {
      $thoughtsWrapper.show();
      $thoughtsContent.text(allThinkContent.trim());
    } else {
      $thoughtsWrapper.hide();
    }

    // Render remaining text after any think blocks
    if (allMainContent.trim()) {
      $bubble.html(`<div class="markdown-body">${DOMPurify.sanitize(marked.parse(allMainContent))}</div>`);
    } else {
      $bubble.html('');
    }
  }

  // Handle custom expansion for reasoning blocks via event delegation
  $messagesInner.on('click', '.msg-thoughts-toggle', function (e) {
    e.stopPropagation();
    const $wrapper = $(this).closest('.msg-thoughts-wrapper');
    const $content = $wrapper.find('.msg-thoughts-content');

    $content.slideToggle(200);
    $wrapper.toggleClass('expanded');
  });

  function appendMessage(role, text, images) {
    const isUser = role === 'user';
    const label = isUser ? 'You' : 'ASLM';

    // Build images HTML for user messages.
    // images can be [{dataUrl, base64}, ...] (live) or ['data:...', ...] (from history)
    let imagesHtml = '';
    if (isUser && images && images.length > 0) {
      const imgs = images.map(function (img) {
        const src = (typeof img === 'string') ? img : img.dataUrl;
        return `<img src="${src}" alt="Attached image">`;
      }).join('');
      imagesHtml = `<div class="msg-images">${imgs}</div>`;
    }

    const $row = $(`
      <div class="msg ${role}">
        <div class="msg-avatar">${isUser ? 'U' : 'A'}</div>
        <div class="msg-body">
          <div class="msg-meta">
            <span>${label}</span>
            <span>${timeNow()}</span>
          </div>
          ${!isUser ? `
          <div class="msg-thoughts-wrapper" style="display:none;">
            <div class="msg-thoughts-toggle">Thought Process</div>
            <div class="msg-thoughts-content" style="display:none;"></div>
          </div>
          ` : ''}
          <div class="msg-bubble">${imagesHtml}</div>
        </div>
      </div>`);

    if (!isUser) {
      renderMessageHtml($row, text);
    } else {
      $row.find('.msg-bubble').append($('<span>').text(text));
    }

    $messagesInner.append($row);
    scrollBottom();
  }

  function appendTyping() {
    const $row = $(`
      <div class="msg assistant">
        <div class="msg-avatar">A</div>
        <div class="msg-body">
          <div class="msg-meta">
            <span>ASLM</span>
            <span>${timeNow()}</span>
          </div>
          <div class="msg-thoughts-wrapper" style="display:none;">
            <div class="msg-thoughts-toggle">Thought Process</div>
            <div class="msg-thoughts-content" style="display:none;"></div>
          </div>
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
            appendMessage(msg.role, msg.content, msg.images || []);
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
