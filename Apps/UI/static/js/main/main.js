// Copyright NGGT.LightKeeper. All Rights Reserved.

import { createAttachmentsUi } from '../ui/attachments-ui.js';
import { createBrowserPortalUi } from '../ui/browser-portal-ui.js';
import { createChatHistoryUi } from '../ui/chat-history-ui.js';
import { createDeepResearchUi } from '../ui/deep-research-ui.js';
import { createMessagesUi } from '../ui/messages-ui.js';
import { createModelSelectorUi } from '../ui/model-selector-ui.js';
import { createParametersUi } from '../ui/parameters-ui.js';
import { createSettingsSelectUi } from '../ui/settings-select-ui.js';
import { createSkillsUi } from '../ui/skills-ui.js';
import { createToolInspector } from '../ui/tool-inspector.js';
import { createAppContext } from './app-context.js';
import { createChatController } from './chat-controller.js';
import { createEngineManager } from './engine-manager.js';
import { bindEventHandlers } from './event-bindings.js';

// Application bootstrap.
// Initialize the chat page after the DOM is ready.
$(function initChatApp() {
  const context = createAppContext();

  const toolInspector = createToolInspector(context);
  const deepResearchUi = createDeepResearchUi(context, { toolInspector });
  const browserPortalUi = createBrowserPortalUi(context);
  const attachmentsUi = createAttachmentsUi(context);
  const parametersUi = createParametersUi(context);
  const skillsUi = createSkillsUi(context);
  // Settings selects (engine / preset / dyn params) share the model-selector look
  // but stay independent of the model control itself.
  const settingsSelectUi = createSettingsSelectUi(context);
  const modelSelectorUi = createModelSelectorUi(context);
  const messagesUi = createMessagesUi(context, {
    attachmentUi: attachmentsUi,
    browserPortalUi,
    deepResearchUi,
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
    parametersUi,
    skillsUi
  });

  bindEventHandlers(context, {
    attachmentsUi,
    chatController,
    deepResearchUi,
    engineManager,
    historyUi,
    messagesUi,
    modelSelectorUi,
    parametersUi,
    settingsSelectUi
  });

  // Finalize shared UI setup.
  toolInspector.bindGlobalEvents();
  messagesUi.configureMarkdown();
  chatController.wireInput(context.dom.$chatInput, context.dom.$sendBtn);
  chatController.wireInput(context.dom.$chatInputConv, context.dom.$sendBtnConv);
  messagesUi.updateSendButtons();
  skillsUi.init();
  // Catch any selects rendered during engine bootstrap after first paint.
  settingsSelectUi.scan();
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
