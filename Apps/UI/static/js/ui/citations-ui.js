// Copyright NGGT.LightKeeper. All Rights Reserved.

import { escHtml, escapeAttributeValue } from '../main/utils.js';

const CITATION_ID_PATTERN = /^(?:S\d+|SOURCE-(?:[A-Z0-9]+-)?\d+|C[A-Z0-9]{2,16}-\d+)$/;
const CITATION_SCAN_PATTERN = /\b(?:S\d+|SOURCE-(?:[A-Z0-9]+-)?\d+|C[A-Z0-9]{2,16}-\d+)\b/gi;
const CITATION_INLINE_NOISE_PATTERN = /[\u034f\u061c\u180e\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/g;
const CITATION_HANDLE_SOURCE = String.raw`(?:S\d+|source-(?:[a-z0-9]+-)?\d+|c[a-z0-9]{2,16}-\d+)`;
const CITATION_HANDLE_LIST_SOURCE = String.raw`${CITATION_HANDLE_SOURCE}(?:\s*,\s*${CITATION_HANDLE_SOURCE})*`;
const CITATION_HANDLE_LIST_PATTERN = new RegExp(String.raw`^\s*${CITATION_HANDLE_LIST_SOURCE}\s*$`, 'i');
const CITATION_BRACKET_SOURCE = String.raw`\[\s*${CITATION_HANDLE_LIST_SOURCE}\s*\]`;
const CITATION_GAP_SOURCE = String.raw`[\s\u00a0\u1680\u180e\u2000-\u200d\u2028\u2029\u202f\u205f\u2060\u3000\ufeff]*`;
const CITATION_JUNK_CLASS_SOURCE = String.raw`.,;:!?(){}<>|/\\'"\-\u00ad\u058a\u05be\u1400\u1806\u2010-\u2015\u2053\u207b\u208b\u2212\u2796\u2e17\u2e1a\u2e3a-\u2e3b\u2e40\u2e5d\u30a0\ufe31-\ufe32\ufe58\ufe63\uff0d`;
const CITATION_LEADING_JUNK_PATTERN = new RegExp(
  String.raw`([^\s\[(])${CITATION_GAP_SOURCE}[${CITATION_JUNK_CLASS_SOURCE}]+${CITATION_GAP_SOURCE}(?=${CITATION_BRACKET_SOURCE})`,
  'gi'
);
const CITATION_INTER_BLOCK_JUNK_PATTERN = new RegExp(
  String.raw`(${CITATION_BRACKET_SOURCE})${CITATION_GAP_SOURCE}[${CITATION_JUNK_CLASS_SOURCE}]+${CITATION_GAP_SOURCE}(?=${CITATION_BRACKET_SOURCE})`,
  'gi'
);
const CITATION_ATTACHED_PATTERN = new RegExp(String.raw`([^\s\[(])\[(${CITATION_HANDLE_LIST_SOURCE})\]`, 'gi');
const CITATION_TITLE_MAX_CHARS = 180;
const CITATION_PREVIEW_MAX_CHARS = 520;


// Citation glyph helpers.
// Report whether one Unicode code point is a dash-like citation separator.
function isCitationDashCodePoint(codePoint) {
  return codePoint === 0x002d
    || codePoint === 0x00ad
    || codePoint === 0x058a
    || codePoint === 0x05be
    || codePoint === 0x1400
    || codePoint === 0x1806
    || (codePoint >= 0x2010 && codePoint <= 0x2015)
    || codePoint === 0x2053
    || codePoint === 0x207b
    || codePoint === 0x208b
    || codePoint === 0x2212
    || codePoint === 0x2796
    || codePoint === 0x2e17
    || codePoint === 0x2e1a
    || (codePoint >= 0x2e3a && codePoint <= 0x2e3b)
    || codePoint === 0x2e40
    || codePoint === 0x2e5d
    || codePoint === 0x30a0
    || (codePoint >= 0xfe31 && codePoint <= 0xfe32)
    || codePoint === 0xfe58
    || codePoint === 0xfe63
    || codePoint === 0xff0d
    || codePoint === 0x10ead;
}

// Normalize dash variants and invisible characters in citation handles.
function normalizeCitationHandleGlyphs(value) {
  return Array.from(String(value || '').replace(CITATION_INLINE_NOISE_PATTERN, ''))
    .map(function normalizeCitationGlyph(character) {
      return isCitationDashCodePoint(character.codePointAt(0)) ? '-' : character;
    })
    .join('');
}


// Public citation normalization API.
// Normalize one citation handle into canonical uppercase form.
export function normalizeCitationId(value) {
  return normalizeCitationHandleGlyphs(value)
    .trim()
    .replace(/^\[|\]$/g, '')
    .replace(/[.,;:!?]+$/g, '')
    .toUpperCase();
}

// Report whether a value matches the supported citation handle pattern.
export function isCitationHandleId(value) {
  return CITATION_ID_PATTERN.test(normalizeCitationId(value));
}

// Normalize full-width and variant bracket glyphs around citation handles.
export function normalizeCitationBrackets(value) {
  return String(value || '')
    .replace(/[\u3010\uFF3B]/g, '[')
    .replace(/[\u3011\uFF3D]/g, ']')
    .replace(/\[([^\]]+)\]/g, function normalizeBracketedCitation(match, body) {
      const normalizedBody = normalizeCitationHandleGlyphs(body);
      return CITATION_HANDLE_LIST_PATTERN.test(normalizedBody)
        ? `[${normalizedBody}]`
        : match;
    });
}

