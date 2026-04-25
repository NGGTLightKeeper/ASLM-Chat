// Copyright NGGT.LightKeeper. All Rights Reserved.

import { escHtml, escapeAttributeValue, timeNow } from '../main/utils.js';

// Message UI.
// Create helpers for rendering messages, activity timelines, and message actions.
export function createMessagesUi(context, dependencies) {
  const { attachmentUi, toolInspector } = dependencies;
  const { dom, icons, state } = context;
  const MORE_LABEL = '\u0415\u0449\u0435';
  const HIDE_LABEL = '\u0421\u043a\u0440\u044b\u0442\u044c';
  const SEARCH_BATCH_FIRST_CALL_HOLD_MS = 0;
  const SEARCH_BATCH_MULTI_CALL_SETTLE_MS = 0;

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
  function renderMarkdownSegment(content, citationSources) {
    const hasCitationSources = citationSources && typeof citationSources === 'object' && Object.keys(citationSources).length > 0;
    const visibleContent = hasCitationSources
      ? String(content || '')
      : String(content || '').replace(/\s*\[(?:S\d+|source-(?:[a-z0-9]+-)?\d+|c[a-z0-9]{3}-\d+)\]/gi, '');
    if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
      return decorateCitationsInHtml(escHtml(visibleContent), citationSources);
    }

    return decorateCitationsInHtml(DOMPurify.sanitize(marked.parse(visibleContent)), citationSources);
  }

  // Render text cheaply while a message is still streaming.
  function renderPlainTextSegment(content) {
    return escHtml(content);
  }

  function normalizeCitationId(value) {
    return String(value || '').trim().toUpperCase();
  }

  function sourceDisplayDomain(source) {
    const candidate = String(source.display_domain || source.domain || '').trim();
    if (candidate) {
      return candidate;
    }

    try {
      return new URL(String(source.url || '')).hostname.replace(/^www\./i, '');
    } catch (_error) {
      return '';
    }
  }

  function safeExternalUrl(value) {
    const rawValue = String(value || '').trim();
    if (!rawValue) {
      return '';
    }

    try {
      const parsed = new URL(rawValue);
      return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : '';
    } catch (_error) {
      return '';
    }
  }

  function sourceHasExtractedPreview(source) {
    const safeSource = source && typeof source === 'object' ? source : {};
    const hasPreviewField = Object.prototype.hasOwnProperty.call(safeSource, 'preview');
    const hasSnippetField = Object.prototype.hasOwnProperty.call(safeSource, 'snippet');
    if (!hasPreviewField && !hasSnippetField) {
      return true;
    }

    const preview = String(safeSource.preview || '').trim();
    const snippet = String(safeSource.snippet || '').trim();
    return !!preview && preview !== snippet;
  }

  function sourceFaviconUrl(source) {
    if (!sourceHasExtractedPreview(source)) {
      return '';
    }

    return safeExternalUrl(source.favicon_url);
  }

  function domainAccentStyle(value, extraStyle) {
    const text = String(value || '').trim().toLowerCase();
    let hash = 0;
    for (let index = 0; index < text.length; index += 1) {
      hash = ((hash << 5) - hash) + text.charCodeAt(index);
      hash |= 0;
    }

    const hue = Math.abs(hash) % 360;
    const base = `--msg-source-accent-bg: hsla(${hue}, 68%, 46%, 0.36); --msg-source-accent-fg: hsl(${hue}, 86%, 82%);`;
    return extraStyle ? `${base} ${extraStyle}` : base;
  }

  function renderCitationChip(source, sourceId) {
    const safeSource = source && typeof source === 'object' ? source : {};
    const normalizedId = normalizeCitationId(sourceId || safeSource.id);
    const sourceUrl = safeExternalUrl(safeSource.url);
    if (!normalizedId || !sourceUrl) {
      return escHtml(`[${normalizedId || sourceId}]`);
    }

    const domain = sourceDisplayDomain(safeSource) || normalizedId;
    const title = String(safeSource.title || domain || normalizedId).trim();
    const faviconUrl = sourceFaviconUrl(safeSource);
    const fallbackLetter = domain.charAt(0).toUpperCase();
    const faviconHtml = faviconUrl
      ? `<img class="msg-citation-favicon" src="${escapeAttributeValue(faviconUrl)}" alt="" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='inline-flex';">`
      : '';
    const fallbackStyle = domainAccentStyle(domain, faviconUrl ? 'display:none;' : '');

    return `
      <a class="msg-citation-chip" href="${escapeAttributeValue(sourceUrl)}" target="_blank" rel="noopener noreferrer" title="${escapeAttributeValue(title)}">
        ${faviconHtml}<span class="msg-citation-fallback" style="${escapeAttributeValue(fallbackStyle)}">${escHtml(fallbackLetter)}</span>
        <span class="msg-citation-domain">${escHtml(domain)}</span>
      </a>
    `;
  }

  function decorateCitationsInHtml(html, citationSources) {
    if (!citationSources || typeof citationSources !== 'object' || Object.keys(citationSources).length === 0) {
      return html;
    }

    const template = document.createElement('template');
    template.innerHTML = html;
    const citationPattern = /\[((?:S\d+)|(?:source-(?:[a-z0-9]+-)?\d+)|(?:c[a-z0-9]{3}-\d+))\]/gi;
    const ignoredTags = new Set(['A', 'CODE', 'PRE', 'SCRIPT', 'STYLE', 'TEXTAREA']);

    function appendChip(fragment, source, sourceId) {
      const chipTemplate = document.createElement('template');
      chipTemplate.innerHTML = renderCitationChip(source, sourceId).trim();
      fragment.appendChild(chipTemplate.content.cloneNode(true));
    }

    function walk(node) {
      if (!node) {
        return;
      }

      if (node.nodeType === Node.ELEMENT_NODE && ignoredTags.has(node.tagName)) {
        return;
      }

      if (node.nodeType === Node.TEXT_NODE) {
        const value = node.nodeValue || '';
        citationPattern.lastIndex = 0;
        if (!citationPattern.test(value)) {
          return;
        }

        citationPattern.lastIndex = 0;
        const fragment = document.createDocumentFragment();
        let lastIndex = 0;
        let match = citationPattern.exec(value);

        while (match) {
          const sourceId = normalizeCitationId(match[1]);
          const source = citationSources[sourceId];
          if (match.index > lastIndex) {
            fragment.appendChild(document.createTextNode(value.slice(lastIndex, match.index)));
          }
          if (source) {
            appendChip(fragment, source, sourceId);
          }
          lastIndex = match.index + match[0].length;
          match = citationPattern.exec(value);
        }

        if (lastIndex === 0) {
          return;
        }

        if (lastIndex < value.length) {
          fragment.appendChild(document.createTextNode(value.slice(lastIndex)));
        }
        node.parentNode.replaceChild(fragment, node);
        return;
      }

      Array.from(node.childNodes).forEach(walk);
    }

    Array.from(template.content.childNodes).forEach(walk);
    return template.innerHTML;
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
          target.toolUi = parsed.tool_ui && typeof parsed.tool_ui === 'object' ? parsed.tool_ui : null;
          target.structuredContent = parsed.structured_content && typeof parsed.structured_content === 'object'
            ? parsed.structured_content
            : null;
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
  function isSearchToolSegment(segment) {
    const toolId = String(segment.toolId || '').toLowerCase();
    const alias = String(segment.alias || '').toLowerCase();
    return toolId === 'web_search'
      || toolId === 'web_search_rich'
      || alias.endsWith('__web_search')
      || alias.endsWith('__web_search_rich')
      || !!(segment.toolUi && segment.toolUi.compact);
  }

  function searchQueryFromSegment(segment) {
    const args = segment.arguments && typeof segment.arguments === 'object' ? segment.arguments : {};
    return String(args.query || args.q || '').trim();
  }

  function isReadPageToolSegment(segment) {
    const toolId = String(segment.toolId || '').toLowerCase();
    const alias = String(segment.alias || '').toLowerCase();
    const uiKind = segment.toolUi && segment.toolUi.kind ? String(segment.toolUi.kind).toLowerCase() : '';
    return toolId === 'read_page'
      || alias.endsWith('__read_page')
      || uiKind === 'read_page';
  }

  function sourceFromUrl(value, rank) {
    const rawUrl = String(value || '').trim();
    if (!rawUrl) {
      return null;
    }

    let domain = '';
    try {
      domain = new URL(rawUrl).hostname.replace(/^www\./i, '');
    } catch (_error) {
      domain = rawUrl.replace(/^https?:\/\//i, '').split('/')[0].replace(/^www\./i, '');
    }

    const parts = domain.split('.').filter(Boolean);
    const label = parts.length >= 2 ? parts[parts.length - 2] : (parts[0] || domain);
    const displayDomain = label.replace(/-/g, ' ').replace(/\b\w/g, function titleCase(letter) {
      return letter.toUpperCase();
    });

    return {
      rank: rank || 0,
      url: rawUrl,
      domain,
      display_domain: displayDomain || domain,
      favicon_url: domain ? `https://icons.duckduckgo.com/ip3/${domain}.ico` : '',
    };
  }

  function searchSourcesFromSegment(segment) {
    const structured = segment.structuredContent && typeof segment.structuredContent === 'object'
      ? segment.structuredContent
      : null;
    if (structured && Array.isArray(structured.sources) && structured.sources.length > 0) {
      return structured.sources;
    }

    const compact = segment.toolUi && segment.toolUi.compact && typeof segment.toolUi.compact === 'object'
      ? segment.toolUi.compact
      : null;
    return compact && Array.isArray(compact.source_chips) ? compact.source_chips : [];
  }

  function readPageSourcesFromSegment(segment) {
    const structured = segment.structuredContent && typeof segment.structuredContent === 'object'
      ? segment.structuredContent
      : null;
    const uiSources = segment.toolUi && Array.isArray(segment.toolUi.sources) ? segment.toolUi.sources : [];
    if (uiSources.length > 0) {
      return uiSources;
    }
    if (structured && Array.isArray(structured.sources) && structured.sources.length > 0) {
      return structured.sources;
    }

    const args = segment.arguments && typeof segment.arguments === 'object' ? segment.arguments : {};
    const rawUrls = Array.isArray(args.url) ? args.url : [args.url || args.urls];
    return rawUrls
      .flatMap(function flattenUrls(item) { return Array.isArray(item) ? item : [item]; })
      .map(function mapUrl(item, index) { return sourceFromUrl(item, index + 1); })
      .filter(Boolean);
  }

  function addSearchSourcesToCitationRegistry(registry, segment) {
    searchSourcesFromSegment(segment).forEach(function registerSource(source) {
      if (!source || typeof source !== 'object') {
        return;
      }

      const sourceId = normalizeCitationId(source.id || source.source_id);
      if (!/^(?:S\d+|SOURCE-(?:[A-Z0-9]+-)?\d+|C[A-Z0-9]{3}-\d+)$/.test(sourceId)) {
        return;
      }

      registry[sourceId] = source;
    });
  }

  function renderSourceChip(chip) {
    const source = chip && typeof chip === 'object' ? chip : {};
    const domain = String(source.display_domain || source.domain || '').trim();
    if (!domain) {
      return '';
    }
    const faviconUrl = sourceFaviconUrl(source);
    const sourceUrl = String(source.url || '').trim();
    const fallbackLetter = domain.charAt(0).toUpperCase();
    const imgHtml = faviconUrl
      ? `<img class="msg-search-chip-favicon" src="${escapeAttributeValue(faviconUrl)}" alt="" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='inline-flex';">`
      : '';
    const fallbackStyle = domainAccentStyle(domain, faviconUrl ? 'display:none;' : '');
    const tagName = sourceUrl ? 'a' : 'span';
    const linkAttrs = sourceUrl
      ? ` href="${escapeAttributeValue(sourceUrl)}" target="_blank" rel="noopener noreferrer"`
      : '';
    return `
      <${tagName} class="msg-search-chip" title="${escapeAttributeValue(source.title || domain)}"${linkAttrs}>
        ${imgHtml}<span class="msg-search-chip-fallback" style="${escapeAttributeValue(fallbackStyle)}">${escHtml(fallbackLetter)}</span>
        <span class="msg-search-chip-domain">${escHtml(domain)}</span>
      </${tagName}>
    `;
  }

  function dedupeSearchSources(sources) {
    const seen = {};
    return (Array.isArray(sources) ? sources : []).filter(function keepFirstSource(source) {
      if (!source || typeof source !== 'object') {
        return false;
      }

      const key = String(source.domain || source.display_domain || source.url || source.source_id || source.id || '').trim().toLowerCase();
      if (!key || seen[key]) {
        return false;
      }

      seen[key] = true;
      return true;
    });
  }

  function renderSearchToolCard(segment, toolSegmentIndex, options) {
    const renderOptions = options || {};
    const hasResult = segment.result !== null && segment.result !== undefined;
    const compact = segment.toolUi && segment.toolUi.compact && typeof segment.toolUi.compact === 'object'
      ? segment.toolUi.compact
      : null;
    const query = searchQueryFromSegment(segment);
    const sources = searchSourcesFromSegment(segment);
    const visibleSources = sources.slice(0, 3);
    const hiddenSources = sources.slice(3);
    let label = '';
    if (renderOptions.compactLabel && query) {
      label = query;
    } else if (hasResult) {
      label = sources.length > 0 ? `Searched for ${query || 'sources'}` : `No sources found for ${query || 'sources'}`;
    } else {
      label = compact && compact.label ? String(compact.label) : `Searching for ${query || 'sources'}`;
    }
    const chipsHtml = visibleSources.map(renderSourceChip).join('');
    const hiddenChipsHtml = hiddenSources.map(renderSourceChip).join('');
    const moreCount = hiddenSources.length || (compact ? Math.max(0, parseInt(compact.more_count || 0, 10) || 0) : 0);
    const moreButtonAttrs = `type="button" data-search-more-count="${moreCount}" aria-expanded="false"`;
    const collapsedMoreHtml = moreCount > 0
      ? `<button class="msg-search-chip msg-search-chip--more msg-search-chip--more-collapsed" ${moreButtonAttrs}><span class="msg-search-chip-domain">${escHtml(`${MORE_LABEL} ${moreCount}`)}</span></button>`
      : '';
    const expandedMoreHtml = moreCount > 0
      ? `<button class="msg-search-chip msg-search-chip--more msg-search-chip--more-expanded" ${moreButtonAttrs}><span class="msg-search-chip-domain">${escHtml(HIDE_LABEL)}</span></button>`
      : '';
    const pendingHtml = hasResult ? '' : '<span class="msg-search-pending-dot"></span>';
    const status = segment.toolUi && segment.toolUi.status ? String(segment.toolUi.status) : '';
    const iconHtml = status === 'error' || status === 'timeout'
      ? (icons.WEB_SEARCH_ERROR_ICON || icons.GLOBE_ICON)
      : (icons.WEB_SEARCH_ICON || icons.GLOBE_ICON);

    return `
      <div class="msg-search-card${hasResult ? ' is-done' : ' is-pending'}${renderOptions.compactLabel ? ' msg-search-card--batch-item' : ''}" data-tool-segment-index="${toolSegmentIndex}">
        <div class="msg-search-line">
          ${renderOptions.hideIcon ? '' : `<span class="msg-search-icon">${iconHtml}</span>`}
          <span class="msg-search-label">${escHtml(label)}</span>
          ${pendingHtml}
        </div>
        ${chipsHtml || collapsedMoreHtml ? `<div class="msg-search-chips">${chipsHtml}${collapsedMoreHtml}</div>` : ''}
        ${hiddenChipsHtml || expandedMoreHtml ? `<div class="msg-search-extra-chips">${hiddenChipsHtml}${expandedMoreHtml}</div>` : ''}
      </div>
    `;
  }

  function renderSearchToolGroup(searchItems) {
    if (!Array.isArray(searchItems) || searchItems.length === 0) {
      return '';
    }

    if (searchItems.length === 1) {
      return renderSearchToolCard(searchItems[0].segment, searchItems[0].index);
    }

    const hasProblem = searchItems.some(function hasProblemStatus(item) {
      const status = item.segment.toolUi && item.segment.toolUi.status ? String(item.segment.toolUi.status) : '';
      return status === 'error' || status === 'timeout';
    });
    const iconHtml = hasProblem
      ? (icons.WEB_SEARCH_ERROR_ICON || icons.GLOBE_ICON)
      : (icons.WEB_SEARCH_ICON || icons.GLOBE_ICON);
    const activePendingIndex = searchItems.findIndex(function findPendingSearch(item) {
      return item.segment.result === null || item.segment.result === undefined;
    });
    const hasPending = activePendingIndex !== -1;
    const queriesHtml = searchItems.map(function renderBatchQuery(item, itemIndex) {
      const query = searchQueryFromSegment(item.segment);
      const compact = item.segment.toolUi && item.segment.toolUi.compact && typeof item.segment.toolUi.compact === 'object'
        ? item.segment.toolUi.compact
        : null;
      const label = query || (compact && compact.label ? String(compact.label).replace(/^Searching for\s+/i, '') : 'sources');
      const activeClass = itemIndex === activePendingIndex ? ' is-active' : '';
      const activeDot = itemIndex === activePendingIndex ? '<span class="msg-search-pending-dot"></span>' : '';
      return `<div class="msg-search-batch-query${activeClass}"><span class="msg-search-batch-query-text">${escHtml(label)}</span>${activeDot}</div>`;
    }).join('');
    const combinedSources = dedupeSearchSources(searchItems.flatMap(function collectSources(item) {
      return searchSourcesFromSegment(item.segment);
    }));
    const visibleSources = combinedSources.slice(0, 3);
    const hiddenSources = combinedSources.slice(3);
    const chipsHtml = visibleSources.map(renderSourceChip).join('');
    const hiddenChipsHtml = hiddenSources.map(renderSourceChip).join('');
    const moreCount = hiddenSources.length;
    const moreButtonAttrs = `type="button" data-search-more-count="${moreCount}" aria-expanded="false"`;
    const collapsedMoreHtml = moreCount > 0
      ? `<button class="msg-search-chip msg-search-chip--more msg-search-chip--more-collapsed" ${moreButtonAttrs}><span class="msg-search-chip-domain">${escHtml(`${MORE_LABEL} ${moreCount}`)}</span></button>`
      : '';
    const expandedMoreHtml = moreCount > 0
      ? `<button class="msg-search-chip msg-search-chip--more msg-search-chip--more-expanded" ${moreButtonAttrs}><span class="msg-search-chip-domain">${escHtml(HIDE_LABEL)}</span></button>`
      : '';
    const firstIndex = Number.isInteger(searchItems[0].index) ? searchItems[0].index : 0;

    return `
      <div class="msg-search-card msg-search-card--batch${hasPending ? ' is-pending' : ' is-done'}" data-tool-segment-index="${firstIndex}">
        <div class="msg-search-batch-head">
          <span class="msg-search-icon msg-search-batch-icon">${iconHtml}</span>
          <div class="msg-search-batch-queries">${queriesHtml}</div>
        </div>
        ${chipsHtml || collapsedMoreHtml ? `<div class="msg-search-chips msg-search-chips--batch">${chipsHtml}${collapsedMoreHtml}</div>` : ''}
        ${hiddenChipsHtml || expandedMoreHtml ? `<div class="msg-search-extra-chips msg-search-extra-chips--batch">${hiddenChipsHtml}${expandedMoreHtml}</div>` : ''}
      </div>
    `;
  }

  function renderReadPageToolCard(readItems) {
    const items = Array.isArray(readItems) ? readItems : [];
    const firstItem = items[0] || {};
    const sourcesByUrl = {};
    items.forEach(function collectSources(item) {
      readPageSourcesFromSegment(item.segment).forEach(function collectSource(source) {
        const key = String(source.url || source.domain || '').trim();
        if (key && !sourcesByUrl[key]) {
          sourcesByUrl[key] = source;
        }
      });
    });

    const sources = Object.keys(sourcesByUrl).map(function mapSource(key) { return sourcesByUrl[key]; });
    const chipsHtml = sources.map(renderSourceChip).join('');
    const resultCount = sources.length;
    const label = resultCount === 1 ? 'Read source:' : 'Read sources:';
    const status = firstItem.segment && firstItem.segment.toolUi && firstItem.segment.toolUi.status
      ? String(firstItem.segment.toolUi.status)
      : '';
    const iconHtml = status === 'error'
      ? (icons.WEB_SEARCH_ERROR_ICON || icons.GLOBE_ICON)
      : (icons.WEB_SEARCH_ICON || icons.GLOBE_ICON);
    const dataIndex = Number.isInteger(firstItem.index) ? ` data-tool-segment-index="${firstItem.index}"` : '';

    return `
      <div class="msg-read-page-card${status === 'error' ? ' is-error' : ' is-done'}"${dataIndex}>
        <div class="msg-read-page-line">
          <span class="msg-read-page-icon">${iconHtml}</span>
          <span class="msg-read-page-label">${escHtml(label)}</span>
        </div>
        ${chipsHtml ? `<div class="msg-read-page-chips">${chipsHtml}</div>` : ''}
      </div>
    `;
  }

  function renderActivityTimeline($msgRow, segments, options) {
    const renderOptions = options || {};
    const useMarkdown = renderOptions.markdown !== false;
    const $stream = $msgRow.find('.msg-activity-stream');
    const $bubble = $msgRow.find('.msg-bubble');

    if (!$stream.length) {
      return;
    }

    if (!Array.isArray(segments) || segments.length === 0) {
      $stream.hide().empty();
      $bubble.html('');
      $msgRow.removeAttr('data-expanded-thoughts');
      $msgRow.removeData('toolSegments');
      return;
    }

    const expandedThoughts = getExpandedThoughtIndices($msgRow);
    let thoughtIndex = -1;
    let toolSegmentIndex = 0;
    const citationRegistry = {};
    const toolSegments = segments.filter(function onlyToolSegments(segment) {
      return segment.type === 'tool';
    });

    const htmlParts = [];
    for (let segmentIndex = 0; segmentIndex < segments.length; segmentIndex += 1) {
      const segment = segments[segmentIndex];
      if (segment.type === 'thought') {
        thoughtIndex += 1;
        const isExpanded = expandedThoughts.has(thoughtIndex);

        htmlParts.push(`
          <div class="msg-thoughts-wrapper${isExpanded ? ' expanded' : ''}" data-thought-index="${thoughtIndex}">
            <div class="msg-thoughts-toggle">Thought Process</div>
            <div class="msg-thoughts-content" style="display:${isExpanded ? 'block' : 'none'};">${escHtml(segment.content)}</div>
          </div>
        `);
        continue;
      }

      if (segment.type === 'tool') {
        if (isSearchToolSegment(segment)) {
          const searchItems = [];
          while (
            segmentIndex < segments.length
            && segments[segmentIndex].type === 'tool'
            && isSearchToolSegment(segments[segmentIndex])
          ) {
            const searchSegment = segments[segmentIndex];
            searchItems.push({ segment: searchSegment, index: toolSegmentIndex++ });
            addSearchSourcesToCitationRegistry(citationRegistry, searchSegment);
            segmentIndex += 1;
          }
          segmentIndex -= 1;
          htmlParts.push(renderSearchToolGroup(searchItems));
          continue;
        }

        if (isReadPageToolSegment(segment)) {
          const readItems = [];
          while (
            segmentIndex < segments.length
            && segments[segmentIndex].type === 'tool'
            && isReadPageToolSegment(segments[segmentIndex])
          ) {
            readItems.push({ segment: segments[segmentIndex], index: toolSegmentIndex++ });
            segmentIndex += 1;
          }
          segmentIndex -= 1;
          htmlParts.push(renderReadPageToolCard(readItems));
          continue;
        }

        const label = escHtml(segment.toolName || segment.alias || segment.toolId || 'Tool');
        const badge = escHtml(segment.serverName || segment.serverId || 'server');
        const hasResult = segment.result !== null && segment.result !== undefined;
        const statusDot = hasResult
          ? '<span class="msg-tool-call-dot msg-tool-call-dot--done"></span>'
          : '<span class="msg-tool-call-dot msg-tool-call-dot--pending"></span>';

        htmlParts.push(`
          <div class="msg-tool-call-card" data-tool-segment-index="${toolSegmentIndex++}">
            <div class="msg-tool-call-main">
              ${statusDot}
              <div class="msg-tool-call-name">${label}</div>
            </div>
            <div class="msg-tool-call-badge">${badge}</div>
          </div>
        `);
        continue;
      }

      htmlParts.push(`
        <div class="msg-stream-text">
          <div class="markdown-body${useMarkdown ? '' : ' is-streaming'}">${useMarkdown ? renderMarkdownSegment(segment.content, citationRegistry) : renderPlainTextSegment(segment.content)}</div>
        </div>
      `);
    }
    const html = htmlParts.join('');

    $bubble.empty();
    $stream.html(html).show();
    setExpandedThoughtIndices($msgRow, expandedThoughts);
    $msgRow.data('toolSegments', toolSegments);
  }

  function searchSegmentCount(segments) {
    return (Array.isArray(segments) ? segments : []).filter(function onlySearchSegment(segment) {
      return segment && segment.type === 'tool' && isSearchToolSegment(segment);
    }).length;
  }

  function clearSearchBatchHold($msgRow) {
    const holdState = $msgRow.data('searchBatchHoldState');
    if (holdState && holdState.timer) {
      window.clearTimeout(holdState.timer);
    }

    $msgRow.removeData('searchBatchHoldState');
    $msgRow.removeData('searchBatchHoldRaw');
  }

  function shouldHoldStreamingSearchBatch($msgRow, parsed, rawText) {
    const count = searchSegmentCount(parsed.segments);
    if (count === 0) {
      clearSearchBatchHold($msgRow);
      return false;
    }

    const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
    const holdState = $msgRow.data('searchBatchHoldState') || {};
    if (holdState.count !== count) {
      holdState.count = count;
      holdState.changedAt = now;
    }
    if (!holdState.changedAt) {
      holdState.changedAt = now;
    }

    const holdMs = count <= 1 ? SEARCH_BATCH_FIRST_CALL_HOLD_MS : SEARCH_BATCH_MULTI_CALL_SETTLE_MS;
    const remaining = holdMs - (now - holdState.changedAt);
    $msgRow.data('searchBatchHoldRaw', rawText);

    if (remaining <= 0) {
      if (holdState.timer) {
        window.clearTimeout(holdState.timer);
        holdState.timer = null;
      }
      $msgRow.data('searchBatchHoldState', holdState);
      return false;
    }

    if (holdState.timer) {
      window.clearTimeout(holdState.timer);
    }
    holdState.timer = window.setTimeout(function renderHeldSearchBatch() {
      const latestRaw = $msgRow.data('searchBatchHoldRaw');
      const latestState = $msgRow.data('searchBatchHoldState') || {};
      latestState.timer = null;
      $msgRow.data('searchBatchHoldState', latestState);
      renderMessageStream($msgRow, latestRaw || rawText);
    }, Math.max(0, remaining + 16));
    $msgRow.data('searchBatchHoldState', holdState);
    return true;
  }

  // Parse and render one assistant transcript string.
  function renderMessageHtml($msgRow, rawText) {
    clearSearchBatchHold($msgRow);
    const parsed = parseMessageTimeline(rawText);
    renderActivityTimeline($msgRow, parsed.segments);
    $msgRow.find('.msg-bubble').attr('data-raw', rawText).attr('data-copy', parsed.visibleText);
  }

  // Parse and render one assistant transcript during active streaming.
  function renderMessageStream($msgRow, rawText) {
    const parsed = parseMessageTimeline(rawText);
    if (shouldHoldStreamingSearchBatch($msgRow, parsed, rawText)) {
      $msgRow.find('.msg-bubble').attr('data-raw', rawText).attr('data-copy', parsed.visibleText);
      return;
    }

    renderActivityTimeline($msgRow, parsed.segments, { markdown: false });
    $msgRow.find('.msg-bubble').attr('data-raw', rawText).attr('data-copy', parsed.visibleText);
  }

  // Open the inspector for a delegated tool-card click.
  function openToolInspectorFromCard($card) {
    const index = parseInt($card.attr('data-tool-segment-index') || '-1', 10);
    if (!Number.isInteger(index) || index < 0) {
      return;
    }

    const toolSegments = $card.closest('.msg').data('toolSegments') || [];
    const segment = toolSegments[index];
    if (segment) {
      const toolDebugEnabled = state.runtimeSettings && (
        state.runtimeSettings.tool_output_debug === true
        || state.runtimeSettings.tool_output_debug === 'true'
        || state.runtimeSettings['tool-output-debug'] === true
        || state.runtimeSettings['tool-output-debug'] === 'true'
      );
      if (isSearchToolSegment(segment) && !toolDebugEnabled) {
        return;
      }
      toolInspector.open(segment);
    }
  }

  function toggleSearchSources($button) {
    const $card = $button.closest('.msg-search-card');
    const expanded = !$card.hasClass('is-expanded');
    const moreCount = parseInt($button.attr('data-search-more-count') || '0', 10) || 0;
    $card.toggleClass('is-expanded', expanded);
    $card.find('.msg-search-chip--more').attr('aria-expanded', expanded ? 'true' : 'false');
    $card.find('.msg-search-chip--more-collapsed .msg-search-chip-domain').text(`${MORE_LABEL} ${moreCount}`);
    $card.find('.msg-search-chip--more-expanded .msg-search-chip-domain').text(HIDE_LABEL);
  }


  // Message row rendering.
  // Build one user or assistant message row.
  function buildMessageRow(role, text, attachments, timestamp, options) {
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
      const $bubble = $row.find('.msg-bubble')
        .attr('data-raw', text)
        .append($('<span>').text(text));
      $bubble.data('attachments', attachments || []);
    } else if (Array.isArray(viewOptions.activitySegments) && viewOptions.activitySegments.length > 0) {
      $row.find('.msg-bubble').attr('data-raw', text);
      renderActivityTimeline($row, viewOptions.activitySegments);
    } else {
      renderMessageHtml($row, text);
    }

    return $row;
  }

  // Append one user or assistant message to the stream.
  function appendMessage(role, text, attachments, timestamp, options) {
    const viewOptions = options || {};
    const $row = buildMessageRow(role, text, attachments, timestamp, viewOptions);
    dom.$messagesInner.append($row);
    if (!viewOptions.deferSideEffects) {
      updateRegenButtons();
      scrollBottom();
    }
    return $row;
  }

  // Append a batch of stored messages with one DOM insertion.
  function appendMessages(messages, options) {
    const batchOptions = options || {};
    const rows = [];
    const fragment = document.createDocumentFragment();

    (messages || []).forEach(function buildStoredMessage(message) {
      const $row = buildMessageRow(
        message.role,
        message.text,
        message.attachments,
        message.timestamp,
        message.options || {}
      );
      rows.push($row);
      fragment.appendChild($row[0]);
    });

    dom.$messagesInner[0].appendChild(fragment);
    updateRegenButtons();
    if (batchOptions.scroll !== false) {
      scrollBottom();
    }
    return rows;
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
    appendMessages,
    appendTyping,
    configureMarkdown,
    copyMessage,
    openToolInspectorFromCard,
    renderMessageHtml,
    renderMessageStream,
    scrollBottom,
    setQueuedMessageState,
    toggleSearchSources,
    toggleThoughtSection,
    updateRegenButtons,
    updateSendButtons
  };
}
