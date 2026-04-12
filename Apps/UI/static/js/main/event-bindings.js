// Copyright NGGT.LightKeeper. All Rights Reserved.

export function bindEventHandlers(context, dependencies) {
  const {
    attachmentsUi,
    chatController,
    engineManager,
    historyUi,
    messagesUi,
    parametersUi
  } = dependencies;
  const { dom, state } = context;

  dom.$newChatBtn.on('click', function onNewChatClick(event) {
    if ($(this).attr('href') === '/') {
      event.preventDefault();
      chatController.startNewChat();
    }
  });

  dom.$messagesInner.on('click', '.msg-regen-btn', function onRegenClick() {
    const $msg = $(this).closest('.msg');
    if ($msg.hasClass('user')) {
      chatController.regenerateFromUserMessage($msg);
      return;
    }
    chatController.regenerateLastResponse();
  });

  dom.$messagesInner.on('click', '.msg-copy-btn', function onCopyClick() {
    messagesUi.copyMessage($(this));
  });

  dom.$messagesInner.on('click', '.msg-delete-btn', function onDeleteClick() {
    chatController.deleteMessage($(this).closest('.msg'));
  });

  dom.$imageInput.add(dom.$imageInputConv).on('change', function onAttachmentChange(event) {
    attachmentsUi.handleFileInput(event);
  });

  $(document).on('click', '#attachBtn', function onAttachClick() {
    dom.$imageInput.trigger('click');
  });

  $(document).on('click', '#attachBtnConv', function onAttachConvClick() {
    dom.$imageInputConv.trigger('click');
  });

  $(document).on('click', '.img-preview-remove', function onAttachmentRemove(event) {
    event.stopPropagation();
    const index = $(this).closest('[data-idx]').data('idx');
    attachmentsUi.removePendingAttachment(index);
  });

  $(document).on('click', '.settings-section-header', function onSectionHeaderClick() {
    $(this).parent('.settings-section').toggleClass('collapsed');
  });

  $(document).on('click', '.think-toggle-btn', function onThinkToggleClick() {
    if (!state.thinkState.supported || !state.thinkState.toggleSupported || state.thinkState.levelSupported) {
      return;
    }
    state.thinkState.enabled = !state.thinkState.enabled;
    parametersUi.updateThinkControls();
    engineManager.schedulePresetSync();
  });

  $(document).on('click', '.think-level-btn', function onThinkLevelClick() {
    if (!state.thinkState.supported || !state.thinkState.levelSupported) {
      return;
    }
    state.thinkState.level = $(this).data('value');
    parametersUi.updateThinkControls();
    engineManager.schedulePresetSync();
  });

  $(document).on('input', '.setting-range', function onRangeInput() {
    parametersUi.handleRangeInput($(this));
  });

  $(document).on('change blur', '.setting-number', function onNumberChange() {
    parametersUi.handleNumberInput($(this));
    engineManager.schedulePresetSync();
  });

  $(document).on('keydown', '.setting-number', function onNumberKeyDown(event) {
    if (event.key === 'Enter') {
      $(this).trigger('blur');
    }
  });

  $(document).on('change blur', '.dyn-param[data-value-type="optional-number"], .dyn-param[data-value-type="optional-integer"]', function onOptionalNumberChange() {
    parametersUi.normalizeOptionalNumericInput($(this));
    engineManager.schedulePresetSync();
  });

  $(document).on('change', '.optional-param-toggle', function onOptionalToggleChange() {
    parametersUi.toggleOptionalParameter($(this));
    engineManager.schedulePresetSync();
  });

  dom.$messagesInner.on('mousedown', '.msg-thoughts-toggle', function onThoughtToggleMouseDown(event) {
    event.preventDefault();
    event.stopPropagation();
    messagesUi.toggleThoughtSection($(this));
  });

  $(document).on('click', function onDocumentClick(event) {
    if (!$(event.target).closest('#chatItemDropdown, .chat-item-menu-btn').length) {
      historyUi.closeChatMenu();
    }
  });

  $(document).on('click', '.chat-item-menu-btn', function onChatMenuClick(event) {
    historyUi.toggleChatMenu($(this).closest('.chat-item'), event);
  });

  $(document).on('click', '#historyList .chat-item', function onHistoryItemClick(event) {
    event.preventDefault();
    chatController.loadChat($(this).data('chat-id'), true);
  });

  $('#chatRenameBtn').on('click', function onRenameClick() {
    chatController.renameActiveMenuChat();
  });

  $('#chatDeleteBtn').on('click', function onDeleteChatClick() {
    chatController.deleteActiveMenuChat();
  });

  dom.$engineSelector.on('change', async function onEngineChange() {
    try {
      await engineManager.applyEngineSelection($(this).val(), {
        persist: true
      });
    } catch (error) {
      console.error('Failed to switch engine:', error);
      engineManager.setEngineAddressStatus('Error', 'error');
    }
  });

  dom.$engineAddressInput.on('keydown', function onAddressKeyDown(event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      $(this).trigger('blur');
    }
  });

  dom.$engineAddressInput.on('blur', function onAddressBlur() {
    engineManager.persistEngineAddress();
  });

  dom.$engineApiKeyEnabled.on('change', function onApiKeyToggle() {
    engineManager.handleApiKeyToggle();
  });

  dom.$engineApiKeyInput.on('keydown', function onApiKeyKeyDown(event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      $(this).trigger('blur');
    }
  });

  dom.$engineApiKeyInput.on('blur', function onApiKeyBlur() {
    engineManager.persistApiKey();
  });

  dom.$modelSelector.on('change', function onModelChange() {
    engineManager.loadModelInfo($(this).val());
  });

  dom.$presetSelector.on('change', function onPresetChange() {
    engineManager.selectPreset($(this).val()).catch(function onSelectError(error) {
      console.error('Failed to select preset:', error);
    });
  });

  dom.$presetCreateBtn.on('click', function onPresetCreate() {
    engineManager.createPreset().catch(function onCreateError(error) {
      console.error('Failed to create preset:', error);
    });
  });

  dom.$presetRenameBtn.on('click', function onPresetRename() {
    engineManager.renamePreset().catch(function onRenameError(error) {
      console.error('Failed to rename preset:', error);
    });
  });

  dom.$presetDeleteBtn.on('click', function onPresetDelete() {
    engineManager.deletePreset().catch(function onDeleteError(error) {
      console.error('Failed to delete preset:', error);
    });
  });

  $(document).on('change', '.dyn-param', function onDynamicParamChange() {
    engineManager.schedulePresetSync();
  });

  $(document).on('blur', '.dyn-param', function onDynamicParamBlur() {
    if ($(this).is(':checkbox')) {
      return;
    }
    engineManager.schedulePresetSync();
  });

  window.addEventListener('popstate', function onPopState(event) {
    if (event.state && event.state.chatId) {
      chatController.loadChat(event.state.chatId, false);
    } else {
      chatController.startNewChat();
    }
  });
}