// Insert spaces between adjacent citation blocks and attached punctuation.
export function normalizeCitationSpacing(value) {
  return String(value || '')
    .replace(CITATION_INTER_BLOCK_JUNK_PATTERN, '$1 ')
    .replace(CITATION_LEADING_JUNK_PATTERN, '$1 ')
    .replace(
      CITATION_ATTACHED_PATTERN,
      '$1 [$2]'
    );
}

// Create an empty citation registry object.
export function createCitationRegistry() {
  return Object.create(null);
}


// Source URL helpers.
// Keep only http and https URLs safe for links and favicons.
function safeExternalUrl(value) {
  try {
    const parsed = new URL(String(value || '').trim());
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : '';
  } catch (_error) {
    return '';
  }
}

// Resolve one favicon URL from external links or the local favicon proxy.
function safeFaviconUrl(value) {
  const rawValue = String(value || '').trim();
  if (!rawValue) {
    return '';
  }
  if (rawValue.startsWith('/api/favicon/')) {
    return rawValue;
  }
  return safeExternalUrl(rawValue);
}

// Extract a hostname from one URL string.
function domainFromUrl(value) {
  try {
    return new URL(String(value || '').trim()).hostname.replace(/^www\./i, '');
  } catch (_error) {
    return '';
  }
}

// Build the favicon proxy URL for one domain when the name is safe.
function faviconUrlForDomain(domain) {
  const cleanDomain = String(domain || '').trim().replace(/^www\./i, '');
  return cleanDomain && !/[^a-z0-9.-]/i.test(cleanDomain)
    ? `/api/favicon/?domain=${encodeURIComponent(cleanDomain)}`
    : '';
}

// Read the best display domain from one citation source record.
function readSourceDomain(source) {
  const safeSource = source && typeof source === 'object' ? source : {};
  return String(
    safeSource.display_domain
    || safeSource.displayDomain
    || safeSource.domain
    || safeSource.host
    || domainFromUrl(safeSource.url || safeSource.link || safeSource.href || '')
    || ''
  ).trim().replace(/^www\./i, '');
}

// Read one labeled field from a text citation block.
function fieldFromCitationBlock(block, fieldName) {
  const knownFields = 'Citation handle|Evidence kind|Title|Domain|URL|Date|Preview|Content';
  const pattern = new RegExp(`(?:^|\\n)${fieldName}:\\s*([\\s\\S]*?)(?=\\n(?:${knownFields}):|$)`, 'i');
  const match = String(block || '').match(pattern);
  return match ? String(match[1] || '').trim() : '';
}

