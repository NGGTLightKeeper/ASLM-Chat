// Copyright NGGT.LightKeeper. All Rights Reserved.

import { escHtml, escapeAttributeValue } from '../main/utils.js';

export function createChatHistoryUi(context) {
  const { dom, icons, state } = context;

  function buildChatItemHtml(chatId, title, dateStr, active) {
    const activeAttr = active ? ' class="chat-item active" aria-current="page"' : ' class="chat-item"';
    return `
      <a${activeAttr} href="/chat/${chatId}/" data-chat-id="${escapeAttributeValue(chatId)}">
        <div class="chat-item-icon">
          ${icons.CHAT_ITEM_ICON}
        </div>
        <div class="chat-item-body">
          <span class="chat-item-title">${escHtml(title)}</span>
          <span class="chat-item-date">${escHtml(dateStr)}</span>
        </div>
        <button class="chat-item-menu-btn" aria-label="Chat options">
          ${icons.CHAT_ITEM_MENU_ICON}
        </button>
      </a>
    `;
  }

  function setActiveChat(chatId) {
    dom.$historyList.find('.chat-item').removeClass('active').removeAttr('aria-current');
    if (!chatId) {
      return;
    }

    dom.$historyList
      .find(`.chat-item[data-chat-id="${chatId}"]`)
      .addClass('active')
      .attr('aria-current', 'page');
  }

  function clearActiveChat() {
    setActiveChat('');
  }

  function prependChatItem(chatId, title, dateStr) {
    dom.$historyList.find('.empty-state').remove();
    setActiveChat('');
    const $newItem = $(buildChatItemHtml(chatId, title, dateStr, true));
    dom.$historyList.prepend($newItem);
    return $newItem;
  }

  function removeChatItem(chatId) {
    dom.$historyList.find(`.chat-item[data-chat-id="${chatId}"]`).remove();
    ensureEmptyState();
  }

  function ensureEmptyState() {
    if (dom.$historyList.find('.chat-item:not(.empty-state)').length > 0) {
      return;
    }

    dom.$historyList.append('<div class="chat-item empty-state"><span class="chat-item-title">No previous chats</span></div>');
  }

  function openChatMenu($item, event) {
    event.preventDefault();
    event.stopPropagation();

    state.activeMenuTarget = $item;
    const rect = $item[0].getBoundingClientRect();
    dom.$chatItemDropdown.css({
      top: rect.bottom + window.scrollY + 2,
      left: rect.left + window.scrollX,
      minWidth: rect.width
    }).show();
  }

  function closeChatMenu() {
    dom.$chatItemDropdown.hide();
    state.activeMenuTarget = null;
  }

  function toggleChatMenu($item, event) {
    if (state.activeMenuTarget && state.activeMenuTarget.is($item)) {
      closeChatMenu();
      return;
    }

    openChatMenu($item, event);
  }

  function getActiveMenuTarget() {
    return state.activeMenuTarget;
  }

  return {
    buildChatItemHtml,
    clearActiveChat,
    closeChatMenu,
    ensureEmptyState,
    getActiveMenuTarget,
    openChatMenu,
    prependChatItem,
    removeChatItem,
    setActiveChat,
    toggleChatMenu
  };
}
