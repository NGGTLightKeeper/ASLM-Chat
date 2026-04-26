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
  const PRE_TOOL_TEXT_HOLD_MS = 650;
  const WRITE_PREVIEW_COLLAPSED_LINES = 4;
  const WRITE_PREVIEW_EXPANDED_LINES = 80;
  const EDIT_PREVIEW_COLLAPSED_ROWS = 4;
  const EDIT_PREVIEW_EXPANDED_ROWS = 120;
  const SANDBOX_INPUT_PREVIEW_CHARS = 12000;
  const HEAVY_TOOL_ARGUMENT_KEYS = {
    bash: ['stdin'],
    edit: ['content', 'new_str', 'old_str'],
    write: ['content']
  };

  // Composer state.
  // Sync both send buttons with the current generation and attachment state.
  function updateSendButtons() {
    const hasPendingAttachments = state.attachmentState.pending.length > 0;

    function syncComposerButton($button, $input) {
      const hasDraft = !!String($input.val() || '').trim() || hasPendingAttachments;

      // During generation an empty composer acts as a stop button. As soon as
      // the user types or attaches something, the same button becomes an
      // enabled send button so follow-up messages can be queued instead of
      // feeling locked.
      if (state.isChatGenerating && !hasDraft) {
        $button
          .prop('disabled', false)
          .addClass('stop-btn')
          .html(icons.STOP_ICON)
          .attr('aria-label', 'Stop generation');
        return;
      }

      $button
        .removeClass('stop-btn')
        .html(icons.SEND_ICON)
        .attr('aria-label', state.isChatGenerating ? 'Queue message' : 'Send Message')
        .prop('disabled', !hasDraft);
    }

    syncComposerButton(dom.$sendBtn, dom.$chatInput);
    syncComposerButton(dom.$sendBtnConv, dom.$chatInputConv);
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

  function normalizeHighlightLanguage(language) {
    const raw = String(language || '').trim().toLowerCase();
    const aliases = {
      bash: 'bash',
      sh: 'bash',
      shell: 'bash',
      zsh: 'bash',
      ps1: 'powershell',
      py: 'python',
      python: 'python',
      js: 'javascript',
      jsx: 'javascript',
      mjs: 'javascript',
      cjs: 'javascript',
      ts: 'typescript',
      tsx: 'typescript',
      html: 'xml',
      xml: 'xml',
      css: 'css',
      scss: 'scss',
      json: 'json',
      jsonl: 'json',
      md: 'markdown',
      markdown: 'markdown',
      yaml: 'yaml',
      yml: 'yaml',
      diff: 'diff'
    };
    const normalized = aliases[raw] || raw || 'plaintext';
    if (typeof hljs !== 'undefined' && hljs.getLanguage && hljs.getLanguage(normalized)) {
      return normalized;
    }
    return 'plaintext';
  }

  function languageFromPath(path, fallback) {
    const cleanPath = String(path || '').split(/[?#]/)[0];
    const baseName = cleanPath.split(/[\\/]/).pop().toLowerCase();
    const specialNames = {
      dockerfile: 'dockerfile',
      makefile: 'makefile',
      'requirements.txt': 'plaintext',
      'package.json': 'json',
      'tsconfig.json': 'json'
    };
    if (specialNames[baseName]) {
      return normalizeHighlightLanguage(specialNames[baseName]);
    }

    const extension = cleanPath.split('.').pop();
    if (!extension || extension === cleanPath) {
      return normalizeHighlightLanguage(fallback || 'plaintext');
    }
    return normalizeHighlightLanguage(extension);
  }

  function highlightCode(code, language) {
    const text = String(code || '');
    const safeLanguage = normalizeHighlightLanguage(language);
    if (typeof hljs === 'undefined' || !hljs.highlight || safeLanguage === 'plaintext') {
      return escHtml(text);
    }

    try {
      return hljs.highlight(text, {
        language: safeLanguage,
        ignoreIllegals: true
      }).value;
    } catch (_error) {
      return escHtml(text);
    }
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
  function hasOpenActivityMarker(rawText, openTag, closeTag) {
    const source = String(rawText || '').toLowerCase();
    const open = String(openTag || '').toLowerCase();
    const close = String(closeTag || '').toLowerCase();
    const openIndex = source.lastIndexOf(open);
    if (openIndex === -1) {
      return false;
    }
    return source.indexOf(close, openIndex + open.length) === -1;
  }

  function hasOpenToolPayload(rawText) {
    return hasOpenActivityMarker(rawText, '<tool_call>', '</tool_call>')
      || hasOpenActivityMarker(rawText, '<tool_result>', '</tool_result>');
  }

  function parseMessageTimeline(rawText) {
    const source = String(rawText || '');
    const lowerSource = source.toLowerCase();
    const segments = [];
    const toolSegmentByAlias = {};
    const reasoningTagPairs = [
      { start: '<think>', end: '</think>' },
      { start: '<reasoning>', end: '</reasoning>' },
      { start: '<analysis>', end: '</analysis>' }
    ];
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

    function findNextReasoningStart(fromIndex) {
      let best = null;
      reasoningTagPairs.forEach(function checkPair(pair) {
        const pos = lowerSource.indexOf(pair.start, fromIndex);
        if (pos === -1) {
          return;
        }
        if (!best || pos < best.pos) {
          best = { pos, kind: 'thought', pair };
        }
      });
      return best;
    }

    while (cursor < source.length) {
      const reasoningStart = findNextReasoningStart(cursor);
      const toolCallStart = lowerSource.indexOf('<tool_call>', cursor);
      const toolResultStart = lowerSource.indexOf('<tool_result>', cursor);
      const candidates = [
        reasoningStart,
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
        const contentStart = next.pos + next.pair.start.length;
        const thinkEnd = lowerSource.indexOf(next.pair.end, contentStart);
        if (thinkEnd === -1) {
          const content = sanitizeVisibleText(source.substring(contentStart)).trim();
          if (content) {
            segments.push({ type: 'thought', content });
          }
          break;
        }

        const content = sanitizeVisibleText(source.substring(contentStart, thinkEnd)).trim();
        if (content) {
          segments.push({ type: 'thought', content });
        }

        cursor = thinkEnd + next.pair.end.length;
        continue;
      }

      if (next.kind === 'tool') {
        const openTag = '<tool_call>';
        const closeTag = '</tool_call>';
        const toolEnd = lowerSource.indexOf(closeTag, next.pos + openTag.length);
        if (toolEnd === -1) {
          break;
        }

        const payload = source.substring(next.pos + openTag.length, toolEnd);

        try {
          const parsed = JSON.parse(payload);
          const alias = String(parsed.alias || '').trim();
          const segment = {
            type: 'tool',
            alias,
            serverId: String(parsed.server_id || '').trim(),
            serverName: String(parsed.server_name || '').trim(),
            toolId: String(parsed.tool_id || '').trim(),
            toolName: String(parsed.tool_name || parsed.tool_display_name || '').trim(),
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

        cursor = toolEnd + closeTag.length;
        continue;
      }

      const resultOpenTag = '<tool_result>';
      const resultCloseTag = '</tool_result>';
      const resultEnd = lowerSource.indexOf(resultCloseTag, next.pos + resultOpenTag.length);
      if (resultEnd === -1) {
        break;
      }

      const payload = source.substring(next.pos + resultOpenTag.length, resultEnd);

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

      cursor = resultEnd + resultCloseTag.length;
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


  // Read the set of expanded search cards for one row.
  function getExpandedSearchIndices($msgRow) {
    const rawValue = String($msgRow.attr('data-expanded-searches') || '').trim();
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

  // Persist expanded search cards back to the row element.
  function setExpandedSearchIndices($msgRow, expandedIndices) {
    const normalized = Array.from(expandedIndices)
      .filter(function isValid(value) { return Number.isInteger(value) && value >= 0; })
      .sort(function sortValues(left, right) { return left - right; });

    if (normalized.length === 0) {
      $msgRow.removeAttr('data-expanded-searches');
      return;
    }

    $msgRow.attr('data-expanded-searches', normalized.join(','));
  }


  // Read the set of expanded write cards for one row.
  function getExpandedWriteIndices($msgRow) {
    const rawValue = String($msgRow.attr('data-expanded-writes') || '').trim();
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

  // Persist expanded write cards back to the row element.
  function setExpandedWriteIndices($msgRow, expandedIndices) {
    const normalized = Array.from(expandedIndices)
      .filter(function isValid(value) { return Number.isInteger(value) && value >= 0; })
      .sort(function sortValues(left, right) { return left - right; });

    if (normalized.length === 0) {
      $msgRow.removeAttr('data-expanded-writes');
      return;
    }

    $msgRow.attr('data-expanded-writes', normalized.join(','));
  }


  // Read the set of expanded edit cards for one row.
  function getExpandedEditIndices($msgRow) {
    const rawValue = String($msgRow.attr('data-expanded-edits') || '').trim();
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

  // Persist expanded edit cards back to the row element.
  function setExpandedEditIndices($msgRow, expandedIndices) {
    const normalized = Array.from(expandedIndices)
      .filter(function isValid(value) { return Number.isInteger(value) && value >= 0; })
      .sort(function sortValues(left, right) { return left - right; });

    if (normalized.length === 0) {
      $msgRow.removeAttr('data-expanded-edits');
      return;
    }

    $msgRow.attr('data-expanded-edits', normalized.join(','));
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

  function isWriteToolSegment(segment) {
    const toolId = String(segment.toolId || '').toLowerCase();
    const alias = String(segment.alias || '').toLowerCase();
    const toolName = String(segment.toolName || '').toLowerCase();
    return toolId === 'write'
      || alias.endsWith('__write')
      || toolName === 'write'
      || toolName === 'write file';
  }

  function isEditToolSegment(segment) {
    const toolId = String(segment.toolId || '').toLowerCase();
    const alias = String(segment.alias || '').toLowerCase();
    const toolName = String(segment.toolName || '').toLowerCase();
    return toolId === 'edit'
      || alias.endsWith('__edit')
      || toolName === 'edit'
      || toolName === 'edit file';
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
    const isExpanded = !!renderOptions.expanded;
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
    const moreButtonAttrs = `type="button" data-search-more-count="${moreCount}" aria-expanded="${isExpanded ? 'true' : 'false'}"`;
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
      : (icons.TOOL_SEARCH_ICON || icons.WEB_SEARCH_ICON || icons.GLOBE_ICON);

    return `
      <div class="msg-search-card${hasResult ? ' is-done' : ' is-pending'}${isExpanded ? ' is-expanded' : ''}${renderOptions.compactLabel ? ' msg-search-card--batch-item' : ''}" data-tool-segment-index="${toolSegmentIndex}">
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

  function renderSearchToolGroup(searchItems, options) {
    const renderOptions = options || {};
    if (!Array.isArray(searchItems) || searchItems.length === 0) {
      return '';
    }

    if (searchItems.length === 1) {
      return renderSearchToolCard(searchItems[0].segment, searchItems[0].index, renderOptions);
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
    const firstIndex = Number.isInteger(searchItems[0].index) ? searchItems[0].index : 0;
    const isExpanded = renderOptions.expanded === undefined ? false : !!renderOptions.expanded;
    const moreButtonAttrs = `type="button" data-search-more-count="${moreCount}" aria-expanded="${isExpanded ? 'true' : 'false'}"`;
    const collapsedMoreHtml = moreCount > 0
      ? `<button class="msg-search-chip msg-search-chip--more msg-search-chip--more-collapsed" ${moreButtonAttrs}><span class="msg-search-chip-domain">${escHtml(`${MORE_LABEL} ${moreCount}`)}</span></button>`
      : '';
    const expandedMoreHtml = moreCount > 0
      ? `<button class="msg-search-chip msg-search-chip--more msg-search-chip--more-expanded" ${moreButtonAttrs}><span class="msg-search-chip-domain">${escHtml(HIDE_LABEL)}</span></button>`
      : '';

    return `
      <div class="msg-search-card msg-search-card--batch${hasPending ? ' is-pending' : ' is-done'}${isExpanded ? ' is-expanded' : ''}" data-tool-segment-index="${firstIndex}">
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

  function writePathFromSegment(segment) {
    const args = segment.arguments && typeof segment.arguments === 'object' ? segment.arguments : {};
    return String(args.path || args.file || args.filename || '').trim();
  }

  function writeContentFromSegment(segment) {
    const args = segment.arguments && typeof segment.arguments === 'object' ? segment.arguments : {};
    if (args.content !== undefined && args.content !== null) {
      return String(args.content);
    }
    if (args.text !== undefined && args.text !== null) {
      return String(args.text);
    }
    if (args.input !== undefined && args.input !== null) {
      return String(args.input);
    }
    return '';
  }

  function renderWritePreviewLines(content, isExpanded, path) {
    const lines = String(content || '').split(/\r?\n/);
    const maxLines = isExpanded ? WRITE_PREVIEW_EXPANDED_LINES : WRITE_PREVIEW_COLLAPSED_LINES;
    const visibleLines = lines.slice(0, maxLines);
    const language = languageFromPath(path, 'plaintext');
    const rowsHtml = visibleLines.map(function renderLine(line, index) {
      const isFadeLine = !isExpanded && index === WRITE_PREVIEW_COLLAPSED_LINES - 1 && lines.length > WRITE_PREVIEW_COLLAPSED_LINES;
      const lineClass = isFadeLine ? ' msg-write-line--fade' : '';
      const lineText = isFadeLine && !line ? '...' : line;
      return `<div class="msg-write-line${lineClass}">${lineText ? highlightCode(lineText, language) : ' '}</div>`;
    }).join('');
    if (isExpanded && lines.length > maxLines) {
      return `${rowsHtml}<div class="msg-write-line msg-write-line--fade">... ${escHtml(String(lines.length - maxLines))} more lines omitted</div>`;
    }
    return rowsHtml;
  }

  function renderWriteToolCard(segment, toolSegmentIndex, options) {
    const renderOptions = options || {};
    const content = writeContentFromSegment(segment);
    const path = writePathFromSegment(segment);
    const isExpanded = !!renderOptions.expanded;
    const lineCount = textLineCount(content);
    const byteCount = utf8ByteLength(content);
    const hasMore = lineCount > WRITE_PREVIEW_COLLAPSED_LINES;
    const dataIndex = Number.isInteger(toolSegmentIndex) ? ` data-write-segment-index="${toolSegmentIndex}"` : '';
    const label = path ? `Write ${path}` : 'Write';
    const summary = lineCount > 0
      ? `${lineCount} ${lineCount === 1 ? 'line' : 'lines'}${byteCount > 8192 ? ` · ${Math.round(byteCount / 1024)} KB` : ''}`
      : toolStatusText(segment);
    const language = languageFromPath(path, 'plaintext');

    return `
      <div class="msg-write-card${toolStatusClass(segment)}${isExpanded ? ' is-expanded' : ''}${hasMore ? ' has-more' : ''}"${dataIndex} role="button" tabindex="0" aria-expanded="${isExpanded ? 'true' : 'false'}">
        <span class="msg-write-head">
          <span class="msg-write-title">${escHtml(label)}</span>
          <span class="msg-write-summary">${escHtml(summary)}</span>
        </span>
        <span class="msg-write-preview msg-code-block language-${escapeAttributeValue(language)}" data-language="${escapeAttributeValue(language)}">${content ? renderWritePreviewLines(content, isExpanded, path) : '<span class="msg-write-line msg-write-line--empty">No content.</span>'}</span>
      </div>
    `;
  }

  function parseToolResultObject(segment) {
    const rawResult = segment && segment.result !== null && segment.result !== undefined
      ? String(segment.result)
      : '';
    if (!rawResult) {
      return {};
    }

    try {
      const parsed = JSON.parse(rawResult);
      if (!parsed || typeof parsed !== 'object') {
        return {};
      }
      return parsed.result && typeof parsed.result === 'object' ? parsed.result : parsed;
    } catch (_error) {
      return {};
    }
  }

  function editModeFromSegment(segment) {
    const args = segment.arguments && typeof segment.arguments === 'object' ? segment.arguments : {};
    const mode = String(args.mode || '').trim().toLowerCase();
    if (mode === 'lines' || mode === 'line' || (args.range !== undefined && String(args.range || '').trim())) {
      return 'lines';
    }
    return 'match';
  }

  function editPathFromSegment(segment, result) {
    const args = segment.arguments && typeof segment.arguments === 'object' ? segment.arguments : {};
    return String((result && (result.p || result.path)) || args.path || args.file || args.filename || '').trim();
  }

  function parseUnifiedDiffRows(diffText) {
    const rows = [];
    const lines = String(diffText || '').split(/\r?\n/);
    let oldLine = null;
    let newLine = null;

    lines.forEach(function parseDiffLine(line) {
      if (!line || line.startsWith('--- ') || line.startsWith('+++ ')) {
        return;
      }

      const hunkMatch = /^@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@/.exec(line);
      if (hunkMatch) {
        oldLine = parseInt(hunkMatch[1], 10);
        newLine = parseInt(hunkMatch[2], 10);
        rows.push({ type: 'hunk', oldNo: '', newNo: '', text: line });
        return;
      }

      if (oldLine === null || newLine === null) {
        return;
      }

      const marker = line.charAt(0);
      const text = line.slice(1);
      if (marker === '-') {
        rows.push({ type: 'delete', oldNo: oldLine, newNo: '', text });
        oldLine += 1;
        return;
      }
      if (marker === '+') {
        rows.push({ type: 'add', oldNo: '', newNo: newLine, text });
        newLine += 1;
        return;
      }
      if (marker === ' ') {
        rows.push({ type: 'context', oldNo: oldLine, newNo: newLine, text });
        oldLine += 1;
        newLine += 1;
      }
    });

    return rows;
  }

  function fallbackEditRows(segment) {
    const args = segment.arguments && typeof segment.arguments === 'object' ? segment.arguments : {};
    const mode = editModeFromSegment(segment);
    const rows = [];

    if (mode === 'lines') {
      const rangeLabel = args.range !== undefined ? String(Array.isArray(args.range) ? args.range.join(':') : args.range) : '';
      if (rangeLabel) {
        rows.push({ type: 'hunk', oldNo: '', newNo: '', text: `range ${rangeLabel}` });
      }
      String(args.content || args.new_str || '')
        .split(/\r?\n/)
        .forEach(function addLine(line, index) {
          rows.push({ type: 'add', oldNo: '', newNo: index + 1, text: line });
        });
      return rows;
    }

    String(args.old_str || '')
      .split(/\r?\n/)
      .forEach(function deleteLine(line, index) {
        rows.push({ type: 'delete', oldNo: index + 1, newNo: '', text: line });
      });
    String(args.new_str || '')
      .split(/\r?\n/)
      .forEach(function addLine(line, index) {
        rows.push({ type: 'add', oldNo: '', newNo: index + 1, text: line });
      });
    return rows;
  }

  function editRowsFromSegment(segment, result) {
    const rows = parseUnifiedDiffRows(result && result.ud ? result.ud : '');
    return rows.length > 0 ? rows : fallbackEditRows(segment);
  }

  function renderEditRows(rows, isExpanded, language) {
    const safeRows = Array.isArray(rows) ? rows : [];
    const maxRows = isExpanded ? EDIT_PREVIEW_EXPANDED_ROWS : EDIT_PREVIEW_COLLAPSED_ROWS;
    const visibleRows = safeRows.slice(0, maxRows);
    const codeLanguage = normalizeHighlightLanguage(language);
    const rowsHtml = visibleRows.map(function renderEditRow(row, index) {
      const isFadeLine = !isExpanded && index === EDIT_PREVIEW_COLLAPSED_ROWS - 1 && safeRows.length > EDIT_PREVIEW_COLLAPSED_ROWS;
      const rowClass = `msg-edit-row is-${row.type || 'context'}${isFadeLine ? ' msg-edit-row--fade' : ''}`;
      const lineNo = row.type === 'delete'
        ? row.oldNo
        : (row.newNo !== undefined && row.newNo !== '' ? row.newNo : row.oldNo);
      return `
        <span class="${rowClass}">
          <span class="msg-edit-gutter">${escHtml(lineNo === undefined ? '' : lineNo)}</span>
          <span class="msg-edit-code">${row.type === 'hunk' ? escHtml(row.text || ' ') : highlightCode(row.text || ' ', codeLanguage)}</span>
        </span>
      `;
    }).join('');
    if (isExpanded && safeRows.length > maxRows) {
      return `${rowsHtml}<span class="msg-edit-row is-context msg-edit-row--fade"><span class="msg-edit-gutter"></span><span class="msg-edit-code">... ${escHtml(String(safeRows.length - maxRows))} more rows omitted</span></span>`;
    }
    return rowsHtml;
  }

  function renderEditToolCard(segment, toolSegmentIndex, options) {
    const renderOptions = options || {};
    const result = parseToolResultObject(segment);
    const rows = editRowsFromSegment(segment, result);
    const isExpanded = !!renderOptions.expanded;
    const path = editPathFromSegment(segment, result);
    const mode = editModeFromSegment(segment);
    const language = languageFromPath(path, 'plaintext');
    const dataIndex = Number.isInteger(toolSegmentIndex) ? ` data-edit-segment-index="${toolSegmentIndex}"` : '';
    const label = path ? `Edit ${path}` : 'Edit';
    const summaryParts = [mode];
    if (result.r) {
      summaryParts.push(`range ${result.r}`);
    } else if (result.rep !== undefined) {
      summaryParts.push(`${result.rep} replaced`);
    }
    if (result.d !== undefined) {
      summaryParts.push(`${Number(result.d) >= 0 ? '+' : ''}${result.d} lines`);
    } else if (rows.length > EDIT_PREVIEW_EXPANDED_ROWS) {
      summaryParts.push(`${rows.length} rows`);
    }

    return `
      <div class="msg-edit-card${toolStatusClass(segment)}${isExpanded ? ' is-expanded' : ''}"${dataIndex} role="button" tabindex="0" aria-expanded="${isExpanded ? 'true' : 'false'}">
        <span class="msg-edit-head">
          <span class="msg-edit-title">${escHtml(label)}</span>
          <span class="msg-edit-summary">${escHtml(summaryParts.join(' · '))}</span>
        </span>
        <span class="msg-edit-preview msg-code-block language-${escapeAttributeValue(language)}" data-language="${escapeAttributeValue(language)}">${rows.length ? renderEditRows(rows, isExpanded, language) : '<span class="msg-edit-row is-context"><span class="msg-edit-gutter"></span><span class="msg-edit-code">No diff.</span></span>'}</span>
      </div>
    `;
  }

  function truncateInlineText(value, maxLength) {
    const text = String(value || '').replace(/\s+/g, ' ').trim();
    const limit = maxLength || 140;
    return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
  }

  function compactToolValue(value) {
    if (value === null || value === undefined) {
      return '';
    }

    if (typeof value === 'string') {
      return truncateInlineText(value, 150);
    }

    try {
      return truncateInlineText(JSON.stringify(value), 150);
    } catch (_error) {
      return truncateInlineText(String(value), 150);
    }
  }

  function utf8ByteLength(value) {
    const text = String(value || '');
    if (typeof TextEncoder !== 'undefined') {
      return new TextEncoder().encode(text).length;
    }
    return unescape(encodeURIComponent(text)).length;
  }

  function textLineCount(value) {
    const text = String(value || '');
    return text ? text.split(/\r?\n/).length : 0;
  }

  function truncateTextPreview(value, maxChars) {
    const text = String(value || '');
    const limit = Math.max(0, Number(maxChars) || 0);
    if (!limit || text.length <= limit) {
      return { text, truncated: false, omittedChars: 0 };
    }
    return {
      text: text.slice(0, limit),
      truncated: true,
      omittedChars: text.length - limit
    };
  }

  function heavyToolKeysForSegment(segment) {
    if (isWriteToolSegment(segment)) {
      return HEAVY_TOOL_ARGUMENT_KEYS.write;
    }
    if (isEditToolSegment(segment)) {
      return HEAVY_TOOL_ARGUMENT_KEYS.edit;
    }
    if (isSandboxToolSegment(segment)) {
      return HEAVY_TOOL_ARGUMENT_KEYS.bash;
    }
    return [];
  }

  function toolIdentityText(segment) {
    return [
      segment.alias,
      segment.serverId,
      segment.serverName,
      segment.toolId,
      segment.toolName
    ].join(' ').toLowerCase();
  }

  function isSandboxToolSegment(segment) {
    return /sandbox|python|bash|shell|exec|code|deep[-_\s]?think|container/.test(toolIdentityText(segment));
  }

  function parseSandboxResult(segment) {
    const rawResult = segment && segment.result !== null && segment.result !== undefined
      ? String(segment.result)
      : '';
    if (!rawResult) {
      return {
        ok: null,
        exitCode: null,
        stdout: '',
        stderr: '',
        raw: ''
      };
    }

    try {
      const parsed = JSON.parse(rawResult);
      const envelope = parsed && typeof parsed === 'object' ? parsed : {};
      const result = envelope.result && typeof envelope.result === 'object' ? envelope.result : envelope;
      const error = envelope.error && typeof envelope.error === 'object' ? envelope.error : null;
      return {
        ok: envelope.ok === undefined ? null : !!envelope.ok,
        exitCode: result.exit_code !== undefined && result.exit_code !== null ? result.exit_code : null,
        stdout: result.stdout !== undefined && result.stdout !== null ? String(result.stdout) : '',
        stderr: result.stderr !== undefined && result.stderr !== null
          ? String(result.stderr)
          : (error && error.message ? String(error.message) : ''),
        raw: rawResult
      };
    } catch (_error) {
      return {
        ok: null,
        exitCode: null,
        stdout: rawResult,
        stderr: '',
        raw: rawResult
      };
    }
  }

  function sandboxInputText(segment) {
    const args = segment.arguments && typeof segment.arguments === 'object' ? segment.arguments : {};
    const command = args.command || args.cmd || args.code || args.input || '';
    const stdin = args.stdin !== undefined && args.stdin !== null ? String(args.stdin) : '';
    if (stdin) {
      return `${command}\n\n${stdin}`;
    }
    return String(command || '');
  }

  function sandboxInputPreviewText(segment) {
    const preview = truncateTextPreview(sandboxInputText(segment), SANDBOX_INPUT_PREVIEW_CHARS);
    if (!preview.truncated) {
      return preview.text;
    }
    return `${preview.text}\n\n... ${preview.omittedChars} more characters omitted`;
  }

  function sandboxLanguage(segment) {
    const identity = toolIdentityText(segment);
    if (/python/.test(identity)) {
      return 'python';
    }
    if (/bash|shell|exec|sandbox|container/.test(identity)) {
      return 'bash';
    }
    return 'plaintext';
  }

  function renderSandboxStreamBlock(label, content, streamClass, language) {
    const text = String(content || '');
    if (!text) {
      return '';
    }

    const safeLanguage = String(language || 'plaintext').replace(/[^a-z0-9_-]/gi, '') || 'plaintext';
    return `
      <div class="msg-sandbox-section ${streamClass}">
        <div class="msg-sandbox-section-label">${escHtml(label)}</div>
        <pre class="msg-sandbox-pre msg-code-block language-${safeLanguage}" data-language="${escapeAttributeValue(safeLanguage)}"><code>${highlightCode(text, safeLanguage)}</code></pre>
      </div>
    `;
  }

  function sandboxStatusClass(segment, result) {
    if (result && (result.ok === false || (result.exitCode !== null && result.exitCode !== undefined && Number(result.exitCode) !== 0))) {
      return ' is-error';
    }
    return toolStatusClass(segment);
  }

  function renderSandboxToolBlock(segment, toolSegmentIndex) {
    const status = toolStatusText(segment);
    const detail = reasoningToolDetail(segment);
    const result = parseSandboxResult(segment);
    const language = sandboxLanguage(segment);
    const inputText = sandboxInputPreviewText(segment) || detail;
    const hasResult = segment.result !== null && segment.result !== undefined;
    const outputText = result.stdout || (!hasResult ? 'Running...' : '');
    const exitCodeText = result.exitCode !== null && result.exitCode !== undefined ? `exit ${result.exitCode}` : status;
    const dataIndex = Number.isInteger(toolSegmentIndex) ? ` data-tool-segment-index="${toolSegmentIndex}"` : '';
    const stderrHtml = renderSandboxStreamBlock('stderr', result.stderr, 'is-stderr', 'plaintext');
    const stdoutHtml = renderSandboxStreamBlock('stdout', outputText, 'is-stdout', 'plaintext');

    return `
      <div class="msg-sandbox-card${sandboxStatusClass(segment, result)}"${dataIndex}>
        <div class="msg-sandbox-head">
          ${icons.TOOL_BASH_ICON || '<span class="msg-reasoning-tool-icon is-sandbox" aria-hidden="true">S</span>'}
          <span class="msg-sandbox-title">Sandbox</span>
          ${detail ? `<span class="msg-sandbox-detail">${escHtml(detail)}</span>` : ''}
          <span class="msg-reasoning-tool-status">${escHtml(exitCodeText)}</span>
        </div>
        ${renderSandboxStreamBlock('stdin', inputText, 'is-stdin', language)}
        ${stdoutHtml || stderrHtml ? `${stdoutHtml}${stderrHtml}` : renderSandboxStreamBlock('stdout', 'No output.', 'is-stdout is-empty', 'plaintext')}
      </div>
    `;
  }

  function toolDisplayName(segment) {
    if (isSearchToolSegment(segment)) {
      return 'Search';
    }
    if (isReadPageToolSegment(segment)) {
      return 'Read page';
    }
    if (isSandboxToolSegment(segment)) {
      return 'Sandbox';
    }

    return String(segment.toolName || segment.toolId || segment.alias || 'Tool').trim();
  }

  function toolStatusText(segment) {
    const rawStatus = segment.toolUi && segment.toolUi.status ? String(segment.toolUi.status).trim().toLowerCase() : '';
    if (rawStatus === 'error' || rawStatus === 'timeout') {
      return rawStatus === 'timeout' ? 'Timeout' : 'Error';
    }
    return segment.result !== null && segment.result !== undefined ? 'Done' : 'Running';
  }

  function toolStatusClass(segment) {
    const status = toolStatusText(segment).toLowerCase();
    if (status === 'error' || status === 'timeout') {
      return ' is-error';
    }
    if (status === 'running') {
      return ' is-pending';
    }
    return ' is-done';
  }

  function reasoningToolDetail(segment) {
    if (isSearchToolSegment(segment)) {
      return searchQueryFromSegment(segment) || 'sources';
    }

    if (isReadPageToolSegment(segment)) {
      const sources = readPageSourcesFromSegment(segment);
      if (sources.length > 0) {
        return sources
          .map(function sourceLabel(source) { return source.display_domain || source.domain || source.url || ''; })
          .filter(Boolean)
          .slice(0, 2)
          .join(', ');
      }
      return 'source page';
    }

    const args = segment.arguments && typeof segment.arguments === 'object' ? segment.arguments : {};
    const heavyKeys = new Set(heavyToolKeysForSegment(segment));
    const preferredKeys = ['query', 'q', 'url', 'urls', 'path', 'file', 'filename', 'command', 'cmd', 'code', 'prompt', 'input'];
    for (let index = 0; index < preferredKeys.length; index += 1) {
      const key = preferredKeys[index];
      if (heavyKeys.has(key)) {
        continue;
      }
      if (args[key] !== undefined && args[key] !== null && String(args[key]).trim() !== '') {
        return compactToolValue(args[key]);
      }
    }

    const keys = Object.keys(args).filter(function keepKey(key) {
      return !heavyKeys.has(key) && args[key] !== undefined && args[key] !== null && String(args[key]).trim() !== '';
    });
    return keys.slice(0, 2).map(function formatArg(key) {
      return `${key}: ${compactToolValue(args[key])}`;
    }).join(' · ');
  }

  function toolIconHtml(segment) {
    if (isSearchToolSegment(segment) || isReadPageToolSegment(segment)) {
      return icons.TOOL_SEARCH_ICON || icons.WEB_SEARCH_ICON || icons.GLOBE_ICON || '';
    }
    if (isWriteToolSegment(segment)) {
      return icons.TOOL_MAKE_FILE_ICON || '';
    }
    if (isEditToolSegment(segment)) {
      return icons.TOOL_EDIT_FILE_ICON || '';
    }
    if (isSandboxToolSegment(segment)) {
      return icons.TOOL_BASH_ICON || '';
    }
    return '';
  }

  function renderReasoningToolRow(segment) {
    const name = toolDisplayName(segment);
    const detail = reasoningToolDetail(segment);
    const status = toolStatusText(segment);
    const iconHtml = toolIconHtml(segment);
    const initial = name.charAt(0).toUpperCase() || 'T';

    return `
      <div class="msg-reasoning-tool-row${toolStatusClass(segment)}">
        ${iconHtml || `<span class="msg-reasoning-tool-icon" aria-hidden="true">${escHtml(initial)}</span>`}
        <span class="msg-reasoning-tool-main">
          <span class="msg-reasoning-tool-name">${escHtml(name)}</span>
          ${detail ? `<span class="msg-reasoning-tool-detail">${escHtml(detail)}</span>` : ''}
        </span>
        <span class="msg-reasoning-tool-status">${escHtml(status)}</span>
      </div>
    `;
  }

  function renderReasoningToolItem(item) {
    const segment = item && item.segment ? item.segment : item;
    const toolIndex = item && Number.isInteger(item.toolIndex) ? item.toolIndex : undefined;
    if (!segment) {
      return '';
    }

    if (isSearchToolSegment(segment)) {
      return renderSearchToolCard(segment, toolIndex, { compactLabel: true, hideIcon: false, expanded: !!item.expanded });
    }
    if (isReadPageToolSegment(segment)) {
      return renderReadPageToolCard([{ segment, index: toolIndex }]);
    }
    if (isWriteToolSegment(segment)) {
      return renderWriteToolCard(segment, toolIndex, { expanded: !!item.expanded });
    }
    if (isEditToolSegment(segment)) {
      return renderEditToolCard(segment, toolIndex, { expanded: !!item.expanded });
    }
    if (isSandboxToolSegment(segment)) {
      return renderSandboxToolBlock(segment, toolIndex);
    }
    return renderReasoningToolRow(segment);
  }

  function reasoningToolStepTitle(segment) {
    if (isSearchToolSegment(segment)) {
      return toolStatusText(segment) === 'Done' ? 'Searched sources' : 'Searching sources';
    }
    if (isReadPageToolSegment(segment)) {
      return 'Reading source page';
    }
    if (isWriteToolSegment(segment)) {
      const path = writePathFromSegment(segment);
      return path ? `Writing ${path}` : 'Writing file';
    }
    if (isEditToolSegment(segment)) {
      const result = parseToolResultObject(segment);
      const path = editPathFromSegment(segment, result);
      return path ? `Editing ${path}` : 'Editing file';
    }
    if (isSandboxToolSegment(segment)) {
      return 'Running sandbox command';
    }
    return toolDisplayName(segment);
  }

  function formatReasoningElapsed(seconds) {
    const numericSeconds = Number(seconds);
    if (!Number.isFinite(numericSeconds) || numericSeconds <= 0) {
      return '';
    }
    if (numericSeconds < 60) {
      return `${Math.max(1, Math.round(numericSeconds))}s`;
    }
    const minutes = Math.floor(numericSeconds / 60);
    const remainder = Math.round(numericSeconds % 60);
    return remainder > 0 ? `${minutes}m ${remainder}s` : `${minutes}m`;
  }

  function reasoningElapsedSeconds($msgRow) {
    const fixedValue = Number($msgRow.data('reasoningElapsedSeconds'));
    if (Number.isFinite(fixedValue) && fixedValue > 0) {
      return fixedValue;
    }

    const startedAt = Number($msgRow.data('responseStartedAt'));
    if (!Number.isFinite(startedAt) || startedAt <= 0) {
      return null;
    }

    return Math.max(0, (Date.now() - startedAt) / 1000);
  }

  function reasoningToggleLabel($msgRow) {
    const elapsed = formatReasoningElapsed(reasoningElapsedSeconds($msgRow));
    return elapsed ? `Thought for ${elapsed}` : 'Thought';
  }

  function hasThoughtSegments(segments) {
    return (Array.isArray(segments) ? segments : []).some(function hasThought(segment) {
      return segment && segment.type === 'thought';
    });
  }

  function hasClosedReasoning(rawText) {
    return /<\/(?:think|reasoning|analysis)>/i.test(String(rawText || ''));
  }

  function renderReasoningGroup(items, thoughtIndex, isExpanded, toggleLabel) {
    const safeItems = Array.isArray(items) ? items : [];
    const thoughtCount = safeItems.filter(function countThoughts(item) { return item && item.type === 'thought'; }).length;
    const toolCount = safeItems.filter(function countTools(item) { return item && item.type === 'tool'; }).length;
    const summaryParts = [];
    if (toolCount > 0) {
      summaryParts.push(`${toolCount} tool ${toolCount === 1 ? 'call' : 'calls'}`);
    }

    // Tool-only group (no reasoning): wrap in a pill without the "Thought for Xs" label
    // so tools don't flash in chat and then jump into a reasoning block when thinking arrives.
    if (thoughtCount === 0) {
      const toolsHtml = safeItems.map(function renderToolOnlyItem(item) {
        return item && item.type === 'tool' ? renderReasoningToolItem(item) : '';
      }).join('');
      return `
        <div class="msg-thoughts-wrapper msg-reasoning-wrapper${isExpanded ? ' expanded' : ''}" data-thought-index="${thoughtIndex}">
          <button type="button" class="msg-thoughts-toggle msg-reasoning-toggle" aria-expanded="${isExpanded ? 'true' : 'false'}">
            ${summaryParts.length ? `<span class="msg-reasoning-summary">${escHtml(summaryParts.join(' · '))}</span>` : ''}
          </button>
          <div class="msg-thoughts-content msg-reasoning-content" style="display:${isExpanded ? 'block' : 'none'};">${toolsHtml}</div>
        </div>
      `;
    }

    const renderItems = toolCount > 0
      ? safeItems.filter(function keepToolItems(item) { return item && item.type === 'tool'; })
      : safeItems;
    const contentHtml = renderItems.map(function renderReasoningItem(item) {
      if (!item) {
        return '';
      }
      if (item.type === 'tool') {
        const segment = item && item.segment ? item.segment : item;
        const title = reasoningToolStepTitle(segment || {});
        const status = toolStatusText(segment || {});
        const iconHtml = toolIconHtml(segment || {});
        const hideStepTitle = isWriteToolSegment(segment || {}) || isEditToolSegment(segment || {});
        return `
          <div class="msg-reasoning-step msg-reasoning-step--tool${toolStatusClass(segment || {})}">
            <div class="msg-reasoning-step-dot" aria-hidden="true">${iconHtml}</div>
            <div class="msg-reasoning-step-body">
              <div class="msg-reasoning-step-title">
                ${hideStepTitle ? '' : `<span>${escHtml(title)}</span>`}
                <span class="msg-reasoning-step-status">${escHtml(status)}</span>
              </div>
              ${renderReasoningToolItem(item)}
            </div>
          </div>
        `;
      }
      return `
        <div class="msg-reasoning-step">
          <div class="msg-reasoning-step-dot" aria-hidden="true"></div>
          <div class="msg-reasoning-step-body">
            <div class="msg-reasoning-text">${escHtml(item.content || '')}</div>
          </div>
        </div>
      `;
    }).join('');

    return `
      <div class="msg-thoughts-wrapper msg-reasoning-wrapper${isExpanded ? ' expanded' : ''}" data-thought-index="${thoughtIndex}">
        <button type="button" class="msg-thoughts-toggle msg-reasoning-toggle" aria-expanded="${isExpanded ? 'true' : 'false'}">
          <span class="msg-reasoning-title">${escHtml(toggleLabel || 'Thought')}</span>
          ${summaryParts.length ? `<span class="msg-reasoning-summary">${escHtml(summaryParts.join(' · '))}</span>` : ''}
        </button>
        <div class="msg-thoughts-content msg-reasoning-content" style="display:${isExpanded ? 'block' : 'none'};">${contentHtml}</div>
      </div>
    `;
  }

  function renderThoughtBlock(content, thoughtIndex, isExpanded) {
    return `
      <div class="msg-thoughts-wrapper msg-reasoning-wrapper${isExpanded ? ' expanded' : ''}" data-thought-index="${thoughtIndex}">
        <button type="button" class="msg-thoughts-toggle msg-reasoning-toggle" aria-expanded="${isExpanded ? 'true' : 'false'}">
          <span class="msg-reasoning-title">Thought</span>
        </button>
        <div class="msg-thoughts-content msg-reasoning-content" style="display:${isExpanded ? 'block' : 'none'};"><div class="msg-reasoning-text">${escHtml(content)}</div></div>
      </div>
    `;
  }

  function createActivityBlock(key, innerHtml) {
    const safeKey = String(key || 'block');
    return {
      key: safeKey,
      html: `<div class="msg-activity-block" data-activity-key="${escapeAttributeValue(safeKey)}">${innerHtml}</div>`
    };
  }

  function applyActivityBlocks($stream, blocks) {
    const safeBlocks = Array.isArray(blocks) ? blocks : [];
    const $existing = $stream.children('.msg-activity-block[data-activity-key]');
    let canPatch = $existing.length === safeBlocks.length;

    if (canPatch) {
      safeBlocks.forEach(function compareBlock(block, index) {
        if ($existing.eq(index).attr('data-activity-key') !== block.key) {
          canPatch = false;
        }
      });
    }

    function appendBlock(block) {
      const $block = $(block.html);
      $block.data('activityHtml', block.html);
      $stream.append($block);
    }

    if (!canPatch) {
      $stream.empty();
      safeBlocks.forEach(appendBlock);
      return;
    }

    safeBlocks.forEach(function patchBlock(block, index) {
      const $block = $existing.eq(index);
      if ($block.data('activityHtml') === block.html) {
        return;
      }

      const $newBlock = $(block.html);
      $newBlock.data('activityHtml', block.html);
      $block.replaceWith($newBlock);
    });
  }

  function renderActivityTimeline($msgRow, segments, options) {
    const renderOptions = options || {};
    const useMarkdown = renderOptions.markdown !== false;
    const $stream = $msgRow.find('.msg-activity-stream');
    const $bubble = $msgRow.find('.msg-bubble');
    const shouldSyncOpenDrawer = (
      $activeReasoningWrapper
      && $('#reasoningDrawer').hasClass('is-open')
      && $activeReasoningWrapper.closest('.msg')[0] === $msgRow[0]
    );
    const activeReasoningIndex = shouldSyncOpenDrawer
      ? String($activeReasoningWrapper.attr('data-thought-index') || '')
      : '';

    if (!$stream.length) {
      return;
    }

    if (!Array.isArray(segments) || segments.length === 0) {
      $stream.hide().empty();
      $bubble.html('');
      $msgRow.removeAttr('data-expanded-thoughts');
      $msgRow.removeAttr('data-expanded-searches');
      $msgRow.removeAttr('data-expanded-writes');
      $msgRow.removeAttr('data-expanded-edits');
      $msgRow.removeData('toolSegments');
      return;
    }

    const expandedThoughts = getExpandedThoughtIndices($msgRow);
    const expandedSearches = getExpandedSearchIndices($msgRow);
    const expandedWrites = getExpandedWriteIndices($msgRow);
    const expandedEdits = getExpandedEditIndices($msgRow);
    let thoughtIndex = -1;
    let toolSegmentIndex = 0;
    const citationRegistry = {};
    const toolSegments = segments.filter(function onlyToolSegments(segment) {
      return segment.type === 'tool';
    });
    const lastToolSegmentIndex = segments.reduce(function findLastToolIndex(lastIndex, segment, index) {
      return segment && segment.type === 'tool' ? index : lastIndex;
    }, -1);
    let reasoningGroupIndex = -1;
    const thoughtToggleLabel = reasoningToggleLabel($msgRow);

    const blocks = [];
    function pushBlock(key, html) {
      if (!html || !String(html).trim()) {
        return;
      }
      blocks.push(createActivityBlock(key, html));
    }

    for (let segmentIndex = 0; segmentIndex < segments.length; segmentIndex += 1) {
      const segment = segments[segmentIndex];

      if (segment.type === 'thought' || segment.type === 'tool') {
        const groupStartIndex = segmentIndex;
        const groupItems = [];
        reasoningGroupIndex += 1;

        while (
          segmentIndex < segments.length
          && (segments[segmentIndex].type === 'thought' || segments[segmentIndex].type === 'tool')
        ) {
          const groupSegment = segments[segmentIndex];
          if (groupSegment.type === 'thought') {
            thoughtIndex += 1;
            groupItems.push(groupSegment);
          } else {
            const currentToolIndex = toolSegmentIndex;
            if (isSearchToolSegment(groupSegment)) {
              addSearchSourcesToCitationRegistry(citationRegistry, groupSegment);
            }
            groupItems.push({
              type: 'tool',
              segment: groupSegment,
              toolIndex: currentToolIndex,
              expanded: isSearchToolSegment(groupSegment)
                ? expandedSearches.has(currentToolIndex)
                : (isWriteToolSegment(groupSegment)
                  ? expandedWrites.has(currentToolIndex)
                  : (isEditToolSegment(groupSegment) ? expandedEdits.has(currentToolIndex) : false))
            });
            toolSegmentIndex += 1;
          }
          segmentIndex += 1;
        }

        segmentIndex -= 1;
        if (groupItems.some(function hasToolItem(item) { return item && item.type === 'tool'; }) || groupStartIndex > lastToolSegmentIndex) {
          pushBlock(
            `reasoning-${reasoningGroupIndex}`,
            renderReasoningGroup(groupItems, reasoningGroupIndex, expandedThoughts.has(reasoningGroupIndex), thoughtToggleLabel)
          );
        }
        continue;
      }

      if (lastToolSegmentIndex !== -1 && segmentIndex < lastToolSegmentIndex) {
        continue;
      }

      pushBlock(
        `text-${segmentIndex}`,
        `
        <div class="msg-stream-text">
          <div class="markdown-body${useMarkdown ? '' : ' is-streaming'}">${useMarkdown ? renderMarkdownSegment(segment.content, citationRegistry) : renderPlainTextSegment(segment.content)}</div>
        </div>
      `
      );
    }

    $bubble.empty();
    applyActivityBlocks($stream, blocks);
    $stream.css('display', 'flex');
    setExpandedThoughtIndices($msgRow, expandedThoughts);
    setExpandedSearchIndices($msgRow, expandedSearches);
    setExpandedWriteIndices($msgRow, expandedWrites);
    setExpandedEditIndices($msgRow, expandedEdits);
    $msgRow.data('toolSegments', toolSegments);

    if (shouldSyncOpenDrawer) {
      const $nextActiveWrapper = $msgRow
        .find('.msg-thoughts-wrapper, .msg-reasoning-wrapper')
        .filter(function matchActiveReasoningWrapper() {
          return String($(this).attr('data-thought-index') || '') === activeReasoningIndex;
        })
        .first();

      if ($nextActiveWrapper.length) {
        $activeReasoningWrapper = $nextActiveWrapper;
        $nextActiveWrapper.addClass('is-active');
        $nextActiveWrapper.find('.msg-reasoning-toggle, .msg-thoughts-toggle').attr('aria-expanded', 'true');
        syncReasoningDrawerFromWrapper($nextActiveWrapper);
      } else {
        closeReasoningDrawer();
      }
    }
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

  function clearPreToolTextHold($msgRow) {
    const holdState = $msgRow.data('preToolTextHoldState');
    if (holdState && holdState.timer) {
      window.clearTimeout(holdState.timer);
    }

    $msgRow.removeData('preToolTextHoldState');
    $msgRow.removeData('preToolTextHoldRaw');
  }

  function shouldHoldPreToolText($msgRow, parsed, rawText) {
    const segments = Array.isArray(parsed && parsed.segments) ? parsed.segments : [];
    if (!segments.length || segments.some(function hasTool(segment) { return segment && segment.type === 'tool'; })) {
      clearPreToolTextHold($msgRow);
      return false;
    }

    const hasRenderableText = segments.some(function hasTextLikeSegment(segment) {
      return segment
        && (segment.type === 'text' || segment.type === 'thought')
        && String(segment.content || '').trim();
    });
    if (!hasRenderableText) {
      clearPreToolTextHold($msgRow);
      return false;
    }

    const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
    const holdState = $msgRow.data('preToolTextHoldState') || {};
    if (!holdState.startedAt) {
      holdState.startedAt = now;
    }
    if (holdState.released) {
      return false;
    }

    const remaining = PRE_TOOL_TEXT_HOLD_MS - (now - holdState.startedAt);
    $msgRow.data('preToolTextHoldRaw', rawText);

    if (remaining <= 0) {
      holdState.released = true;
      if (holdState.timer) {
        window.clearTimeout(holdState.timer);
        holdState.timer = null;
      }
      $msgRow.data('preToolTextHoldState', holdState);
      return false;
    }

    if (holdState.timer) {
      window.clearTimeout(holdState.timer);
    }
    holdState.timer = window.setTimeout(function renderHeldPreToolText() {
      const latestRaw = $msgRow.data('preToolTextHoldRaw');
      const latestState = $msgRow.data('preToolTextHoldState') || {};
      latestState.timer = null;
      latestState.released = true;
      $msgRow.data('preToolTextHoldState', latestState);
      renderMessageStream($msgRow, latestRaw || rawText);
    }, Math.max(0, remaining + 16));
    $msgRow.data('preToolTextHoldState', holdState);
    return true;
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
    clearPreToolTextHold($msgRow);
    const parsed = parseMessageTimeline(rawText);
    if (hasThoughtSegments(parsed.segments) && !$msgRow.data('reasoningElapsedSeconds')) {
      const startedAt = Number($msgRow.data('responseStartedAt'));
      if (Number.isFinite(startedAt) && startedAt > 0) {
        $msgRow.data('reasoningElapsedSeconds', Math.max(1, (Date.now() - startedAt) / 1000));
      }
    }
    renderActivityTimeline($msgRow, parsed.segments);
    $msgRow.find('.msg-bubble').attr('data-raw', rawText).attr('data-copy', parsed.visibleText);
  }

  // Parse and render one assistant transcript during active streaming.
  function renderMessageStream($msgRow, rawText) {
    if (hasOpenToolPayload(rawText)) {
      $msgRow.find('.msg-bubble').attr('data-raw', rawText);
      return;
    }

    const parsed = parseMessageTimeline(rawText);
    if (hasThoughtSegments(parsed.segments) && !$msgRow.data('responseStartedAt')) {
      $msgRow.data('responseStartedAt', Date.now());
    }
    if (hasThoughtSegments(parsed.segments) && !$msgRow.data('reasoningElapsedSeconds') && hasClosedReasoning(rawText)) {
      const startedAt = Number($msgRow.data('responseStartedAt'));
      if (Number.isFinite(startedAt) && startedAt > 0) {
        $msgRow.data('reasoningElapsedSeconds', Math.max(1, (Date.now() - startedAt) / 1000));
      }
    }
    if (shouldHoldPreToolText($msgRow, parsed, rawText)) {
      $msgRow.find('.msg-bubble').attr('data-raw', rawText).attr('data-copy', parsed.visibleText);
      return;
    }
    if (shouldHoldStreamingSearchBatch($msgRow, parsed, rawText)) {
      $msgRow.find('.msg-bubble').attr('data-raw', rawText).attr('data-copy', parsed.visibleText);
      return;
    }

    renderActivityTimeline($msgRow, parsed.segments);
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
    const $row = $button.closest('.msg');
    const expanded = !$card.hasClass('is-expanded');
    const moreCount = parseInt($button.attr('data-search-more-count') || '0', 10) || 0;
    const cardIndex = parseInt($card.attr('data-tool-segment-index') || '-1', 10);
    const expandedSearches = getExpandedSearchIndices($row);

    if (Number.isInteger(cardIndex) && cardIndex >= 0) {
      if (expanded) {
        expandedSearches.add(cardIndex);
      } else {
        expandedSearches.delete(cardIndex);
      }
      setExpandedSearchIndices($row, expandedSearches);
    }

    $card.toggleClass('is-expanded', expanded);
    $card.find('.msg-search-chip--more').attr('aria-expanded', expanded ? 'true' : 'false');
    $card.find('.msg-search-chip--more-collapsed .msg-search-chip-domain').text(`${MORE_LABEL} ${moreCount}`);
    $card.find('.msg-search-chip--more-expanded .msg-search-chip-domain').text(HIDE_LABEL);
  }

  function toggleWriteCard($card) {
    const $row = $card.closest('.msg');
    const cardIndex = parseInt($card.attr('data-write-segment-index') || '-1', 10);
    const expandedWrites = getExpandedWriteIndices($row);
    const willExpand = !$card.hasClass('is-expanded');

    if (Number.isInteger(cardIndex) && cardIndex >= 0) {
      if (willExpand) {
        expandedWrites.add(cardIndex);
      } else {
        expandedWrites.delete(cardIndex);
      }
      setExpandedWriteIndices($row, expandedWrites);
    }

    const toolSegments = $row.data('toolSegments') || $('#reasoningDrawerBody').data('toolSegments') || [];
    const segment = toolSegments[cardIndex];
    if (!segment) {
      $card.toggleClass('is-expanded', willExpand).attr('aria-expanded', willExpand ? 'true' : 'false');
      return;
    }

    const $replacement = $(renderWriteToolCard(segment, cardIndex, { expanded: willExpand }));
    $card.replaceWith($replacement);
  }

  function toggleEditCard($card) {
    const $row = $card.closest('.msg');
    const cardIndex = parseInt($card.attr('data-edit-segment-index') || '-1', 10);
    const expandedEdits = getExpandedEditIndices($row);
    const willExpand = !$card.hasClass('is-expanded');

    if (Number.isInteger(cardIndex) && cardIndex >= 0) {
      if (willExpand) {
        expandedEdits.add(cardIndex);
      } else {
        expandedEdits.delete(cardIndex);
      }
      setExpandedEditIndices($row, expandedEdits);
    }

    const toolSegments = $row.data('toolSegments') || $('#reasoningDrawerBody').data('toolSegments') || [];
    const segment = toolSegments[cardIndex];
    if (!segment) {
      $card.toggleClass('is-expanded', willExpand).attr('aria-expanded', willExpand ? 'true' : 'false');
      return;
    }

    const $replacement = $(renderEditToolCard(segment, cardIndex, { expanded: willExpand }));
    $card.replaceWith($replacement);
  }

  function startWritePreviewPan(event, $preview) {
    if (event.button !== 1) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    const preview = $preview[0];
    if (!preview) {
      return;
    }

    const existingStop = $preview.data('writePreviewPanStop');
    if (typeof existingStop === 'function') {
      existingStop();
      return;
    }

    const anchorX = event.clientX;
    let currentX = event.clientX;
    let animationFrame = null;
    let isActive = true;
    let hasMoved = false;
    const startTime = Date.now();
    $preview.addClass('is-middle-panning');

    function scrollFrame() {
      if (!isActive) {
        return;
      }

      const distance = currentX - anchorX;
      if (Math.abs(distance) > 4) {
        preview.scrollLeft += distance * 0.18;
      }

      animationFrame = window.requestAnimationFrame(scrollFrame);
    }

    function onMouseMove(moveEvent) {
      moveEvent.preventDefault();
      currentX = moveEvent.clientX;
      if (Math.abs(currentX - anchorX) > 4) {
        hasMoved = true;
      }
    }

    function stopPan() {
      isActive = false;
      if (animationFrame !== null) {
        window.cancelAnimationFrame(animationFrame);
        animationFrame = null;
      }
      $preview.removeClass('is-middle-panning');
      $preview.removeData('writePreviewPanStop');
      $(document).off('.writePreviewPan');
    }

    function onMouseUp(upEvent) {
      if (upEvent.button !== 1) {
        return;
      }

      const isQuickClick = !hasMoved && Date.now() - startTime < 260;
      if (!isQuickClick) {
        stopPan();
      }
    }

    $(document).on('mousemove.writePreviewPan', onMouseMove);
    $(document).on('mouseup.writePreviewPan', onMouseUp);
    $(document).on('blur.writePreviewPan', stopPan);
    $(document).on('mousedown.writePreviewPan', function onNextMiddleDown(nextEvent) {
      if (nextEvent.target !== preview && !$(nextEvent.target).closest(preview).length) {
        nextEvent.preventDefault();
        stopPan();
      }
    });
    $preview.data('writePreviewPanStop', stopPan);
    animationFrame = window.requestAnimationFrame(scrollFrame);
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
    const startedAt = timestamp ? new Date(timestamp).getTime() : Date.now();
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

    $row.data('responseStartedAt', Number.isFinite(startedAt) ? startedAt : Date.now());
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


  // Reasoning drawer state.
  let $activeReasoningWrapper = null;
  const REASONING_DRAWER_DEFAULT_WIDTH = 340;
  const REASONING_DRAWER_MIN_WIDTH = 300;
  const REASONING_DRAWER_MAX_WIDTH = 720;
  const REASONING_DRAWER_CLOSE_WIDTH = 220;

  function reasoningDrawerMaxWidth() {
    return Math.max(
      REASONING_DRAWER_MIN_WIDTH,
      Math.min(REASONING_DRAWER_MAX_WIDTH, Math.floor(window.innerWidth * 0.82))
    );
  }

  function setReasoningDrawerWidth(width) {
    const clamped = Math.max(
      REASONING_DRAWER_MIN_WIDTH,
      Math.min(reasoningDrawerMaxWidth(), Math.round(Number(width) || REASONING_DRAWER_DEFAULT_WIDTH))
    );
    $('#reasoningDrawer').css('--reasoning-drawer-width', `${clamped}px`);
  }

  function resetReasoningDrawerWidth() {
    setReasoningDrawerWidth(REASONING_DRAWER_DEFAULT_WIDTH);
  }

  function syncReasoningDrawerFromWrapper($wrapper) {
    const $drawer = $('#reasoningDrawer');
    const $body = $('#reasoningDrawerBody');
    const $summary = $('#reasoningDrawerSummary');

    if (!$drawer.hasClass('is-open') || !$body.length) {
      return;
    }

    const $content = $wrapper.find('.msg-thoughts-content, .msg-reasoning-content').first();
    const summaryText = $wrapper.find('.msg-reasoning-summary').text().trim();
    const bodyEl = $body[0];
    const isNearBottom = bodyEl ? bodyEl.scrollHeight - bodyEl.clientHeight <= bodyEl.scrollTop + 50 : false;
    $summary.text(summaryText);
    $body.html(`<div class="msg-reasoning-content">${$content.html() || ''}</div>`);
    $body.data('toolSegments', $wrapper.closest('.msg').data('toolSegments') || []);
    if (isNearBottom && bodyEl) {
      bodyEl.scrollTop = bodyEl.scrollHeight;
    }
  }

  function openReasoningDrawer($wrapper) {
    const $drawer = $('#reasoningDrawer');
    const $backdrop = $('#reasoningDrawerBackdrop');

    if (!$drawer.length) {
      return;
    }

    resetReasoningDrawerWidth();

    // Deactivate previously active pill.
    if ($activeReasoningWrapper && $activeReasoningWrapper[0] !== $wrapper[0]) {
      $activeReasoningWrapper.removeClass('is-active');
      $activeReasoningWrapper.find('.msg-reasoning-toggle, .msg-thoughts-toggle').attr('aria-expanded', 'false');
    }

    // If clicking the same pill while open, close the drawer.
    if ($activeReasoningWrapper && $activeReasoningWrapper[0] === $wrapper[0] && $drawer.hasClass('is-open')) {
      closeReasoningDrawer();
      return;
    }

    $activeReasoningWrapper = $wrapper;
    $wrapper.addClass('is-active');
    $wrapper.find('.msg-reasoning-toggle, .msg-thoughts-toggle').attr('aria-expanded', 'true');

    $drawer.addClass('is-open');
    $backdrop.addClass('is-visible');
    syncReasoningDrawerFromWrapper($wrapper);
  }

  function closeReasoningDrawer() {
    const $drawer = $('#reasoningDrawer');
    const $backdrop = $('#reasoningDrawerBackdrop');

    $drawer.removeClass('is-open is-resizing');
    $backdrop.removeClass('is-visible');
    $('body').removeClass('is-resizing-reasoning-drawer');

    if ($activeReasoningWrapper) {
      $activeReasoningWrapper.removeClass('is-active');
      $activeReasoningWrapper.find('.msg-reasoning-toggle, .msg-thoughts-toggle').attr('aria-expanded', 'false');
      $activeReasoningWrapper = null;
    }

    // Clear body after transition.
    setTimeout(function clearDrawerBody() {
      if (!$drawer.hasClass('is-open')) {
        $('#reasoningDrawerBody').empty();
      }
    }, 250);
  }

  function bindReasoningDrawerResize() {
    const $handle = $('#reasoningDrawerResizeHandle');
    if (!$handle.length) {
      return;
    }

    $handle.on('pointerdown', function onReasoningResizeStart(event) {
      const $drawer = $('#reasoningDrawer');
      if (!$drawer.hasClass('is-open')) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();

      let shouldClose = false;
      $drawer.addClass('is-resizing');
      $('body').addClass('is-resizing-reasoning-drawer');

      function widthFromPointer(pointerEvent) {
        return window.innerWidth - pointerEvent.clientX;
      }

      function onMove(moveEvent) {
        const nextWidth = widthFromPointer(moveEvent);
        shouldClose = nextWidth <= REASONING_DRAWER_CLOSE_WIDTH;
        if (!shouldClose) {
          setReasoningDrawerWidth(nextWidth);
        }
      }

      function onEnd() {
        $(document).off('.reasoningDrawerResize');
        $drawer.removeClass('is-resizing');
        $('body').removeClass('is-resizing-reasoning-drawer');
        if (shouldClose) {
          closeReasoningDrawer();
        }
      }

      $(document)
        .on('pointermove.reasoningDrawerResize', onMove)
        .on('pointerup.reasoningDrawerResize pointercancel.reasoningDrawerResize', onEnd);
    });
  }

  // Thought UI.
  function toggleThoughtSection($toggle) {
    const $wrapper = $toggle.closest('.msg-thoughts-wrapper, .msg-reasoning-wrapper');
    openReasoningDrawer($wrapper);
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
        return hljs.highlight(code, { language, ignoreIllegals: true }).value;
      },
      breaks: true
    });
  }

  bindReasoningDrawerResize();

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
    toggleEditCard,
    toggleWriteCard,
    startWritePreviewPan,
    toggleThoughtSection,
    closeReasoningDrawer,
    updateRegenButtons,
    updateSendButtons
  };
}
