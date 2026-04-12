// Copyright NGGT.LightKeeper. All Rights Reserved.

import { DEFAULT_THINK_LEVEL_OPTIONS } from './constants.js';
import { normalizeEngineValue } from '../engines/engine-registry.js';
import { parseJsonScript } from './utils.js';

function svgIcon(iconPath, attrs) {
  return `<svg ${attrs}><use href="${iconPath}#icon"></use></svg>`;
}

export function createAppContext() {
  const dom = {
    $body: $('body'),
    $newChatBtn: $('#newChatBtn'),
    $historyList: $('#historyList'),
    $chatTitle: $('#chatTitle'),
    $messagesArea: $('#messagesArea'),
    $messagesInner: $('#messagesInner'),
    $welcomeScreen: $('#welcomeScreen'),
    $chatInput: $('#chatInput'),
    $sendBtn: $('#sendBtn'),
    $chatInputConv: $('#chatInputConv'),
    $sendBtnConv: $('#sendBtnConv'),
    $conversationInput: $('#conversationInput'),
    $engineSelector: $('#engineSelector'),
    $engineAddressGroup: $('#engineAddressGroup'),
    $engineAddressInput: $('#engineAddressInput'),
    $engineAddressStatus: $('#engineAddressStatus'),
    $engineAddressHint: $('#engineAddressHint'),
    $engineApiKeyGroup: $('#engineApiKeyGroup'),
    $engineApiKeyEnabled: $('#engineApiKeyEnabled'),
    $engineApiKeyInput: $('#engineApiKeyInput'),
    $engineApiKeyStatus: $('#engineApiKeyStatus'),
    $modelSelector: $('#modelSelector'),
    $presetGroup: $('#ollamaPresetGroup'),
    $presetSelector: $('#ollamaPresetSelector'),
    $presetCreateBtn: $('#ollamaPresetCreateBtn'),
    $presetRenameBtn: $('#ollamaPresetRenameBtn'),
    $presetDeleteBtn: $('#ollamaPresetDeleteBtn'),
    $groupTools: $('#group-tools'),
    $dividerTools: $('#divider-tools'),
    $toolInspectorModal: $('#toolInspectorModal'),
    $chatItemDropdown: $('#chatItemDropdown'),
    $systemPrompt: $('#systemPrompt'),
    $imageInput: $('#imageInput'),
    $imageInputConv: $('#imageInputConv'),
    $imagePreviewStrip: $('#imagePreviewStrip'),
    $imagePreviewStripConv: $('#imagePreviewStripConv'),
    $attachBtn: $('#attachBtn'),
    $attachBtnConv: $('#attachBtnConv'),
    $visionBadge: $('#visionBadge'),
    $visionBadgeConv: $('#visionBadgeConv'),
    $thinkToggleBtn: $('#thinkToggleBtn'),
    $thinkToggleBtnConv: $('#thinkToggleBtnConv'),
    $thinkLevelSelector: $('#thinkLevelSelector'),
    $thinkLevelSelectorConv: $('#thinkLevelSelectorConv')
  };

  const runtimeSettings = parseJsonScript('runtimeSettingsData') || {};
  const defaultAvailableToolServers = parseJsonScript('availableToolServersData') || [];
  const uiIconPaths = parseJsonScript('uiIconPathsData') || {};

  const icons = {
    STOP_ICON: svgIcon(uiIconPaths.stopSquare, 'width="18" height="18" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true"'),
    SEND_ICON: svgIcon(uiIconPaths.send, 'width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"'),
    REMOVE_ATTACHMENT_ICON: svgIcon(uiIconPaths.removeAttachment, 'width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true"'),
    COPY_MESSAGE_ICON: svgIcon(uiIconPaths.copy, 'width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"'),
    REGENERATE_ICON: svgIcon(uiIconPaths.refresh, 'width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"'),
    DELETE_MESSAGE_ICON: svgIcon(uiIconPaths.trash, 'width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"'),
    COPIED_ICON: svgIcon(uiIconPaths.check, 'width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"'),
    CHAT_ITEM_ICON: svgIcon(uiIconPaths.chatBubble, 'width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"'),
    CHAT_ITEM_MENU_ICON: svgIcon(uiIconPaths.ellipsisVertical, 'width="14" height="14" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true"')
  };

  icons.buildMessageActionsHtml = function buildMessageActionsHtml() {
    return `<div class="msg-actions">
      <button class="msg-action-btn msg-copy-btn" title="Copy" aria-label="Copy message">${icons.COPY_MESSAGE_ICON}</button>
      <button class="msg-action-btn msg-regen-btn" title="Regenerate" aria-label="Regenerate response">${icons.REGENERATE_ICON}</button>
      <button class="msg-action-btn msg-delete-btn" title="Delete" aria-label="Delete message">${icons.DELETE_MESSAGE_ICON}</button>
    </div>`;
  };

  return {
    dom,
    icons,
    state: {
      runtimeSettings,
      defaultAvailableToolServers,
      availableToolServers: Array.isArray(defaultAvailableToolServers) ? defaultAvailableToolServers.slice() : [],
      selectedToolServerIds: new Set(),
      currentChatId: null,
      engineSelectionVersion: 0,
      modelInfoRequestVersion: 0,
      activeEngine: normalizeEngineValue(runtimeSettings['llm-engine'] || dom.$body.data('llm-engine') || 'ollama-service'),
      modelsCache: {},
      lmsModelsRefreshTimer: null,
      lmsModelsRefreshInFlight: false,
      presetState: {
        engine: '',
        model: '',
        activePresetId: '',
        presets: []
      },
      presetSyncTimer: null,
      isChatGenerating: false,
      currentAbortController: null,
      queuedMessageCounter: 0,
      chatRequestQueue: [],
      currentModelInfo: null,
      activeMenuTarget: null,
      visionState: {
        supported: false
      },
      fileState: {
        supported: false
      },
      attachmentState: {
        pending: []
      },
      thinkState: {
        supported: false,
        paramName: 'think',
        toggleSupported: false,
        enabled: true,
        levelSupported: false,
        levelParamName: 'think_level',
        levelOptions: DEFAULT_THINK_LEVEL_OPTIONS.slice(),
        level: 'medium'
      },
      toolState: {
        supported: false
      }
    }
  };
}
