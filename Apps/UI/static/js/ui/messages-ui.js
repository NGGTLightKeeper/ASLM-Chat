// Copyright NGGT.LightKeeper. All Rights Reserved.

import { escHtml, escapeAttributeValue, timeNow } from '../main/utils.js';

// Message UI.
// Create helpers for rendering messages, activity timelines, and message actions.
export function createMessagesUi(context, dependencies) {
  const { attachmentUi, toolInspector } = dependencies;
  const { dom, icons, state } = context;

  // Composer state.
  // Sync both send buttons with the current generation and attachment state.
  function updateSendButtons() {
    if (state.isChatGenerating) {
      dom.$sendBtn.prop('disabled', false).addClass('stop-btn').html(icons.STOP_ICON).attr('aria-label', 'Stop generation');
      dom.$sendBtnConv.prop('disabled', false).addClass('stop-btn').html(icons.STOP_ICON).attr('aria-label', 'Stop generation');

      return;
    }

    const hasPendingAttachments = state.attachmentState.pending.length > 0;

    dom.$sendBtn
      .removeClass('stop-btn')
      .html(icons.SEND_ICON)
      .attr('aria-label', 'Send Message')
      .prop('disabled', !dom.$chatInput.val().trim() && !hasPendingAttachments);

    dom.$sendBtnConv
      .removeClass('stop-btn')
      .html(icons.SEND_ICON)
      .attr('aria-label', 'Send Message')
      .prop('disabled', !dom.$chatInputConv.val().trim() && !hasPendingAttachments);
  }

  // Show regen buttons only on the latest assistant exchange.
  function updateRegenButtons() {
    dom.$messagesInner.find('.msg-regen-btn').hide();

    const $lastAssistant = dom.$messagesInner.find('.msg.assistant').last();
    if (!$lastAssistant.length) {
      return;
    }

    $lastAssistant.find('.msg-regen-btn').show();

    const $prev = $lastAssistant.prev('.msg.user');
    if ($prev.length) {
      $prev.find('.msg-regen-btn').show();
    }
  }

  // Scroll the message area to the bottom.
  function scrollBottom() {
    dom.$messagesArea.scrollTop(dom.$messagesArea[0].scrollHeight);
  }


  // Markdown rendering.
  // Render one visible text segment as sanitized HTML.
  function renderMarkdownSegment(content) {
    if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
      return escHtml(content);
    }

    return DOMPurify.sanitize(marked.parse(content));
  }


  // Activity parsing.
  // Parse model output into visible text, thoughts, and tool events.
  function parseMessageTimeline(rawText) {
    const source = String(rawText || '');
    const segments = [];
    const toolSegmentByAlias = {};
    let cursor = 0;

    // Strip control tokens that should never reach the visible transcript.
    function sanitizeVisibleText(value) {
      return String(value || '')
        .replace(/<\|start\|>\s*(assistant|user|system)?\s*(<\|channel\|>\s*(final|analysis|commentary))?\s*(<\|message\|>)?/gi, '')
        .replace(/<\|start\|>/gi, '')
        .replace(/<\|channel\|>\s*(final|analysis|commentary)/gi, '')
        .replace(/<\|message\|>/gi, '')
        .replace(/<\|return\|>/gi, '')
        .replace(/<\|startoftext\|>/gi, '')
        .replace(/<\|im_(start|end)\|>/gi, '')
        .replace(/<\|(assistant|user|system|endoftext)\|>/gi, '');
    }

    // Append a visible text segment if anything readable remains.
    function pushTextSegment(value) {
      const sanitizedValue = sanitizeVisibleText(value);
      if (!sanitizedValue || !sanitizedValue.trim()) {
        return;
      }

      segments.push({ type: 'text', content: sanitizedValue });
    }

    while (cursor < source.length) {
      const thinkStart = source.indexOf('<think>', cursor);
      const toolCallStart = source.indexOf('<tool_call>', cursor);
      const toolResultStart = source.indexOf('<tool_result>', cursor);
      const candidates = [
        thinkStart !== -1 ? { pos: thinkStart, kind: 'thought' } : null,
        toolCallStart !== -1 ? { pos: toolCallStart, kind: 'tool' } : null,
        toolResultStart !== -1 ? { pos: toolResultStart, kind: 'result' } : null
      ].filter(Boolean);

      if (candidates.length === 0) {
        pushTextSegment(source.substring(cursor));
        break;
      }

      candidates.sort(function sortCandidates(left, right) {
        return left.pos - right.pos;
      });

      const next = candidates[0];

      if (next.pos > cursor) {
        pushTextSegment(source.substring(cursor, next.pos));
      }

      if (next.kind === 'thought') {
        const thinkEnd = source.indexOf('</think>', next.pos + 7);
        if (thinkEnd === -1) {
          const content = sanitizeVisibleText(source.substring(next.pos + 7)).trim();
          if (content) {
            segments.push({ type: 'thought', content });
          }
          break;
        }

        const content = sanitizeVisibleText(source.substring(next.pos + 7, thinkEnd)).trim();
        if (content) {
          segments.push({ type: 'thought', content });
        }

        cursor = thinkEnd + 8;
        continue;
      }

      if (next.kind === 'tool') {
        const toolEnd = source.indexOf('</tool_call>', next.pos + 11);
        if (toolEnd === -1) {
          break;
        }

        const payload = source.substring(next.pos + 11, toolEnd);

        try {
          const parsed = JSON.parse(payload);
          const alias = String(parsed.alias || '').trim();
          const segment = {
            type: 'tool',
            alias,
            serverId: String(parsed.server_id || '').trim(),
            serverName: String(parsed.server_name || '').trim(),
            toolId: String(parsed.tool_id || '').trim(),
            toolName: String(parsed.tool_name || '').trim(),
            arguments: parsed.arguments && typeof parsed.arguments === 'object' ? parsed.arguments : {},
            result: null
          };

          segments.push(segment);

          if (alias) {
            toolSegmentByAlias[alias] = segment;
          }
        } catch (_error) {
          // Ignore malformed tool payloads.
        }

        cursor = toolEnd + 12;
        continue;
      }

      const resultEnd = source.indexOf('</tool_result>', next.pos + 13);
      if (resultEnd === -1) {
        break;
      }

      const payload = source.substring(next.pos + 13, resultEnd);

      try {
        const parsed = JSON.parse(payload);
        const alias = String(parsed.alias || '').trim();
        const target = toolSegmentByAlias[alias];

        if (target) {
          target.result = String(parsed.content || '');
        }
      } catch (_error) {
        // Ignore malformed tool results.
      }

      cursor = resultEnd + 14;
    }

    const visibleText = segments
      .filter(function onlyText(segment) { return segment.type === 'text'; })
      .map(function mapText(segment) { return segment.content; })
      .join('\n\n')
      .trim();

    return { segments, visibleText };
  }


  // Thought state helpers.
  // Read the set of expanded thought indices for one row.
  function getExpandedThoughtIndices($msgRow) {
    const rawValue = String($msgRow.attr('data-expanded-thoughts') || '').trim();
    if (!rawValue) {
      return new Set();
    }

    return new Set(
      rawValue
        .split(',')
        .map(function toNumber(value) { return parseInt(value, 10); })
        .filter(function isValid(value) { return Number.isInteger(value) && value >= 0; })
    );
  }

  // Persist the expanded thought set back to the row element.
  function setExpandedThoughtIndices($msgRow, expandedIndices) {
    const normalized = Array.from(expandedIndices)
      .filter(function isValid(value) { return Number.isInteger(value) && value >= 0; })
      .sort(function sortValues(left, right) { return left - right; });

    if (normalized.length === 0) {
      $msgRow.removeAttr('data-expanded-thoughts');
      return;
    }

    $msgRow.attr('data-expanded-thoughts', normalized.join(','));
  }


  // Activity timeline rendering.
  // Render thoughts, tool calls, and visible text into the assistant timeline.
  function renderActivityTimeline($msgRow, segments) {
    const $stream = $msgRow.find('.msg-activity-stream');
    const $bubble = $msgRow.find('.msg-bubble');

    if (!$stream.length) {
      return;
    }

    if (!Array.isArray(segments) || segments.length === 0) {
      $stream.hide().empty();
      $bubble.html('');
      $msgRow.removeAttr('data-expanded-thoughts');
      return;
    }

    const expandedThoughts = getExpandedThoughtIndices($msgRow);
    let thoughtIndex = -1;
    let toolSegmentIndex = 0;
    const toolSegments = segments.filter(function onlyToolSegments(segment) {
      return segment.type === 'tool';
    });

    const html = segments.map(function renderSegment(segment) {
      if (segment.type === 'thought') {
        thoughtIndex += 1;
        const isExpanded = expandedThoughts.has(thoughtIndex);

        return `
          <div class="msg-thoughts-wrapper${isExpanded ? ' expanded' : ''}" data-thought-index="${thoughtIndex}">
            <div class="msg-thoughts-toggle">Thought Process</div>
            <div class="msg-thoughts-content" style="display:${isExpanded ? 'block' : 'none'};">${escHtml(segment.content)}</div>
          </div>
        `;
      }

      if (segment.type === 'tool') {
        const label = escHtml(segment.toolName || segment.alias || segment.toolId || 'Tool');
        const badge = escHtml(segment.serverName || segment.serverId || 'server');
        const hasResult = segment.result !== null && segment.result !== undefined;
        const statusDot = hasResult
          ? '<span class="msg-tool-call-dot msg-tool-call-dot--done"></span>'
          : '<span class="msg-tool-call-dot msg-tool-call-dot--pending"></span>';

        return `
          <div class="msg-tool-call-card" data-tool-segment-index="${toolSegmentIndex++}">
            <div class="msg-tool-call-main">
              ${statusDot}
              <div class="msg-tool-call-name">${label}</div>
            </div>
            <div class="msg-tool-call-badge">${badge}</div>
          </div>
        `;
      }

      return `
        <div class="msg-stream-text">
          <div class="markdown-body">${renderMarkdownSegment(segment.content)}</div>
        </div>
      `;
    }).join('');

    $bubble.empty();
    $stream.html(html).show();
    setExpandedThoughtIndices($msgRow, expandedThoughts);

    $stream.find('.msg-tool-call-card[data-tool-segment-index]').each(function bindToolInspector() {
      const index = parseInt($(this).attr('data-tool-segment-index'), 10);
      const segment = toolSegments[index];

      if (!segment) {
        return;
      }

      $(this).on('click', function openInspector() {
        toolInspector.open(segment);
      });
    });
  }

  // Parse and render one assistant transcript string.
  function renderMessageHtml($msgRow, rawText) {
    const parsed = parseMessageTimeline(rawText);
    renderActivityTimeline($msgRow, parsed.segments);
    $msgRow.find('.msg-bubble').attr('data-raw', rawText).attr('data-copy', parsed.visibleText);
  }


  // Message row rendering.
  // Append one user or assistant message to the stream.
  function appendMessage(role, text, attachments, timestamp, options) {
    const viewOptions = options || {};
    const isUser = role === 'user';
    const label = isUser ? 'You' : 'ASLM';
    const timeStr = timeNow(timestamp);
    const queuedBadge = isUser && viewOptions.queued
      ? '<span class="msg-status-pill">Queued</span>'
      : '';
    const messageKey = viewOptions.messageKey || '';
    const messageId = viewOptions.messageId || '';

    let attachmentsHtml = '';

    if (isUser && attachments && attachments.length > 0) {
      const imageHtml = attachments
        .filter(function onlyImages(attachment) {
          return typeof attachment === 'string' || attachment.kind === 'image';
        })
        .map(function renderImage(attachment) {
          const normalizedAttachment = attachmentUi.normalizeAttachment(attachment);
          const src = normalizedAttachment ? normalizedAttachment.dataUrl : '';
          return `<img src="${src}" alt="Attached image">`;
        }).join('');

      const fileHtml = attachments
        .filter(function onlyFiles(attachment) {
          return typeof attachment !== 'string' && attachment.kind === 'file';
        })
        .map(function renderFile(attachment) {
          return `
            <div class="msg-file-chip">
              <div class="msg-file-name">${escHtml(attachment.name || 'File')}</div>
              <div class="msg-file-meta">${escHtml(attachment.mimeType || attachment.mime_type || 'application/octet-stream')}</div>
            </div>
          `;
        }).join('');

      attachmentsHtml = `
        ${imageHtml ? `<div class="msg-images">${imageHtml}</div>` : ''}
        ${fileHtml ? `<div class="msg-files">${fileHtml}</div>` : ''}
      `;
    }

    const $row = $(`
      <div class="msg ${role}${viewOptions.queued ? ' is-queued' : ''}" data-message-key="${escapeAttributeValue(messageKey)}"${messageId ? ` data-message-id="${messageId}"` : ''}>
        <div class="msg-avatar">${isUser ? 'U' : 'A'}</div>
        <div class="msg-body">
          <div class="msg-meta">
            <span>${label}</span>
            <span>${timeStr}</span>
            ${queuedBadge}
          </div>
          ${!isUser ? '<div class="msg-activity-stream" style="display:none;"></div>' : ''}
          <div class="msg-bubble">${attachmentsHtml}</div>
          ${icons.buildMessageActionsHtml()}
        </div>
      </div>
    `);

    if (isUser) {
      $row.find('.msg-bubble')
        .attr('data-raw', text)
        .attr('data-attachments', JSON.stringify(attachments || []))
        .append($('<span>').text(text));
    } else if (Array.isArray(viewOptions.activitySegments) && viewOptions.activitySegments.length > 0) {
      $row.find('.msg-bubble').attr('data-raw', text);
      renderActivityTimeline($row, viewOptions.activitySegments);
    } else {
      renderMessageHtml($row, text);
    }

    dom.$messagesInner.append($row);
    updateRegenButtons();
    scrollBottom();
    return $row;
  }

  // Toggle the queued badge for one user row.
  function setQueuedMessageState($row, queued) {
    if (!$row || !$row.length) {
      return;
    }

    $row.toggleClass('is-queued', !!queued);

    const $meta = $row.find('.msg-meta');
    let $badge = $meta.find('.msg-status-pill');

    if (queued) {
      if (!$badge.length) {
        $badge = $('<span class="msg-status-pill">Queued</span>');
        $meta.append($badge);
      }
    } else {
      $badge.remove();
    }
  }

  // Append a temporary assistant typing row.
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
          <div class="msg-activity-stream" style="display:none;"></div>
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

    dom.$messagesInner.append($row);
    return $row;
  }


  // Clipboard helpers.
  // Copy text using the legacy textarea fallback.
  function fallbackCopy(text, onSuccess) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.cssText = 'position:fixed;top:-9999px;left:-9999px;opacity:0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();

    try {
      if (document.execCommand('copy')) {
        onSuccess && onSuccess();
      }
    } catch (_error) {
      // Ignore legacy clipboard errors.
    }

    document.body.removeChild(textarea);
  }

  // Copy the visible message content to the clipboard.
  function copyMessage($button) {
    const $btn = $button || $();
    const $bubble = $btn.closest('.msg-body').find('.msg-bubble');
    const text = $bubble.attr('data-copy') || $bubble.attr('data-raw') || $bubble.text();

    // Swap the icon briefly to confirm the copy action.
    function onCopied() {
      const originalHtml = $btn.html();
      $btn.html(icons.COPIED_ICON);
      setTimeout(function restoreIcon() {
        $btn.html(originalHtml);
      }, 1200);
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(onCopied).catch(function fallback() {
        fallbackCopy(text, onCopied);
      });
      return;
    }

    fallbackCopy(text, onCopied);
  }


  // Thought UI.
  // Toggle one collapsible thought block.
  function toggleThoughtSection($toggle) {
    const $wrapper = $toggle.closest('.msg-thoughts-wrapper');
    const $row = $toggle.closest('.msg');
    const $content = $wrapper.find('.msg-thoughts-content');
    const thoughtIndex = parseInt($wrapper.attr('data-thought-index') || '-1', 10);
    const expandedThoughts = getExpandedThoughtIndices($row);
    const willExpand = !$wrapper.hasClass('expanded');

    if (Number.isInteger(thoughtIndex) && thoughtIndex >= 0) {
      if (willExpand) {
        expandedThoughts.add(thoughtIndex);
      } else {
        expandedThoughts.delete(thoughtIndex);
      }

      setExpandedThoughtIndices($row, expandedThoughts);
    }

    $wrapper.toggleClass('expanded', willExpand);
    $content.stop(true, true)[willExpand ? 'slideDown' : 'slideUp'](160);
  }


  // Markdown configuration.
  // Configure marked + highlight.js when both libraries are available.
  function configureMarkdown() {
    if (typeof marked === 'undefined' || typeof hljs === 'undefined') {
      return;
    }

    marked.setOptions({
      highlight(code, lang) {
        const language = hljs.getLanguage(lang) ? lang : 'plaintext';
        return hljs.highlight(code, { language }).value;
      },
      breaks: true
    });
  }

  return {
    appendMessage,
    appendTyping,
    configureMarkdown,
    copyMessage,
    renderMessageHtml,
    scrollBottom,
    setQueuedMessageState,
    toggleThoughtSection,
    updateRegenButtons,
    updateSendButtons
  };
}
