// Copyright NGGT.LightKeeper. All Rights Reserved.

import { escHtml, escapeAttributeValue } from '/static/js/main/utils.js';

// Chat history UI.
// Create helpers for the sidebar chat list and menu.
export function createChatHistoryUi(context) {
  const { dom, icons, state } = context;

  // Chat item rendering.
  // Build one chat row HTML fragment.
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

  // Highlight the active chat row.
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

  // Clear the active chat highlight.
  function clearActiveChat() {
    setActiveChat('');
  }

  // Insert one chat item at the top of the list.
  function prependChatItem(chatId, title, dateStr) {
    dom.$historyList.find('.empty-state').remove();
    setActiveChat('');

    const $newItem = $(buildChatItemHtml(chatId, title, dateStr, true));
    dom.$historyList.prepend($newItem);
    return $newItem;
  }

  // Remove one chat item from the list.
  function removeChatItem(chatId) {
    dom.$historyList.find(`.chat-item[data-chat-id="${chatId}"]`).remove();
    ensureEmptyState();
  }

  // Restore the empty state when no chats remain.
  function ensureEmptyState() {
    if (dom.$historyList.find('.chat-item:not(.empty-state)').length > 0) {
      return;
    }

    dom.$historyList.append('<div class="chat-item empty-state"><span class="chat-item-title">No previous chats</span></div>');
  }


  // Chat item menu.
  // Open the floating menu for one chat item.
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

  // Close the floating chat menu.
  function closeChatMenu() {
    dom.$chatItemDropdown.hide();
    state.activeMenuTarget = null;
  }

  // Toggle the chat menu for one sidebar row.
  function toggleChatMenu($item, event) {
    if (state.activeMenuTarget && state.activeMenuTarget.is($item)) {
      closeChatMenu();
      return;
    }

    openChatMenu($item, event);
  }

  // Read the row currently bound to the chat menu.
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
