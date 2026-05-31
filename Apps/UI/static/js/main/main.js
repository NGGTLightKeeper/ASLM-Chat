// Copyright NGGT.LightKeeper. All Rights Reserved.

import { createAttachmentsUi } from '/static/js/ui/attachments-ui.js';
import { createBrowserPortalUi } from '/static/js/ui/browser-portal-ui.js';
import { createChatHistoryUi } from '/static/js/ui/chat-history-ui.js';
import { createMessagesUi } from '/static/js/ui/messages-ui.js';
import { createModelSelectorUi } from '/static/js/ui/model-selector-ui.js';
import { createParametersUi } from '/static/js/ui/parameters-ui.js';
import { createSkillsUi } from '/static/js/ui/skills-ui.js';
import { createToolInspector } from '/static/js/ui/tool-inspector.js';
import { createAppContext } from '/static/js/main/app-context.js';
import { createChatController } from '/static/js/main/chat-controller.js';
import { createEngineManager } from '/static/js/main/engine-manager.js';
import { bindEventHandlers } from '/static/js/main/event-bindings.js';

// Application bootstrap.
// Initialize the chat page after the DOM is ready.
$(function initChatApp() {
  const context = createAppContext();

  const toolInspector = createToolInspector(context);
  const browserPortalUi = createBrowserPortalUi(context);
  const attachmentsUi = createAttachmentsUi(context);
  const parametersUi = createParametersUi(context);
  const skillsUi = createSkillsUi(context);
  const modelSelectorUi = createModelSelectorUi(context);
  const messagesUi = createMessagesUi(context, {
    attachmentUi: attachmentsUi,
    browserPortalUi,
    toolInspector
  });

  attachmentsUi.setUpdateSendButtons(messagesUi.updateSendButtons);

  const historyUi = createChatHistoryUi(context);
  const engineManager = createEngineManager(context, {
    attachmentsUi,
    parametersUi
  });
  const chatController = createChatController(context, {
    attachmentUi: attachmentsUi,
    engineManager,
    historyUi,
    messagesUi,
    parametersUi
  });

  bindEventHandlers(context, {
    attachmentsUi,
    chatController,
    engineManager,
    historyUi,
    messagesUi,
    modelSelectorUi,
    parametersUi
  });

  // Finalize shared UI setup.
  toolInspector.bindGlobalEvents();
  messagesUi.configureMarkdown();
  chatController.wireInput(context.dom.$chatInput, context.dom.$sendBtn);
  chatController.wireInput(context.dom.$chatInputConv, context.dom.$sendBtnConv);
  messagesUi.updateSendButtons();
  skillsUi.init();
  chatController.refreshContextUsageNow();
  chatController.startContextUsagePolling();

  // Restore a preloaded chat when the page was opened on /chat/<id>/.
  const preloadChatId = context.dom.$body.data('preload-chat');
  if (preloadChatId) {
    chatController.loadChat(preloadChatId, false);
  }

  // Prime the engine state and load the initial model list.
  parametersUi.updateAvailableToolServers(context.state.defaultAvailableToolServers);
  parametersUi.applySelectedToolServerIds([]);
  engineManager.updateEngineAddressUi();
  engineManager.resetModelUiState('Loading models...');
  engineManager.applyEngineSelection(engineManager.getActiveEngine(), {
    persist: false
  }).catch(function onInitError(error) {
    console.error('Failed to initialize engine state:', error);
  });
});