// Trim long citation text with an ellipsis suffix.
function compactText(value, maxLength) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text || text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, Math.max(0, maxLength - 1)).trim()}...`;
}

// Build a display title with Reddit-specific cleanup when needed.
function displayTitleForSource(source, domain) {
  const rawTitle = String(source && source.title || domain || '').replace(/\s+/g, ' ').trim();
  if (/reddit\.com$/i.test(domain)) {
    const redditTitle = rawTitle.match(/^r\s*\/\s*.+?\s+on\s+Reddit:\s*(.+)$/i);
    if (redditTitle && redditTitle[1]) {
      return compactText(redditTitle[1], CITATION_TITLE_MAX_CHARS);
    }
  }
  return compactText(rawTitle, CITATION_TITLE_MAX_CHARS);
}

// Normalize one raw source record into the registry shape.
function normalizeCitationSource(source, rank) {
  if (typeof source === 'string') {
    const url = safeExternalUrl(source);
    const domain = domainFromUrl(url || source);
    return domain ? { rank, url, domain, display_domain: domain } : null;
  }

  if (!source || typeof source !== 'object') {
    return null;
  }

  const url = safeExternalUrl(source.url || source.link || source.href || source.source_url || '');
  const domain = readSourceDomain({ ...source, url });
  if (!url && !domain) {
    return null;
  }

  return {
    ...source,
    rank: source.rank || rank || 0,
    url,
    domain,
    display_domain: String(source.display_domain || source.displayDomain || domain || '').trim(),
    favicon_url: source.favicon_url || source.faviconUrl || faviconUrlForDomain(domain),
    date: source.date || source.published_date || source.publishedDate || source.published_at || source.publishedAt || source.created_at || source.createdAt || '',
    preview: source.preview || source.snippet || source.summary || source.content || source.text || '',
  };
}

// Collect every known citation id alias from one source record.
function sourceIds(source) {
  return [
    source.id,
    source.source_id,
    source.sourceId,
    source.citation_id,
    source.citationId,
    source.citation_handle,
    source.citationHandle,
    source.handle
  ].map(normalizeCitationId).filter(isCitationHandleId);
}

// Flatten nested tool-result containers into source candidate arrays.
function collectSourceCandidates(container) {
  if (Array.isArray(container)) {
    return container;
  }
  if (!container || typeof container !== 'object') {
    return [];
  }
  return [
    container.sources,
    container.source_chips,
    container.sourceChips,
    container.results,
    container.items,
    container.documents,
    container.data
  ].filter(Array.isArray).flat();
}

// Parse one tool segment result JSON into a plain object.
function parseToolResultObject(segment) {
  const rawResult = segment && segment.result !== null && segment.result !== undefined ? String(segment.result) : '';
  if (!rawResult) {
    return {};
  }
  try {
    const parsed = JSON.parse(rawResult);
    return parsed && typeof parsed === 'object' && parsed.result && typeof parsed.result === 'object'
      ? parsed.result
      : (parsed || {});
  } catch (_error) {
    return {};
  }
}

// Parse citation blocks embedded in plain tool-result text.
function parseTextCitationSources(text) {
  const rawText = String(text || '');
  const starts = [];
  const startPattern = /(?:^|\n)Citation handle:\s*\[?([A-Za-z0-9-]+)\]?\s*/gi;
  let match = startPattern.exec(rawText);
  while (match) {
    starts.push({ index: match.index, id: match[1] });
    match = startPattern.exec(rawText);
  }

  return starts.map(function parseCitationBlock(start, index) {
    const endIndex = index + 1 < starts.length ? starts[index + 1].index : rawText.length;
    const id = normalizeCitationId(start.id);
    if (!isCitationHandleId(id)) {
      return null;
    }

    const block = rawText.slice(start.index, endIndex);
    const domain = fieldFromCitationBlock(block, 'Domain');
    return normalizeCitationSource({
      id,
      source_id: id,
      citation_id: id,
      citation_handle: id,
      title: fieldFromCitationBlock(block, 'Title'),
      domain,
      display_domain: domain,
      url: fieldFromCitationBlock(block, 'URL'),
      date: fieldFromCitationBlock(block, 'Date'),
      preview: fieldFromCitationBlock(block, 'Preview') || fieldFromCitationBlock(block, 'Content'),
      evidence_kind: fieldFromCitationBlock(block, 'Evidence kind'),
    }, index + 1);
  }).filter(Boolean);
}


// Citation registry API.
// Look up one normalized source record by citation handle id.
export function citationSourceForId(citationRegistry, sourceId) {
  if (!citationRegistry || typeof citationRegistry !== 'object') {
    return null;
  }
  const normalizedId = normalizeCitationId(sourceId);
  return citationRegistry[normalizedId] || citationRegistry[String(sourceId || '').toLowerCase()] || null;
}

// Register one source and all of its handle aliases in the registry.
export function addCitationSource(citationRegistry, source, rank) {
  if (!citationRegistry || !source) {
    return;
  }

  const normalizedSource = normalizeCitationSource(source, rank);
  if (!normalizedSource) {
    return;
  }

  sourceIds(normalizedSource).forEach(function registerSourceId(sourceId) {
    const existing = citationRegistry[sourceId];
    if (existing && safeExternalUrl(existing.url) && !safeExternalUrl(normalizedSource.url)) {
      return;
    }
    citationRegistry[sourceId] = normalizedSource;
    citationRegistry[sourceId.toLowerCase()] = normalizedSource;
  });
}

// Extract and register citation sources from one activity segment.
export function addSegmentCitationSources(citationRegistry, segment) {
  if (!citationRegistry || !segment || typeof segment !== 'object') {
    return citationRegistry;
  }

  const toolUi = segment.toolUi && typeof segment.toolUi === 'object' ? segment.toolUi : null;
  const compact = toolUi && toolUi.compact && typeof toolUi.compact === 'object' ? toolUi.compact : null;
  const resultObject = parseToolResultObject(segment);
  const structured = segment.structuredContent && typeof segment.structuredContent === 'object'
    ? segment.structuredContent
    : null;

  [
    ...collectSourceCandidates(structured),
    ...collectSourceCandidates(toolUi),
    ...collectSourceCandidates(compact),
    ...collectSourceCandidates(resultObject),
    ...parseTextCitationSources(segment.result),
    ...parseTextCitationSources(segment.text),
    ...parseTextCitationSources(segment.content),
    ...parseTextCitationSources(resultObject.content),
    ...parseTextCitationSources(resultObject.model_context),
  ].forEach(function registerSource(source, index) {
    addCitationSource(citationRegistry, source, index + 1);
  });

  return citationRegistry;
}

// Register citation sources from every segment in a list.
export function addSegmentsCitationSources(citationRegistry, segments) {
  (Array.isArray(segments) ? segments : []).forEach(function registerSegment(segment) {
    addSegmentCitationSources(citationRegistry, segment);
  });
  return citationRegistry;
}


// Citation chip rendering.
// Collect known citation ids referenced in one text fragment.
function extractCitationIds(value, citationRegistry) {
  const ids = [];
  const seen = Object.create(null);

  // Register one citation handle when it exists in the registry.
  function addId(candidate) {
    const id = normalizeCitationId(candidate);
    if (!id || seen[id] || !citationSourceForId(citationRegistry, id)) {
      return;
    }
    seen[id] = true;
    ids.push(id);
  }

  CITATION_SCAN_PATTERN.lastIndex = 0;
  let match = CITATION_SCAN_PATTERN.exec(String(value || ''));
  while (match) {
    addId(match[0]);
    match = CITATION_SCAN_PATTERN.exec(String(value || ''));
  }
  CITATION_SCAN_PATTERN.lastIndex = 0;

  String(value || '').split(/[\s,;]+/).forEach(addId);
  return ids;
}

// Report whether a text fragment contains any citation handle token.
function hasCitationHandle(value) {
  CITATION_SCAN_PATTERN.lastIndex = 0;
  const found = CITATION_SCAN_PATTERN.test(String(value || ''));
  CITATION_SCAN_PATTERN.lastIndex = 0;
  return found;
}

// Build one inline citation chip anchor for a registered source.
function renderCitationChip(source, sourceId) {
  const id = normalizeCitationId(sourceId || (source && source.id));
  if (!id || !source) {
    return '';
  }

  const domain = readSourceDomain(source) || id;
  const url = safeExternalUrl(source && source.url);
  if (!url) {
    return '';
  }
  const title = displayTitleForSource(source, domain) || id;
  const faviconUrl = safeFaviconUrl(source.favicon_url || source.faviconUrl || faviconUrlForDomain(domain));
  const previewData = {
    id,
    title,
    domain,
    url,
    faviconUrl,
    date: compactText(source.date || '', 80),
    evidenceKind: compactText(source.evidence_kind || source.evidenceKind || '', 80),
    preview: compactText(source.preview || source.snippet || source.summary || source.content || '', CITATION_PREVIEW_MAX_CHARS),
  };
  const faviconHtml = faviconUrl
    ? `<img class="msg-citation-favicon" src="${escapeAttributeValue(faviconUrl)}" alt="" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='inline-flex';">`
    : '';
  const fallbackStyle = faviconUrl ? ' style="display:none;"' : '';

  return `<a class="msg-citation-chip" aria-label="${escapeAttributeValue(title)}" href="${escapeAttributeValue(url)}" target="_blank" rel="noopener noreferrer" data-citation-id="${escapeAttributeValue(id)}" data-citation-preview="${escapeAttributeValue(JSON.stringify(previewData))}">${faviconHtml}<span class="msg-citation-fallback"${fallbackStyle}>${escHtml(domain.charAt(0).toUpperCase() || 'C')}</span><span class="msg-citation-domain">${escHtml(domain)}</span></a>`;
}

