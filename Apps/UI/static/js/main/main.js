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
  }

  /* ── Model Selector ──────────────────────────────────────── */
  $modelSelector.on('change', function () {
    // Placeholder – will call API in future
    console.log('Model selected:', $(this).val());
  });


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
      $chatInputConv.trigger('input');
    }

    appendMessage('user', text);
    $input.val('').css('height', 'auto').trigger('input');

    const $typing = appendTyping();
    scrollBottom();

    $.ajax({
      url: '/api/chat/',
      method: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({
        message: text,
        model: $modelSelector.val()
      }),
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
      success: function (data) {
        $typing.remove();
        appendMessage('assistant', data.reply || '');
        scrollBottom();
      },
      error: function () {
        $typing.remove();
        appendMessage('assistant', '[Error: could not reach the model]');
        scrollBottom();
      }
    });
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

  function getCookie(name) {
    const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : null;
  }

});
