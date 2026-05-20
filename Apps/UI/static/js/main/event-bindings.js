// Copyright NGGT.LightKeeper. All Rights Reserved.

// Event bindings.
// Wire all DOM events used by the chat page.
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
  const rightSidebarStorageKey = 'aslm.settingsSidebarCollapsed';
  const $activityRoots = dom.$messagesInner.add($('#reasoningDrawerBody'));

  function setRightSidebarCollapsed(collapsed, persist) {
    dom.$chatShell.toggleClass('settings-collapsed', !!collapsed);
    dom.$sidebarRightToggle
      .attr('aria-expanded', collapsed ? 'false' : 'true')
      .attr('aria-label', collapsed ? 'Expand settings' : 'Collapse settings')
      .attr('title', collapsed ? 'Expand settings' : 'Collapse settings');

    if (persist !== false) {
      try {
        window.localStorage.setItem(rightSidebarStorageKey, collapsed ? '1' : '0');
      } catch (_error) {
        // Ignore storage failures in privacy-restricted contexts.
      }
    }
  }

  try {
    setRightSidebarCollapsed(window.localStorage.getItem(rightSidebarStorageKey) === '1', false);
  } catch (_error) {
    setRightSidebarCollapsed(false, false);
  }

  // Chat shell events.
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

  $activityRoots.on('click', '.md-code-copy-btn', function onMarkdownCodeCopyClick(event) {
    event.preventDefault();
    event.stopPropagation();
    messagesUi.copyCodeBlock($(this));
  });

  dom.$messagesInner.on('click', '.msg-delete-btn', function onDeleteClick() {
    chatController.deleteMessage($(this).closest('.msg'));
  });

  dom.$sidebarRightToggle.on('click', function onRightSidebarToggleClick() {
    setRightSidebarCollapsed(!dom.$chatShell.hasClass('settings-collapsed'), true);
  });

  $(document).on('click', '#contextUsageBtn, #contextUsageBtnConv', function onContextUsageClick(event) {
    event.preventDefault();
    if ($(this).prop('disabled') || state.isChatGenerating) {
      return;
    }
    chatController.triggerContextCompression(true).catch(function onContextCompressionError(error) {
      console.error('Failed to compress context:', error);
    });
  });

  function closeComposerMenus() {
    dom.$composerMenuPopover.add(dom.$composerMenuPopoverConv).hide();
    dom.$composerMenuBtn.add(dom.$composerMenuBtnConv)
      .removeClass('is-open')
      .attr('aria-expanded', 'false');
  }

  function closeThinkLevelMenus() {
    dom.$thinkLevelSelector.add(dom.$thinkLevelSelectorConv)
      .removeClass('is-open')
      .find('.think-level-menu')
      .hide();
    dom.$thinkLevelSelector.add(dom.$thinkLevelSelectorConv)
      .find('.think-toggle-btn')
      .attr('aria-expanded', 'false');
  }

  function toggleComposerMenu($button, $popover) {
    const willOpen = !$popover.is(':visible');
    closeComposerMenus();
    closeThinkLevelMenus();
    if (!willOpen) {
      return;
    }
    $popover.show();
    $button.addClass('is-open').attr('aria-expanded', 'true');
  }

  dom.$composerMenuBtn.on('click', function onComposerMenuClick(event) {
    event.preventDefault();
    event.stopPropagation();
    toggleComposerMenu(dom.$composerMenuBtn, dom.$composerMenuPopover);
  });

  dom.$composerMenuBtnConv.on('click', function onComposerMenuConvClick(event) {
    event.preventDefault();
    event.stopPropagation();
    toggleComposerMenu(dom.$composerMenuBtnConv, dom.$composerMenuPopoverConv);
  });

  $(document).on('click', function onComposerMenuDocumentClick(event) {
    if (!$(event.target).closest('.composer-menu-popover, .composer-menu-btn, .composer-skills-flyout').length) {
      closeComposerMenus();
    }
    if (!$(event.target).closest('.think-level-selector').length) {
      closeThinkLevelMenus();
    }
  });

  $(document).on('keydown', function onComposerMenuKeydown(event) {
    if (event.key === 'Escape') {
      closeComposerMenus();
      closeThinkLevelMenus();
    }
  });

  $activityRoots.on('click', '.msg-search-chip:not(.msg-search-chip--more)', function onSearchChipClick(event) {
    event.stopPropagation();
  });

  $activityRoots.on('click', '.msg-citation-chip', function onCitationChipClick(event) {
    event.stopPropagation();
  });

  $activityRoots.on('click', '.msg-search-chip--more', function onSearchMoreClick(event) {
    event.preventDefault();
    event.stopPropagation();
    messagesUi.toggleSearchSources($(this));
  });

  $activityRoots.on('click', [
    '.msg-tool-call-card[data-tool-segment-index]',
    '.msg-reasoning-tool-row[data-tool-segment-index]'
  ].join(', '), function onToolCardClick(event) {
    if ($(event.target).closest('.msg-search-chip, .msg-write-card, .msg-edit-card, a, button').length) {
      return;
    }
    messagesUi.openToolInspectorFromCard($(this));
  });

  $activityRoots.on('click', '.msg-write-card[data-write-segment-index]', function onWriteCardClick() {
    messagesUi.toggleWriteCard($(this));
  });

  $activityRoots.on('keydown', '.msg-write-card[data-write-segment-index]', function onWriteCardKeyDown(event) {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }
    event.preventDefault();
    messagesUi.toggleWriteCard($(this));
  });

  $activityRoots.on('click', '.msg-edit-card[data-edit-segment-index]', function onEditCardClick() {
    messagesUi.toggleEditCard($(this));
  });

  $activityRoots.on('keydown', '.msg-edit-card[data-edit-segment-index]', function onEditCardKeyDown(event) {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }
    event.preventDefault();
    messagesUi.toggleEditCard($(this));
  });

  $activityRoots.on('click', '.msg-compression-context-btn', function onCompressionContextClick(event) {
    event.preventDefault();
    event.stopPropagation();
    messagesUi.toggleCompressionContext($(this));
  });

  $activityRoots.on('mousedown', '.msg-write-preview, .msg-edit-preview', function onToolPreviewMouseDown(event) {
    messagesUi.startWritePreviewPan(event, $(this));
  });

  $activityRoots.on('auxclick', '.msg-write-preview, .msg-edit-preview', function onToolPreviewAuxClick(event) {
    if (event.button === 1) {
      event.preventDefault();
      event.stopPropagation();
    }
  });

  dom.$messagesInner.on('click', '.msg-thoughts-toggle', function onThoughtToggleClick(event) {
    event.preventDefault();
    event.stopPropagation();
    messagesUi.toggleThoughtSection($(this));
  });

  // Reasoning drawer: close button and backdrop.
  $(document).on('click', '#reasoningDrawerClose', function onReasoningDrawerClose() {
    messagesUi.closeReasoningDrawer();
  });

  $(document).on('click', '#reasoningDrawerBackdrop', function onReasoningDrawerBackdropClick() {
    messagesUi.closeReasoningDrawer();
  });

  $(document).on('keydown', function onReasoningDrawerKeydown(event) {
    if (event.key === 'Escape' && $('#reasoningDrawer').hasClass('is-open')) {
      messagesUi.closeReasoningDrawer();
    }
  });


  // Attachment events.
  const $dropOverlay = $('<div class="file-drop-overlay" aria-hidden="true"><div class="file-drop-overlay-inner">Drop files to attach</div></div>');
  $('body').append($dropOverlay);

  function showDropOverlay() {
    $dropOverlay.addClass('is-visible');
    dom.$chatShell.addClass('is-file-dragging');
  }

  function hideDropOverlay() {
    $dropOverlay.removeClass('is-visible');
    dom.$chatShell.removeClass('is-file-dragging');
  }

  dom.$imageInput.add(dom.$imageInputConv).on('change', function onAttachmentChange(event) {
    attachmentsUi.handleFileInput(event);
  });

  $(document).on('click', '#attachBtn', function onAttachClick() {
    closeComposerMenus();
    dom.$imageInput.attr('accept', '*/*').prop('disabled', false).trigger('click');
  });

  $(document).on('click', '#attachBtnConv', function onAttachConvClick() {
    closeComposerMenus();
    dom.$imageInputConv.attr('accept', '*/*').prop('disabled', false).trigger('click');
  });

  $(document).on('click', '.img-preview-remove', function onAttachmentRemove(event) {
    event.stopPropagation();
    const index = $(this).closest('[data-idx]').data('idx');
    attachmentsUi.removePendingAttachment(index);
  });

  function getDragDataTransfer(event) {
    return event && (event.dataTransfer || (event.originalEvent && event.originalEvent.dataTransfer));
  }

  function eventHasDraggedFiles(event) {
    const dataTransfer = getDragDataTransfer(event);
    if (!dataTransfer) {
      return false;
    }
    if (dataTransfer.files && dataTransfer.files.length > 0) {
      return true;
    }
    if (dataTransfer.items && dataTransfer.items.length > 0) {
      return Array.from(dataTransfer.items).some(function isFileItem(item) {
        return String(item && item.kind ? item.kind : '').toLowerCase() === 'file';
      });
    }

    return Array.from(dataTransfer.types || []).some(function isFilesType(type) {
      return String(type || '').toLowerCase() === 'files';
    });
  }

  function isSkillsManagerOpen() {
    return document.body.classList.contains('skills-manager-open');
  }

  function isOverSkillsImportSurface(event) {
    const el = event && (event.target || (event.nativeEvent && event.nativeEvent.target));
    return !!(el && el.closest && (
      el.closest('.skills-import-dropzone')
      || el.closest('.skills-add-dialog')
    ));
  }

  function handleFileDrag(event) {
    const dataTransfer = getDragDataTransfer(event);
    if (!dataTransfer) {
      return;
    }

    // Only accept file drag over the import dropzone — global preventDefault breaks
    // Windows drag-and-drop (ghost icon stuck to cursor after mouseup).
    if (isSkillsManagerOpen()) {
      if (isOverSkillsImportSurface(event)) {
        event.preventDefault();
        dataTransfer.dropEffect = 'copy';
      }
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    dataTransfer.dropEffect = 'copy';
    showDropOverlay();
  }

  function handleFileDragEnd(event) {
    if (!event) {
      return;
    }
    if (isSkillsManagerOpen()) {
      document.querySelectorAll('.skills-import-dropzone.is-dragover').forEach(function (el) {
        el.classList.remove('is-dragover');
      });
      return;
    }
    if (event.type === 'dragend' || event.type === 'drop') {
      hideDropOverlay();
      return;
    }
    if (event.clientX <= 0 || event.clientY <= 0 || event.clientX >= window.innerWidth || event.clientY >= window.innerHeight) {
      hideDropOverlay();
    }
  }

  function handleFileDrop(event) {
    const dataTransfer = getDragDataTransfer(event);
    if (!dataTransfer) {
      return;
    }

    // Never read dataTransfer.files while skills manager is open — that triggers
    // Chromium's "upload N files to this site?" confirmation dialog.
    if (isSkillsManagerOpen()) {
      if (isOverSkillsImportSurface(event)) {
        event.preventDefault();
      }
      return;
    }

    const files = dataTransfer.files;
    event.preventDefault();
    event.stopPropagation();
    hideDropOverlay();
    if (files && files.length > 0) {
      attachmentsUi.handleDroppedFiles(files);
    }
  }

  const dragTargets = [
    window,
    document,
    document.documentElement,
    document.body,
    dom.$chatShell.get(0),
    dom.$messagesArea.get(0),
    dom.$welcomeScreen.get(0),
    dom.$conversationInput.get(0)
  ].filter(Boolean);

  dragTargets.forEach(function bindDragTarget(target) {
    target.addEventListener('dragenter', handleFileDrag, true);
    target.addEventListener('dragover', handleFileDrag, true);
    target.addEventListener('dragleave', handleFileDragEnd, true);
    target.addEventListener('dragend', handleFileDragEnd, true);
    target.addEventListener('drop', handleFileDrop, true);
  });

  const dropOverlayNode = $dropOverlay.get(0);
  if (dropOverlayNode) {
    dropOverlayNode.addEventListener('dragenter', handleFileDrag, true);
    dropOverlayNode.addEventListener('dragover', handleFileDrag, true);
    dropOverlayNode.addEventListener('dragleave', function onOverlayDragLeave(event) {
      if (event.target === dropOverlayNode) {
        hideDropOverlay();
      }
    }, true);
    dropOverlayNode.addEventListener('drop', handleFileDrop, true);
  }


  // Settings panel events.
  $(document).on('click', '.settings-section-header', function onSectionHeaderClick() {
    $(this).parent('.settings-section').toggleClass('collapsed');
  });

  $(document).on('click', '.think-toggle-btn', function onThinkToggleClick() {
    if (!state.thinkState.supported) {
      return;
    }

    const $selector = $(this).closest('.think-level-selector');
    if (!$selector.length) {
      $(this).remove();
      return;
    }

    const $menu = $selector.find('.think-level-menu').first();
    const willOpen = !$menu.is(':visible');
    closeComposerMenus();
    closeThinkLevelMenus();
    if (willOpen) {
      $selector.addClass('is-open');
      $menu.show();
      $(this).attr('aria-expanded', 'true');
    }
  });

  $(document).on('click', '.think-level-btn', function onThinkLevelClick() {
    if (!state.thinkState.supported) {
      return;
    }

    const value = String($(this).data('value') || '').toLowerCase();
    if (value === 'off') {
      state.thinkState.enabled = false;
      state.thinkState.level = 'off';
    } else {
      state.thinkState.enabled = true;
      state.thinkState.level = value || state.thinkState.level || 'medium';
    }
    closeThinkLevelMenus();
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

  $(document).on(
    'change blur',
    '.dyn-param[data-value-type="optional-number"], .dyn-param[data-value-type="optional-integer"]',
    function onOptionalNumberChange() {
      parametersUi.normalizeOptionalNumericInput($(this));
      engineManager.schedulePresetSync();
    }
  );

  $(document).on('change', '.optional-param-toggle', function onOptionalToggleChange() {
    parametersUi.toggleOptionalParameter($(this));
    engineManager.schedulePresetSync();
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


  // Chat history events.
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


  // Engine settings events.
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
    const modelName = $(this).val();
    engineManager.rememberLastModel(engineManager.getActiveEngine(), modelName);
    engineManager.loadModelInfo(modelName);
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


  // Navigation events.
  window.addEventListener('popstate', function onPopState(event) {
    if (event.state && event.state.chatId) {
      chatController.loadChat(event.state.chatId, false);
    } else {
      chatController.startNewChat();
    }
  });
}