// Replace bracketed citation handles in HTML with interactive chips.
export function decorateCitationsInHtml(html, citationRegistry) {
  const template = document.createElement('template');
  template.innerHTML = html;
  const ignoredTags = new Set(['A', 'CODE', 'PRE', 'SCRIPT', 'STYLE', 'TEXTAREA']);

  // Walk the DOM tree and replace citation brackets in text nodes.
  function walk(node) {
    if (!node || (node.nodeType === Node.ELEMENT_NODE && ignoredTags.has(node.tagName))) {
      return;
    }

    if (node.nodeType === Node.TEXT_NODE) {
      const value = normalizeCitationSpacing(normalizeCitationBrackets(node.nodeValue || ''));
      const bracketPattern = /\[\s*([^\]]+)\s*\]/gi;
      if (!bracketPattern.test(value)) {
        return;
      }

      bracketPattern.lastIndex = 0;
      const fragment = document.createDocumentFragment();
      let lastIndex = 0;
      let changed = false;
      let match = bracketPattern.exec(value);

      while (match) {
        const ids = extractCitationIds(match[1], citationRegistry);
        fragment.appendChild(document.createTextNode(value.slice(lastIndex, match.index)));
        if (ids.length) {
          ids.forEach(function appendCitation(id, index) {
            if (index > 0) {
              fragment.appendChild(document.createTextNode(' '));
            }
            const chip = document.createElement('template');
            chip.innerHTML = renderCitationChip(citationSourceForId(citationRegistry, id), id);
            if (chip.content.firstChild) {
              fragment.appendChild(chip.content.cloneNode(true));
            }
          });
          changed = true;
        } else if (hasCitationHandle(match[1])) {
          changed = true;
        } else {
          fragment.appendChild(document.createTextNode(match[0]));
        }
        lastIndex = match.index + match[0].length;
        match = bracketPattern.exec(value);
      }

      fragment.appendChild(document.createTextNode(value.slice(lastIndex)));
      if (changed) {
        node.parentNode.replaceChild(fragment, node);
      }
      return;
    }

    Array.from(node.childNodes || []).forEach(walk);
  }

  walk(template.content);
  return template.innerHTML;
}
