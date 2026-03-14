'use strict';

$(function () {
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
  const $engineSelector = $('#engineSelector');
  const $engineAddressGroup = $('#engineAddressGroup');
  const $engineAddressInput = $('#engineAddressInput');
  const $engineAddressStatus = $('#engineAddressStatus');
  const $engineAddressHint = $('#engineAddressHint');
  const $engineApiKeyGroup = $('#engineApiKeyGroup');
  const $engineApiKeyEnabled = $('#engineApiKeyEnabled');
  const $engineApiKeyInput = $('#engineApiKeyInput');
  const $engineApiKeyStatus = $('#engineApiKeyStatus');
  const $modelSelector = $('#modelSelector');

  let runtimeSettings = parseJsonScript('runtimeSettingsData') || {};
  let currentChatId = null;
  let engineSelectionVersion = 0;
  let activeEngine = 'ollama-service';

  const ENGINE_ALIASES = {
    ollama: 'ollama-service',
    'ollama-service': 'ollama-service',
    lms: 'lms',
    'lm-studio': 'lms',
    openai: 'openai',
    'openai-api': 'openai'
  };

  const ENGINE_ADDRESS_KEYS = {
    lms: 'lms_url',
    openai: 'openai_url'
  };

  const ENGINE_ADDRESS_HINTS = {
    'ollama-service': 'Ollama uses the local service managed by ASLM.',
    lms: 'Example: http://127.0.0.1:1234',
    openai: 'Example: http://127.0.0.1:8000/v1'
  };

  activeEngine = normalizeEngineValue(
    runtimeSettings['llm-engine'] || $('body').data('llm-engine') || 'ollama-service'
  );

  const visionState = {
    supported: false,
    pending: []
  };

  const thinkState = {
    supported: false,
    paramName: 'think',
    enabled: true,
    levelSupported: false,
    levelParamName: 'think_level',
    level: 'medium'
  };

  const LLM_KNOWN_PARAMETERS = {
    temperature: {
      label: 'Temperature',
      min: 0,
      max: 2,
      step: 0.1,
      decimals: 1,
      fallback: 0.8
    },
    num_ctx: {
      label: 'Max Tokens',
      min: 256,
      max: 131072,
      step: 256,
      decimals: 0,
      fallback: 2048
    },
    top_p: {
      label: 'Top P',
      min: 0,
      max: 1,
      step: 0.05,
      decimals: 2,
      fallback: 0.9
    },
    top_k: {
      label: 'Top K',
      min: 1,
      max: 100,
      step: 1,
      decimals: 0,
      fallback: 40
    },
    presence_penalty: {
      label: 'Presence Penalty',
      min: -2,
      max: 2,
      step: 0.1,
      decimals: 1,
      fallback: 0.0
    },
    frequency_penalty: {
      label: 'Frequency Penalty',
      min: -2,
      max: 2,
      step: 0.1,
      decimals: 1,
      fallback: 0.0
    }
  };

  const LLM_PARAMETER_OPTION_SETS = {
    reasoning_effort: ['minimal', 'low', 'medium', 'high'],
    think_level: ['low', 'medium', 'high'],
    thinking_level: ['low', 'medium', 'high'],
    verbosity: ['low', 'medium', 'high']
  };

  function parseJsonScript(id) {
    const element = document.getElementById(id);
    if (!element) {
      return null;
    }

    try {
      return JSON.parse(element.textContent);
    } catch (_error) {
      return null;
    }
  }

  function normalizeEngineValue(engine) {
    const normalized = String(engine || '').trim().toLowerCase();
    return ENGINE_ALIASES[normalized] || normalized || 'ollama-service';
  }

  function getEngineAddressKey(engine) {
    return ENGINE_ADDRESS_KEYS[normalizeEngineValue(engine)] || null;
  }

  function getEngineAddress(engine) {
    const key = getEngineAddressKey(engine);
    return key ? (runtimeSettings[key] || '') : '';
  }

  function setEngineAddressStatus(text, state) {
    $engineAddressStatus.text(text || '');
    $engineAddressStatus.removeClass('is-pending is-error');

    if (state) {
      $engineAddressStatus.addClass(`is-${state}`);
    }
  }

  function setEngineApiKeyStatus(text, state) {
    $engineApiKeyStatus.text(text || '');
    $engineApiKeyStatus.removeClass('is-pending is-error');

    if (state) {
      $engineApiKeyStatus.addClass(`is-${state}`);
    }
  }

  function getActiveEngine() {
    return activeEngine;
  }

  function updateEngineAddressUi() {
    const engine = getActiveEngine();
    const addressKey = getEngineAddressKey(engine);
    const hasEditableAddress = Boolean(addressKey);
    const hasApiKeySupport = engine === 'openai';
    const hasStoredApiKey = hasApiKeySupport && !!runtimeSettings.has_openai_api_key;

    $engineAddressGroup.toggle(hasEditableAddress);
    $engineAddressHint.text(ENGINE_ADDRESS_HINTS[engine] || 'Configure the selected engine endpoint.');
    $engineApiKeyGroup.toggle(hasApiKeySupport);

    if (!hasEditableAddress) {
      setEngineAddressStatus('Managed', null);
    } else {
      $engineAddressInput.val(getEngineAddress(engine));
      setEngineAddressStatus('Saved', null);
    }

    if (!hasApiKeySupport) {
      $engineApiKeyEnabled.prop('checked', false);
      $engineApiKeyInput.val('').hide();
      setEngineApiKeyStatus('Disabled', null);
      return;
    }

    $engineApiKeyEnabled.prop('checked', hasStoredApiKey);
    $engineApiKeyInput.val('');
    $engineApiKeyInput.toggle(hasStoredApiKey);
    $engineApiKeyInput.attr(
      'placeholder',
      hasStoredApiKey ? 'Stored API key. Enter a new one to replace it' : 'Enter a new API key'
    );
    setEngineApiKeyStatus(hasStoredApiKey ? 'Saved' : 'Disabled', null);
  }

  function renderModelOptions(models, preferredModel) {
    const uniqueModels = Array.from(new Set(models || []));
    const fallbackModel = uniqueModels[0] || '';
    const selectedModel = uniqueModels.includes(preferredModel) ? preferredModel : fallbackModel;

    $modelSelector.empty();

    if (!uniqueModels.length) {
      $modelSelector.append('<option value="">No models available</option>');
      return '';
    }

    uniqueModels.forEach(function (modelName) {
      const $option = $('<option>').val(modelName).text(modelName);
      if (modelName === selectedModel) {
        $option.prop('selected', true);
      }
      $modelSelector.append($option);
    });

    return selectedModel;
  }

  async function fetchModelsForEngine(engine) {
    const response = await fetch(`/api/models/?engine=${encodeURIComponent(engine)}`);
    if (!response.ok) {
      throw new Error(`Failed to load models: ${response.status}`);
    }
    const data = await response.json();
    return data.models || [];
  }

  async function saveRuntimeSettings(patch) {
    const response = await fetch('/api/runtime_settings/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify(patch)
    });

    if (!response.ok) {
      const errorData = await response.json().catch(function () {
        return {};
      });
      throw new Error(errorData.error || `Failed to save settings: ${response.status}`);
    }

    runtimeSettings = await response.json();
    return runtimeSettings;
  }

  async function refreshModelsForEngine(engine, preferredModel, modelsOverride, selectionVersion) {
    const hasModelOverride = Array.isArray(modelsOverride) && modelsOverride.length > 0;
    const models = hasModelOverride ? modelsOverride : await fetchModelsForEngine(engine);

    if (selectionVersion && selectionVersion !== engineSelectionVersion) {
      return '';
    }

    const selectedModel = renderModelOptions(models, preferredModel);

    if (selectionVersion && selectionVersion !== engineSelectionVersion) {
      return selectedModel;
    }

    await loadModelInfo(selectedModel);
    return selectedModel;
  }

  async function applyEngineSelection(engine, options) {
    const settingsOptions = options || {};
    const normalizedEngine = normalizeEngineValue(engine);
    const selectionVersion = ++engineSelectionVersion;
    let availableModels = null;
    activeEngine = normalizedEngine;

    if (settingsOptions.persist !== false) {
      runtimeSettings = await saveRuntimeSettings({ 'llm-engine': normalizedEngine });
      runtimeSettings['llm-engine'] = normalizedEngine;
      activeEngine = normalizedEngine;
      $('body').data('llm-engine', normalizedEngine);
      availableModels = Array.isArray(runtimeSettings.models) && runtimeSettings.models.length > 0
        ? runtimeSettings.models
        : null;
    } else {
      runtimeSettings['llm-engine'] = normalizedEngine;
      activeEngine = normalizedEngine;
      $('body').data('llm-engine', normalizedEngine);
      availableModels = Array.isArray(runtimeSettings.models) && runtimeSettings.models.length > 0
        ? runtimeSettings.models
        : null;
    }

    if (selectionVersion !== engineSelectionVersion) {
      return;
    }

    $engineSelector.val(activeEngine);
    updateEngineAddressUi();
    await refreshModelsForEngine(
      activeEngine,
      settingsOptions.preferredModel || '',
      availableModels,
      selectionVersion
    );
  }

  function buildChatTitle(text, hasImages) {
    if (text) {
      return text.substring(0, 40) + (text.length > 40 ? '...' : '');
    }
    return hasImages ? 'Image chat' : 'New Chat';
  }

  function updateSendButtons() {
    const hasPendingImages = visionState.pending.length > 0;
    $sendBtn.prop('disabled', !$chatInput.val().trim() && !hasPendingImages);
    $sendBtnConv.prop('disabled', !$chatInputConv.val().trim() && !hasPendingImages);
  }

  function startNewChat() {
    $chatTitle.text('New Chat');
    document.title = 'ASLM Chat';
    $messagesInner.find('.msg').remove();
    $conversationInput.hide();
    $welcomeScreen.show();
    $chatInput.val('').css('height', 'auto').focus();
    $chatInputConv.val('').css('height', 'auto');
    currentChatId = null;
    $('#historyList .chat-item').removeClass('active').removeAttr('aria-current');
    $messagesArea.show();
    clearPendingImages();
    updateSendButtons();
  }

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
    $('#imageInput').val('');
    $('#imageInputConv').val('');
    updateSendButtons();
  }

  function rebuildPreviewStrips() {
    const $strips = $('#imagePreviewStrip, #imagePreviewStripConv');
    $strips.empty();

    if (visionState.pending.length === 0) {
      $strips.hide();
      updateSendButtons();
      return;
    }

    visionState.pending.forEach(function (img, idx) {
      const html = `
        <div class="img-preview-thumb" data-idx="${idx}">
          <img src="${img.dataUrl}" alt="Attached image">
          <button class="img-preview-remove" aria-label="Remove image">
            <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
      `;
      $strips.append(html);
    });

    $strips.show();
    updateSendButtons();
  }

  function handleFileInput(event) {
    const maxImages = 20;
    const files = Array.from(event.target.files || []);
    if (!files.length) {
      return;
    }

    files.forEach(function (file) {
      if (!file.type.startsWith('image/')) {
        return;
      }
      if (visionState.pending.length >= maxImages) {
        console.warn(`Max ${maxImages} images allowed`);
        return;
      }

      const reader = new FileReader();
      reader.onload = function (loadEvent) {
        if (visionState.pending.length >= maxImages) {
          return;
        }

        const dataUrl = loadEvent.target.result;
        const base64 = dataUrl.split(',')[1];
        visionState.pending.push({ dataUrl, base64 });
        rebuildPreviewStrips();
      };
      reader.readAsDataURL(file);
    });

    $(event.target).val('');
  }

  function getParameterGroup(paramKey) {
    if (['temperature', 'num_ctx', 'num_predict', 'seed', 'num_keep'].includes(paramKey)) {
      return '#group-settings';
    }
    if (['top_k', 'top_p', 'min_p', 'repeat_penalty', 'presence_penalty', 'frequency_penalty', 'mirostat', 'tfs_z', 'typical_p', 'repeat_last_n'].includes(paramKey)) {
      return '#group-sampling';
    }
    if (['think', 'think_level', 'thinking', 'reasoning', 'thinking_level', 'reasoning_effort'].includes(paramKey)) {
      return '#group-custom';
    }
    return '#group-advanced';
  }

  function inferExperimentalParameterType(key, value) {
    if (typeof value === 'boolean') {
      return 'boolean';
    }

    if (typeof value === 'number') {
      return Number.isInteger(value) ? 'integer' : 'number';
    }

    if (Array.isArray(value) || (value && typeof value === 'object')) {
      return 'json';
    }

    if (typeof value === 'string' && LLM_PARAMETER_OPTION_SETS[key]) {
      return 'select';
    }

    return 'string';
  }

  function formatExperimentalParameterLabel(key) {
    return key
      .replace(/[_-]+/g, ' ')
      .replace(/\b\w/g, function (letter) {
        return letter.toUpperCase();
      });
  }

  function resetDynamicPanels() {
    $('.settings-section').filter(function () {
      return this.id.startsWith('group-')
        && this.id !== 'group-connection'
        && this.id !== 'group-system'
        && this.id !== 'group-model';
    }).hide().find('.settings-section-content').empty();

    $('.settings-divider[id^="divider-"]').not('#divider-connection').hide();
  }

  function renderKnownParameter(key, config, value) {
    const groupId = getParameterGroup(key);
    const $group = $(groupId);
    const $content = $(`${groupId} .settings-section-content`);
    const numericValue = Number(value);

    const html = `
      <div class="setting-group">
        <label class="setting-label" for="dyn_${key}">
          ${config.label}
          <input
            type="number"
            class="setting-number"
            id="val_${key}"
            data-param="${key}"
            data-decimals="${config.decimals}"
            value="${numericValue.toFixed(config.decimals)}"
            min="${config.min}"
            max="${config.max}"
            step="${config.step}">
        </label>
        <input
          type="range"
          class="setting-range dyn-param"
          id="dyn_${key}"
          data-param="${key}"
          data-decimals="${config.decimals}"
          min="${config.min}"
          max="${config.max}"
          step="${config.step}"
          value="${numericValue}">
      </div>
    `;

    $content.append(html);
    $group.show();
  }

  function renderExperimentalParameter(key, value) {
    const groupId = getParameterGroup(key);
    const $group = $(groupId);
    const $content = $(`${groupId} .settings-section-content`);
    const valueType = inferExperimentalParameterType(key, value);
    const label = formatExperimentalParameterLabel(key);
    let controlHtml = '';

    if (valueType === 'boolean') {
      controlHtml = `
        <select
          class="model-selector setting-select dyn-param"
          id="dyn_${key}"
          data-param="${key}"
          data-value-type="boolean">
          <option value="true"${value ? ' selected' : ''}>True</option>
          <option value="false"${!value ? ' selected' : ''}>False</option>
        </select>
      `;
    } else if (valueType === 'select') {
      const options = LLM_PARAMETER_OPTION_SETS[key] || [];
      controlHtml = `
        <select
          class="model-selector setting-select dyn-param"
          id="dyn_${key}"
          data-param="${key}"
          data-value-type="string">
          ${options.map(function (optionValue) {
            return `<option value="${optionValue}"${optionValue === value ? ' selected' : ''}>${formatExperimentalParameterLabel(optionValue)}</option>`;
          }).join('')}
        </select>
      `;
    } else if (valueType === 'json') {
      controlHtml = `
        <textarea
          class="setting-textarea dyn-param"
          id="dyn_${key}"
          data-param="${key}"
          data-value-type="json"
          rows="4">${escapeTextareaValue(JSON.stringify(value, null, 2))}</textarea>
      `;
    } else {
      const inputType = valueType === 'string' ? 'text' : 'number';
      controlHtml = `
        <input
          type="${inputType}"
          class="setting-input dyn-param"
          id="dyn_${key}"
          data-param="${key}"
          data-value-type="${valueType}"
          value="${escapeAttributeValue(String(value ?? ''))}">
      `;
    }

    const html = `
      <div class="setting-group">
        <label class="setting-label" for="dyn_${key}">
          ${label}
        </label>
        ${controlHtml}
      </div>
    `;

    $content.append(html);
    $group.show();
  }

  function updateVisibleDividers() {
    let visibleCount = 0;
    ['#group-custom', '#group-settings', '#group-sampling', '#group-advanced'].forEach(function (selector) {
      if ($(selector).is(':visible')) {
        visibleCount += 1;
        if (visibleCount > 1) {
          $(`#divider-${selector.replace('#group-', '')}`).show();
        }
      }
    });
  }

  function updateThinkControls() {
    [
      { $toggle: $('#thinkToggleBtn'), $selector: $('#thinkLevelSelector') },
      { $toggle: $('#thinkToggleBtnConv'), $selector: $('#thinkLevelSelectorConv') }
    ].forEach(function (pair) {
      if (!thinkState.supported) {
        pair.$toggle.hide();
        pair.$selector.hide();
        return;
      }

      pair.$toggle.show().toggleClass('active', thinkState.enabled);

      if (thinkState.levelSupported && thinkState.enabled) {
        pair.$selector.show();
        pair.$selector.find('.think-level-btn').each(function () {
          $(this).toggleClass('active', $(this).data('value') === thinkState.level);
        });
      } else {
        pair.$selector.hide();
      }
    });
  }

  async function loadModelInfo(model) {
    if (!model) {
      resetDynamicPanels();
      visionState.supported = false;
      thinkState.supported = false;
      updateVisionControls();
      updateThinkControls();
      return;
    }

    try {
      const response = await fetch(`/api/model_info/?engine=${encodeURIComponent(getActiveEngine())}&model=${encodeURIComponent(model)}`);
      if (!response.ok) {
        throw new Error(`Failed to load model info: ${response.status}`);
      }

      const data = await response.json();
      resetDynamicPanels();

      visionState.supported = !!data.supports_vision;
      updateVisionControls();
      clearPendingImages();

      thinkState.supported = !!data.supports_thinking;
      thinkState.paramName = data.think_param_name || 'think';
      thinkState.levelSupported = !!data.supports_think_level;
      thinkState.levelParamName = data.think_level_param_name || 'think_level';
      thinkState.enabled = data.defaults && data.defaults[thinkState.paramName] !== undefined
        ? String(data.defaults[thinkState.paramName]).toLowerCase() === 'true' || data.defaults[thinkState.paramName] === true
        : true;
      thinkState.level = data.defaults && data.defaults[thinkState.levelParamName] !== undefined
        ? String(data.defaults[thinkState.levelParamName])
        : 'medium';
      updateThinkControls();

      if (!data.defaults) {
        return;
      }

      const defaults = { ...data.defaults };
      delete defaults[thinkState.paramName];
      delete defaults[thinkState.levelParamName];

      if (defaults.num_ctx !== undefined) {
        LLM_KNOWN_PARAMETERS.num_ctx.max = data.context_length || 131072;
        LLM_KNOWN_PARAMETERS.num_ctx.fallback = defaults.num_ctx;
      }

      Object.entries(LLM_KNOWN_PARAMETERS).forEach(function ([key, config]) {
        const value = defaults[key] !== undefined ? defaults[key] : config.fallback;
        renderKnownParameter(key, config, value);
        delete defaults[key];
      });

      delete defaults.num_predict;

      Object.entries(defaults).forEach(function ([key, value]) {
        if (value !== undefined && value !== null) {
          renderExperimentalParameter(key, value);
        }
      });

      updateVisibleDividers();
    } catch (error) {
      console.error('Failed to load model parameters', error);
    }
  }

  function collectOptionsPayload() {
    const payload = {};
    $('#dynamicParameters .dyn-param').each(function () {
      const param = $(this).data('param');
      const valueType = $(this).data('value-type') || 'number';
      const rawValue = $(this).val();

      if (valueType === 'boolean') {
        payload[param] = String(rawValue).toLowerCase() === 'true';
        return;
      }

      if (valueType === 'json') {
        try {
          payload[param] = JSON.parse(rawValue);
        } catch (_error) {
          payload[param] = rawValue;
        }
        return;
      }

      if (valueType === 'integer') {
        const integerValue = parseInt(rawValue, 10);
        if (!Number.isNaN(integerValue)) {
          payload[param] = integerValue;
        }
        return;
      }

      if (valueType === 'number') {
        const numericValue = parseFloat(rawValue);
        if (!Number.isNaN(numericValue)) {
          payload[param] = numericValue;
        }
        return;
      }

      if (rawValue !== '') {
        payload[param] = rawValue;
      }
    });

    if (thinkState.supported) {
      payload[thinkState.paramName] = thinkState.enabled;
      if (thinkState.levelSupported) {
        payload[thinkState.levelParamName] = thinkState.level;
      }
    }

    return payload;
  }

  function timeNow(dateInput) {
    const date = dateInput ? new Date(dateInput) : new Date();
    return date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n/g, '<br>');
  }

  function escapeAttributeValue(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function escapeTextareaValue(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
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
    let currentIndex = 0;

    while (true) {
      const thinkStart = rawText.indexOf('<think>', currentIndex);
      if (thinkStart === -1) {
        allMainContent += rawText.substring(currentIndex);
        break;
      }

      allMainContent += rawText.substring(currentIndex, thinkStart);
      const thinkEnd = rawText.indexOf('</think>', thinkStart + 7);

      if (thinkEnd !== -1) {
        allThinkContent += rawText.substring(thinkStart + 7, thinkEnd) + '\n';
        currentIndex = thinkEnd + 8;
      } else {
        allThinkContent += rawText.substring(thinkStart + 7);
        break;
      }
    }

    if (allThinkContent.trim()) {
      $thoughtsWrapper.show();
      $thoughtsContent.text(allThinkContent.trim());
    } else {
      $thoughtsWrapper.hide();
    }

    if (allMainContent.trim()) {
      $bubble.html(`<div class="markdown-body">${DOMPurify.sanitize(marked.parse(allMainContent))}</div>`);
    } else {
      $bubble.html('');
    }
  }

  function appendMessage(role, text, images, timestamp) {
    const isUser = role === 'user';
    const label = isUser ? 'You' : 'ASLM';
    const timeStr = timeNow(timestamp);

    let imagesHtml = '';
    if (isUser && images && images.length > 0) {
      const content = images.map(function (image) {
        const src = typeof image === 'string' ? image : image.dataUrl;
        return `<img src="${src}" alt="Attached image">`;
      }).join('');
      imagesHtml = `<div class="msg-images">${content}</div>`;
    }

    const $row = $(`
      <div class="msg ${role}">
        <div class="msg-avatar">${isUser ? 'U' : 'A'}</div>
        <div class="msg-body">
          <div class="msg-meta">
            <span>${label}</span>
            <span>${timeStr}</span>
          </div>
          ${!isUser ? `
          <div class="msg-thoughts-wrapper" style="display:none;">
            <div class="msg-thoughts-toggle">Thought Process</div>
            <div class="msg-thoughts-content" style="display:none;"></div>
          </div>
          ` : ''}
          <div class="msg-bubble">${imagesHtml}</div>
        </div>
      </div>
    `);

    if (isUser) {
      $row.find('.msg-bubble').append($('<span>').text(text));
    } else {
      renderMessageHtml($row, text);
    }

    $messagesInner.append($row);
    scrollBottom();
  }

  function appendTyping(timestamp) {
    const timeStr = timeNow(timestamp);
    const $row = $(`
      <div class="msg assistant">
        <div class="msg-avatar">A</div>
        <div class="msg-body">
          <div class="msg-meta">
            <span>ASLM</span>
            <span>${timeStr}</span>
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
      </div>
    `);

    $messagesInner.append($row);
    return $row;
  }

  function scrollBottom() {
    $messagesArea.scrollTop($messagesArea[0].scrollHeight);
  }

  function getCsrfToken() {
    const tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
    if (tokenInput) {
      return tokenInput.value;
    }
    return getCookie('csrftoken');
  }

  function getCookie(name) {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : null;
  }

  async function streamChat(text, imagesToSend, $msgBubble) {
    const $bubbleContent = $msgBubble.find('.msg-bubble');

    try {
      const payload = {
        engine: getActiveEngine(),
        message: text,
        model: $modelSelector.val(),
        system_prompt: $('#systemPrompt').val(),
        chat_id: currentChatId,
        options: collectOptionsPayload()
      };

      if (imagesToSend.length > 0) {
        payload.images = imagesToSend.map(function (img) {
          return img.base64;
        });
      }

      const response = await fetch('/api/chat/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify(payload)
      });

      $msgBubble.removeClass('typing-indicator');
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
      if (returnedChatId && currentChatId !== returnedChatId) {
        currentChatId = returnedChatId;

        if ($(`#historyList .chat-item[data-chat-id="${currentChatId}"]`).length === 0) {
          $('#historyList .empty-state').remove();

          const title = buildChatTitle(text, imagesToSend.length > 0);
          const $newItem = $(`
            <a class="chat-item active" aria-current="page"
               href="/chat/${currentChatId}/"
               data-chat-id="${currentChatId}">
              <div class="chat-item-icon">
                <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
                </svg>
              </div>
              <div class="chat-item-body">
                <span class="chat-item-title">${escHtml(title)}</span>
                <span class="chat-item-date">just now</span>
              </div>
            </a>
          `);

          $('#historyList .chat-item').removeClass('active').removeAttr('aria-current');
          $('#historyList').prepend($newItem);
        }

        const chatTitle = buildChatTitle(text, imagesToSend.length > 0);
        $chatTitle.text(chatTitle);
        document.title = `${chatTitle} - ASLM`;
        history.pushState({ chatId: currentChatId }, chatTitle, `/chat/${currentChatId}/`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let fullText = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        const chunk = decoder.decode(value, { stream: true });
        fullText += chunk;

        const area = $messagesArea[0];
        const isNearBottom = area.scrollHeight - area.clientHeight <= area.scrollTop + 50;
        const $row = $msgBubble.closest('.msg');
        renderMessageHtml($row, fullText);

        if (isNearBottom) {
          scrollBottom();
        }
      }
    } catch (error) {
      $msgBubble.removeClass('typing-indicator');
      $bubbleContent.html(`[Error: failed to connect to server - ${error.message}]`);
    }
  }

  function sendMessage(text, $input) {
    if (!text && visionState.pending.length === 0) {
      return;
    }

    const imagesToSend = visionState.pending.slice();

    if ($welcomeScreen.is(':visible')) {
      $welcomeScreen.hide();
      $conversationInput.show();
      $chatInputConv.val('').css('height', 'auto').focus();
    }

    appendMessage('user', text, imagesToSend);
    $input.val('').css('height', 'auto');
    clearPendingImages();
    updateSendButtons();

    const $msgBubble = appendTyping();
    scrollBottom();
    streamChat(text, imagesToSend, $msgBubble);
  }

  function wireInput($input, $button) {
    $input.on('input', function () {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 200) + 'px';
      updateSendButtons();
    });

    $input.on('keydown', function (event) {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        if (!$button.prop('disabled')) {
          sendMessage($input.val().trim(), $input);
        }
      }
    });

    $button.on('click', function () {
      if (!$button.prop('disabled')) {
        sendMessage($input.val().trim(), $input);
      }
    });
  }

  function loadChat(chatId, pushState) {
    if (!chatId || currentChatId === chatId) {
      return;
    }

    $.ajax({
      url: `/api/chat/${chatId}/`,
      method: 'GET',
      success: function (data) {
        if (data.messages === undefined) {
          return;
        }

        currentChatId = chatId;
        $('#historyList .chat-item').removeClass('active').removeAttr('aria-current');
        $(`#historyList .chat-item[data-chat-id="${chatId}"]`).addClass('active').attr('aria-current', 'page');

        const title = data.title || 'Chat';
        $chatTitle.text(title);
        document.title = `${title} - ASLM`;

        if (pushState !== false) {
          history.pushState({ chatId }, title, `/chat/${chatId}/`);
        }

        $messagesInner.find('.msg').remove();
        $welcomeScreen.hide();
        $messagesArea.show();
        $conversationInput.show();

        data.messages.forEach(function (message) {
          appendMessage(message.role, message.content, message.images || [], message.created_at);
        });

        scrollBottom();
      },
      error: function (error) {
        console.error('Failed to load chat history:', error);
      }
    });
  }

  if (typeof marked !== 'undefined' && typeof hljs !== 'undefined') {
    marked.setOptions({
      highlight: function (code, lang) {
        const language = hljs.getLanguage(lang) ? lang : 'plaintext';
        return hljs.highlight(code, { language }).value;
      },
      breaks: true
    });
  }

  wireInput($chatInput, $sendBtn);
  wireInput($chatInputConv, $sendBtnConv);
  updateSendButtons();

  $newChatBtn.on('click', function (event) {
    if ($(this).attr('href') === '/') {
      event.preventDefault();
      startNewChat();
    }
  });

  $('#imageInput, #imageInputConv').on('change', handleFileInput);

  $(document).on('click', '#attachBtn', function () {
    $('#imageInput').trigger('click');
  });

  $(document).on('click', '#attachBtnConv', function () {
    $('#imageInputConv').trigger('click');
  });

  $(document).on('click', '.img-preview-remove', function (event) {
    event.stopPropagation();
    const index = $(this).closest('.img-preview-thumb').data('idx');
    visionState.pending.splice(index, 1);
    rebuildPreviewStrips();
  });

  $(document).on('click', '.settings-section-header', function () {
    $(this).parent('.settings-section').toggleClass('collapsed');
  });

  $(document).on('click', '.think-toggle-btn', function () {
    if (!thinkState.supported) {
      return;
    }
    thinkState.enabled = !thinkState.enabled;
    updateThinkControls();
  });

  $(document).on('click', '.think-level-btn', function () {
    thinkState.level = $(this).data('value');
    updateThinkControls();
  });

  $(document).on('input', '.setting-range', function () {
    const param = $(this).data('param');
    const decimals = parseInt($(this).data('decimals') || '0', 10);
    $(`#val_${param}`).val(parseFloat(this.value).toFixed(decimals));
  });

  $(document).on('change blur', '.setting-number', function () {
    const param = $(this).data('param');
    const decimals = parseInt($(this).data('decimals') || '0', 10);
    const min = parseFloat(this.min);
    const max = parseFloat(this.max);
    let value = parseFloat(this.value);

    if (Number.isNaN(value)) {
      value = parseFloat($(`#dyn_${param}`).val());
    }

    value = Math.min(max, Math.max(min, value));
    this.value = value.toFixed(decimals);
    $(`#dyn_${param}`).val(value);
  });

  $(document).on('keydown', '.setting-number', function (event) {
    if (event.key === 'Enter') {
      $(this).trigger('blur');
    }
  });

  $messagesInner.on('click', '.msg-thoughts-toggle', function (event) {
    event.stopPropagation();
    const $wrapper = $(this).closest('.msg-thoughts-wrapper');
    const $content = $wrapper.find('.msg-thoughts-content');

    $content.slideToggle(200);
    $wrapper.toggleClass('expanded');
  });

  $(document).on('click', '#historyList .chat-item', function (event) {
    event.preventDefault();
    const chatId = $(this).data('chat-id');
    loadChat(chatId, true);
  });

  $engineSelector.on('change', async function () {
    try {
      await applyEngineSelection($(this).val(), {
        preferredModel: '',
        persist: true
      });
    } catch (error) {
      console.error('Failed to switch engine:', error);
      setEngineAddressStatus('Error', 'error');
    }
  });

  $engineAddressInput.on('keydown', function (event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      $(this).trigger('blur');
    }
  });

  $engineAddressInput.on('blur', async function () {
    const engine = getActiveEngine();
    const addressKey = getEngineAddressKey(engine);
    const addressValue = $(this).val().trim();
    const selectionVersion = ++engineSelectionVersion;

    if (!addressKey) {
      return;
    }

    if ((runtimeSettings[addressKey] || '') === addressValue) {
      setEngineAddressStatus('Saved', null);
      return;
    }

    try {
      setEngineAddressStatus('Saving...', 'pending');
      runtimeSettings = await saveRuntimeSettings({ [addressKey]: addressValue });

      if (selectionVersion !== engineSelectionVersion) {
        return;
      }

      updateEngineAddressUi();
      await refreshModelsForEngine(
        engine,
        $modelSelector.val(),
        Array.isArray(runtimeSettings.models) ? runtimeSettings.models : null,
        selectionVersion
      );
    } catch (error) {
      console.error('Failed to save engine address:', error);
      setEngineAddressStatus('Error', 'error');
    }
  });

  $engineApiKeyEnabled.on('change', async function () {
    if (getActiveEngine() !== 'openai') {
      return;
    }

    const isEnabled = $(this).is(':checked');
    $engineApiKeyInput.toggle(isEnabled);
    if (isEnabled) {
      setEngineApiKeyStatus('Enter key', null);
      $engineApiKeyInput.trigger('focus');
      return;
    }

    try {
      setEngineApiKeyStatus('Saving...', 'pending');
      runtimeSettings = await saveRuntimeSettings({ openai_api_key: '' });
      updateEngineAddressUi();
    } catch (error) {
      console.error('Failed to update API key state:', error);
      setEngineApiKeyStatus('Error', 'error');
    }
  });

  $engineApiKeyInput.on('keydown', function (event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      $(this).trigger('blur');
    }
  });

  $engineApiKeyInput.on('blur', async function () {
    if (getActiveEngine() !== 'openai' || !$engineApiKeyEnabled.is(':checked')) {
      return;
    }

    const apiKeyValue = $(this).val().trim();
    if (!apiKeyValue) {
      setEngineApiKeyStatus(runtimeSettings.has_openai_api_key ? 'Saved' : 'Enter key', null);
      return;
    }

    try {
      setEngineApiKeyStatus('Saving...', 'pending');
      runtimeSettings = await saveRuntimeSettings({ openai_api_key: apiKeyValue });
      $engineApiKeyInput.val('');
      updateEngineAddressUi();
    } catch (error) {
      console.error('Failed to save API key:', error);
      setEngineApiKeyStatus('Error', 'error');
    }
  });

  $modelSelector.on('change', function () {
    loadModelInfo($(this).val());
  });

  window.addEventListener('popstate', function (event) {
    if (event.state && event.state.chatId) {
      loadChat(event.state.chatId, false);
    } else {
      startNewChat();
    }
  });

  const preloadChatId = $('body').data('preload-chat');
  if (preloadChatId) {
    loadChat(preloadChatId, false);
  }

  updateEngineAddressUi();
  applyEngineSelection(getActiveEngine(), {
    preferredModel: $modelSelector.val(),
    persist: false
  }).catch(function (error) {
    console.error('Failed to initialize engine state:', error);
  });
});
