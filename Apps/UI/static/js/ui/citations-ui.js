// Copyright NGGT.LightKeeper. All Rights Reserved.

import { escHtml, escapeAttributeValue } from '../main/utils.js';
import { postJson } from '../main/api.js';
import {
  collectParagraphHighlightNeedles,
  findRangesInText,
} from './citation-highlight-matching.js';

const CITATION_ID_PATTERN = /^(?:S\d+|SOURCE-(?:[A-Z0-9]+-)?\d+|C[A-Z0-9]{2,16}-\d+)$/;
const CITATION_SCAN_PATTERN = /\b(?:S\d+|SOURCE-(?:[A-Z0-9]+-)?\d+|C[A-Z0-9]{2,16}-\d+)\b/gi;
const CITATION_INLINE_NOISE_PATTERN = /[\u034f\u061c\u180e\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/g;
const CITATION_HANDLE_SOURCE = String.raw`(?:S\d+|source-(?:[a-z0-9]+-)?\d+|c[a-z0-9]{2,16}-\d+)`;
const CITATION_HANDLE_LIST_SOURCE = String.raw`${CITATION_HANDLE_SOURCE}(?:\s*,\s*${CITATION_HANDLE_SOURCE})*`;
const CITATION_HANDLE_LIST_PATTERN = new RegExp(String.raw`^\s*${CITATION_HANDLE_LIST_SOURCE}\s*$`, 'i');
const CITATION_BRACKET_SOURCE = String.raw`\[\s*${CITATION_HANDLE_LIST_SOURCE}\s*\]`;
const CITATION_GAP_SOURCE = String.raw`[\s\u00a0\u1680\u180e\u2000-\u200d\u2028\u2029\u202f\u205f\u2060\u3000\ufeff]*`;
const CITATION_JUNK_CLASS_SOURCE = String.raw`.,;:!?(){}<>|/\\'"\-\u00ad\u058a\u05be\u1400\u1806\u2010-\u2015\u2053\u207b\u208b\u2212\u2796\u2e17\u2e1a\u2e3a-\u2e3b\u2e40\u2e5d\u30a0\ufe31-\ufe32\ufe58\ufe63\uff0d`;
// Strip only short punctuation runs directly before a citation handle (never word text).
const CITATION_LEADING_JUNK_PATTERN = new RegExp(
  String.raw`[${CITATION_JUNK_CLASS_SOURCE}]{1,3}${CITATION_GAP_SOURCE}(?=${CITATION_BRACKET_SOURCE})`,
  'gi'
);
const CITATION_INTER_BLOCK_JUNK_PATTERN = new RegExp(
  String.raw`(${CITATION_BRACKET_SOURCE})${CITATION_GAP_SOURCE}[${CITATION_JUNK_CLASS_SOURCE}]+${CITATION_GAP_SOURCE}(?=${CITATION_BRACKET_SOURCE})`,
  'gi'
);
const CITATION_ATTACHED_PATTERN = new RegExp(String.raw`([^\s\[(])\[(${CITATION_HANDLE_LIST_SOURCE})\]`, 'gi');
const CITATION_TITLE_MAX_CHARS = 180;
const CITATION_PREVIEW_MAX_CHARS = 520;
const CITATION_SOURCE_TEXT_MAX_CHARS = 3000;
const CITATION_ANNOTATION_ENDPOINT = '/api/citation_annotations/';

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

function normalizeCitationHandleGlyphs(value) {
  return Array.from(String(value || '').replace(CITATION_INLINE_NOISE_PATTERN, ''))
    .map(function normalizeCitationGlyph(character) {
      return isCitationDashCodePoint(character.codePointAt(0)) ? '-' : character;
    })
    .join('');
}

export function normalizeCitationId(value) {
  return normalizeCitationHandleGlyphs(value)
    .trim()
    .replace(/^\[|\]$/g, '')
    .replace(/[.,;:!?]+$/g, '')
    .toUpperCase();
}

export function isCitationHandleId(value) {
  return CITATION_ID_PATTERN.test(normalizeCitationId(value));
}

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

export function normalizeCitationSpacing(value) {
  return String(value || '')
    .replace(CITATION_INTER_BLOCK_JUNK_PATTERN, '$1 ')
    .replace(CITATION_LEADING_JUNK_PATTERN, ' ')
    .replace(
      CITATION_ATTACHED_PATTERN,
      '$1 [$2]'
    );
}

/** Normalize common assistant-markdown glitches before marked.parse. */
export function normalizeAssistantMarkdown(value) {
  let text = normalizeCitationSpacing(normalizeCitationBrackets(value));
  // CJK citation brackets -> ASCII (【cc19-1】).
  text = text.replace(/【\s*([^\s】]+?)\s*】/g, '[$1]');
  // Broken quote + backtick: "foo`bar` -> "foo" `bar`
  text = text.replace(/"([^"\n`]+)`([^`\n]+)`/g, '"$1" `$2`');
  text = text.replace(/'([^'\n`]+)`([^`\n]+)`/g, '\'$1\' `$2`');
  // Curly quotes -> straight for predictable marked parsing.
  text = text.replace(/[\u201c\u201d]/g, '"').replace(/[\u2018\u2019]/g, '\'');
  // Pipe-separated numeric rows: 0.43|0.87 -> 0.43 | 0.87
  text = text.replace(/([$€₽]?\d[\d,]*(?:\.\d+)?)\s*\|\s*([$€₽]?\d)/g, '$1 | $2');
  // Keep word boundaries around slashes in prices: output/M; -> output /M;
  text = text.replace(/([A-Za-z])(\/\s*[$€₽]?\d)/g, '$1 $2');
  text = text.replace(/([$€₽]?\d[\d,.]*\/[A-Za-z])([A-Za-z])/g, '$1 $2');
  return text;
}

export function createCitationRegistry() {
  return Object.create(null);
}

function safeExternalUrl(value) {
  try {
    const parsed = new URL(String(value || '').trim());
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : '';
  } catch (_error) {
    return '';
  }
}

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

function domainFromUrl(value) {
  try {
    return new URL(String(value || '').trim()).hostname.replace(/^www\./i, '');
  } catch (_error) {
    return '';
  }
}

function faviconUrlForDomain(domain) {
  const cleanDomain = String(domain || '').trim().replace(/^www\./i, '');
  return cleanDomain && !/[^a-z0-9.-]/i.test(cleanDomain)
    ? `/api/favicon/?domain=${encodeURIComponent(cleanDomain)}`
    : '';
}

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

function fieldFromCitationBlock(block, fieldName) {
  const knownFields = 'Citation handle|Evidence kind|Title|Domain|URL|Date|Preview|Content';
  const pattern = new RegExp(`(?:^|\\n)${fieldName}:\\s*([\\s\\S]*?)(?=\\n(?:${knownFields}):|$)`, 'i');
  const match = String(block || '').match(pattern);
  return match ? String(match[1] || '').trim() : '';
}

function compactText(value, maxLength) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text || text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, Math.max(0, maxLength - 1)).trim()}...`;
}

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

export function citationSourceForId(citationRegistry, sourceId) {
  if (!citationRegistry || typeof citationRegistry !== 'object') {
    return null;
  }
  const normalizedId = normalizeCitationId(sourceId);
  return citationRegistry[normalizedId] || citationRegistry[String(sourceId || '').toLowerCase()] || null;
}

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

export function addSegmentsCitationSources(citationRegistry, segments) {
  (Array.isArray(segments) ? segments : []).forEach(function registerSegment(segment) {
    addSegmentCitationSources(citationRegistry, segment);
  });
  return citationRegistry;
}

function extractCitationIds(value, citationRegistry) {
  const ids = [];
  const seen = Object.create(null);

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

function hasCitationHandle(value) {
  CITATION_SCAN_PATTERN.lastIndex = 0;
  const found = CITATION_SCAN_PATTERN.test(String(value || ''));
  CITATION_SCAN_PATTERN.lastIndex = 0;
  return found;
}

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
    sourceText: compactText(source.content || source.text || source.preview || source.snippet || source.summary || '', CITATION_SOURCE_TEXT_MAX_CHARS),
  };
  const faviconHtml = faviconUrl
    ? `<img class="msg-citation-favicon" src="${escapeAttributeValue(faviconUrl)}" alt="" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='inline-flex';">`
    : '';
  const fallbackStyle = faviconUrl ? ' style="display:none;"' : '';

  return `<a class="msg-citation-chip" aria-label="${escapeAttributeValue(title)}" href="${escapeAttributeValue(url)}" target="_blank" rel="noopener noreferrer" data-citation-id="${escapeAttributeValue(id)}" data-citation-preview="${escapeAttributeValue(JSON.stringify(previewData))}">${faviconHtml}<span class="msg-citation-fallback"${fallbackStyle}>${escHtml(domain.charAt(0).toUpperCase() || 'C')}</span><span class="msg-citation-domain">${escHtml(domain)}</span></a>`;
}

function parseCitationPreviewData(chip) {
  try {
    const parsed = JSON.parse(String(chip && chip.getAttribute('data-citation-preview') || ''));
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch (_error) {
    return null;
  }
}

function ensureCitationAnnotationKey(chip, index) {
  const existing = String(chip && chip.getAttribute('data-citation-annotation-key') || '').trim();
  if (existing) {
    return existing;
  }
  const sourceId = normalizeCitationId(chip && chip.getAttribute('data-citation-id') || '');
  const key = `${sourceId || 'CITATION'}-${index + 1}`;
  if (chip && chip.setAttribute) {
    chip.setAttribute('data-citation-annotation-key', key);
  }
  return key;
}

function citationParagraphForChip(chip) {
  if (!chip || !chip.closest) {
    return null;
  }
  // Table cells are the most specific context — a chip inside <td> or <th>
  // should only highlight text within that cell.
  const tableCell = chip.closest('td, th');
  if (tableCell) {
    return tableCell;
  }
  const blockquote = chip.closest('blockquote');
  if (blockquote) {
    return blockquote;
  }
  const listItem = chip.closest('li');
  if (listItem) {
    return listItem;
  }
  // Definition list items.
  const defItem = chip.closest('dd, dt');
  if (defItem) {
    return defItem;
  }
  const paragraph = chip.closest('p');
  if (paragraph) {
    return paragraph;
  }
  const sectionBlock = chip.closest('section, article, .msg-stream-text, .msg-bubble');
  if (sectionBlock) {
    return sectionBlock;
  }
  return chip.closest('.markdown-body') || chip.parentNode || null;
}

function extractTableColumnContext(tableCell) {
  const table = tableCell && tableCell.closest ? tableCell.closest('table') : null;
  if (!table) {
    return '';
  }
  const row = tableCell.closest('tr');
  if (!row || !row.children || !row.children.length) {
    return '';
  }
  const cells = Array.from(row.children);
  const columnIndex = Math.max(0, cells.indexOf(tableCell));
  const headerCell = table.querySelector(`thead tr th:nth-child(${columnIndex + 1}), thead tr td:nth-child(${columnIndex + 1})`);
  const rowLabelCell = cells[0] || null;
  const parts = [];
  if (headerCell) {
    parts.push(String(headerCell.textContent || '').trim());
  }
  if (rowLabelCell && rowLabelCell !== tableCell) {
    parts.push(String(rowLabelCell.textContent || '').trim());
  }
  return parts.filter(Boolean).join('. ');
}

function extractCleanParagraphText(container) {
  if (!container) {
    return '';
  }
  const clone = container.cloneNode(true);
  Array.from(clone.querySelectorAll('.msg-citation-chip')).forEach(function replaceChip(chip) {
    const parent = chip.parentNode;
    if (!parent) {
      return;
    }
    parent.replaceChild(document.createTextNode(' '), chip);
  });
  return String(clone.textContent || '').replace(/\s+/g, ' ').trim();
}

function citationAnnotationPayload(root) {
  return Array.from((root || document).querySelectorAll('.msg-citation-chip[data-citation-id][data-citation-preview]'))
    .map(function mapCitationChip(chip, index) {
      const data = parseCitationPreviewData(chip);
      const paragraph = citationParagraphForChip(chip);
      if (!data || !paragraph) {
        return null;
      }
      const annotationKey = ensureCitationAnnotationKey(chip, index);
      const tableContext = paragraph.matches && paragraph.matches('td, th')
        ? extractTableColumnContext(paragraph)
        : '';
      const paragraphText = extractCleanParagraphText(paragraph);
      const scopedParagraphText = [tableContext, paragraphText].filter(Boolean).join('. ');
      return {
        annotation_id: annotationKey,
        id: chip.getAttribute('data-citation-id') || data.id || '',
        paragraph_text: scopedParagraphText,
        source: {
          title: data.title || '',
          domain: data.domain || '',
          url: data.url || '',
          preview: data.sourceText || data.preview || ''
        }
      };
    })
    .filter(Boolean);
}

function clearCitationHighlights(root) {
  const scope = root || document;
  Array.from(scope.querySelectorAll('.msg-citation-highlight')).forEach(function unwrapHighlight(node) {
    const parent = node.parentNode;
    if (!parent) {
      return;
    }
    parent.replaceChild(document.createTextNode(node.textContent || ''), node);
  });
  if (scope && scope.normalize) {
    scope.normalize();
  }
}

function annotationMatchTexts(annotation, containerText) {
  return collectParagraphHighlightNeedles(annotation, containerText);
}

function highlightTextMatches(container, needles) {
  if (!container || !needles.length) {
    return;
  }
  const ignoredTags = new Set(['A', 'CODE', 'PRE', 'SCRIPT', 'STYLE', 'TEXTAREA']);
  const walker = document.createTreeWalker(
    container,
    NodeFilter.SHOW_TEXT,
    {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent || node.nodeValue == null || node.nodeValue === '') {
          return NodeFilter.FILTER_REJECT;
        }
        if (parent.closest('.msg-citation-chip, .msg-citation-highlight') || ignoredTags.has(parent.tagName)) {
          return NodeFilter.FILTER_REJECT;
        }
        // Keep whitespace-only text nodes — they hold spaces between <em>/<strong> runs.
        return NodeFilter.FILTER_ACCEPT;
      }
    }
  );

  // Collect all eligible text nodes and build a flat concatenated string.
  // This allows needles to match across inline formatting boundaries
  // (e.g. <strong>, <em>) where a sentence spans multiple sibling text nodes.
  const textNodes = [];
  const nodeOffsets = [];
  let flatText = '';
  let node = walker.nextNode();
  while (node) {
    nodeOffsets.push(flatText.length);
    textNodes.push(node);
    flatText += node.nodeValue || '';
    node = walker.nextNode();
  }

  if (!textNodes.length) {
    return;
  }

  const ranges = findRangesInText(flatText, needles);
  if (!ranges.length) {
    return;
  }

  // Map flat-text ranges back to individual text nodes and wrap in reverse
  // order so that DOM mutations don't shift the unprocessed nodes.
  for (let i = textNodes.length - 1; i >= 0; i--) {
    const textNode = textNodes[i];
    const nodeStart = nodeOffsets[i];
    const nodeLen = (textNode.nodeValue || '').length;
    const nodeEnd = nodeStart + nodeLen;

    const nodeRanges = ranges
      .filter(function overlapsNode(r) { return r.start < nodeEnd && r.end > nodeStart; })
      .map(function toLocalRange(r) {
        return {
          start: Math.max(r.start, nodeStart) - nodeStart,
          end: Math.min(r.end, nodeEnd) - nodeStart,
        };
      });

    if (!nodeRanges.length) {
      continue;
    }

    const value = textNode.nodeValue || '';
    const fragment = document.createDocumentFragment();
    let cursor = 0;
    nodeRanges.forEach(function appendRange(range) {
      if (range.start > cursor) {
        fragment.appendChild(document.createTextNode(value.slice(cursor, range.start)));
      }
      const mark = document.createElement('span');
      mark.className = 'msg-citation-highlight is-active';
      mark.textContent = value.slice(range.start, range.end);
      fragment.appendChild(mark);
      cursor = range.end;
    });
    if (cursor < value.length) {
      fragment.appendChild(document.createTextNode(value.slice(cursor)));
    }
    if (textNode.parentNode) {
      textNode.parentNode.replaceChild(fragment, textNode);
    }
  }
}

function applyCitationAnnotation(chip, annotation) {
  const status = String(annotation && annotation.status || 'fallback');
  chip.classList.remove('is-citation-annotating', 'is-citation-annotated', 'is-citation-fallback');
  chip.setAttribute('data-citation-annotation-state', status);
  if (status === 'ready') {
    chip.classList.add('is-citation-annotated');
    chip.setAttribute('data-citation-annotation', JSON.stringify(annotation));
  } else {
    chip.classList.add('is-citation-fallback');
    chip.removeAttribute('data-citation-annotation');
  }
  // Dispatch a custom event to notify listeners (like citation-preview-ui) of the state change!
  chip.dispatchEvent(new CustomEvent('citation-annotation-updated', {
    bubbles: true,
    detail: annotation
  }));
}

function applyCitationAnnotations(root, annotations) {
  const byAnnotationId = Object.create(null);
  const bySourceId = Object.create(null);
  (Array.isArray(annotations) ? annotations : []).forEach(function indexAnnotation(annotation) {
    if (annotation && annotation.id) {
      bySourceId[normalizeCitationId(annotation.id)] = annotation;
    }
    if (annotation && annotation.annotation_id) {
      byAnnotationId[String(annotation.annotation_id)] = annotation;
    }
  });
  Array.from((root || document).querySelectorAll('.msg-citation-chip[data-citation-id]')).forEach(function markChip(chip) {
    const annotationKey = String(chip.getAttribute('data-citation-annotation-key') || '');
    const id = normalizeCitationId(chip.getAttribute('data-citation-id') || '');
    applyCitationAnnotation(
      chip,
      byAnnotationId[annotationKey] || bySourceId[id] || { id, annotation_id: annotationKey, status: 'fallback', matches: [] }
    );
  });
}

export function scheduleCitationAnnotations(root) {
  const target = root || document;
  if (!target || target.__aslmCitationAnnotationsRequested) {
    return;
  }
  const payload = citationAnnotationPayload(target);
  if (!payload.length) {
    return;
  }
  target.__aslmCitationAnnotationsRequested = true;
  Array.from(target.querySelectorAll('.msg-citation-chip[data-citation-id][data-citation-preview]')).forEach(function markLoading(chip, index) {
    ensureCitationAnnotationKey(chip, index);
    chip.classList.add('is-citation-annotating');
    chip.setAttribute('data-citation-annotation-state', 'loading');
  });
  window.setTimeout(function requestCitationAnnotations() {
    postJson(CITATION_ANNOTATION_ENDPOINT, { citations: payload })
      .then(function onCitationAnnotations(data) {
        if (data && data.reranker && typeof console !== 'undefined' && console.info) {
          console.info('[ASLM citations] GTE reranker', data.reranker);
        }
        if (!data || data.enabled === false) {
          Array.from(target.querySelectorAll('.msg-citation-chip.is-citation-annotating')).forEach(function clearLoading(chip) {
            chip.classList.remove('is-citation-annotating');
            chip.setAttribute('data-citation-annotation-state', 'fallback');
          });
          return;
        }
        applyCitationAnnotations(target, data.annotations || []);
      })
      .catch(function onCitationAnnotationError() {
        Array.from(target.querySelectorAll('.msg-citation-chip.is-citation-annotating')).forEach(function fallbackChip(chip) {
          applyCitationAnnotation(chip, {
            id: chip.getAttribute('data-citation-id') || '',
            annotation_id: chip.getAttribute('data-citation-annotation-key') || '',
            status: 'fallback',
            matches: []
          });
        });
      });
  }, 20);
}

export function bindCitationAnnotationHighlights(root) {
  const eventRoot = root || document;
  if (!eventRoot || eventRoot.__aslmCitationAnnotationHighlightsBound) {
    return;
  }
  eventRoot.__aslmCitationAnnotationHighlightsBound = true;

  function showCitationHighlight(chip) {
    if (!chip || !eventRoot.contains(chip)) {
      return;
    }
    let annotation = null;
    try {
      annotation = JSON.parse(chip.getAttribute('data-citation-annotation') || '');
    } catch (_error) {
      annotation = null;
    }
    const paragraph = citationParagraphForChip(chip);
    if (!paragraph || !annotation) {
      return;
    }
    clearCitationHighlights(paragraph);
    highlightTextMatches(paragraph, annotationMatchTexts(annotation, extractCleanParagraphText(paragraph)));
  }

  function hideCitationHighlight(chip) {
    clearCitationHighlights(citationParagraphForChip(chip) || eventRoot);
  }

  function chipFromEvent(event) {
    const chip = event.target.closest && event.target.closest('.msg-citation-chip[data-citation-annotation]');
    return chip && eventRoot.contains(chip) ? chip : null;
  }

  function onCitationHighlightEnter(event) {
    const chip = chipFromEvent(event);
    if (chip) {
      showCitationHighlight(chip);
    }
  }

  function onCitationHighlightLeave(event) {
    const chip = chipFromEvent(event);
    if (chip && (!event.relatedTarget || !chip.contains(event.relatedTarget))) {
      hideCitationHighlight(chip);
    }
  }

  eventRoot.addEventListener('pointerover', onCitationHighlightEnter, true);
  eventRoot.addEventListener('mouseover', onCitationHighlightEnter, true);
  eventRoot.addEventListener('focusin', onCitationHighlightEnter, true);
  eventRoot.addEventListener('click', function onCitationHighlightClick(event) {
    const chip = chipFromEvent(event);
    if (chip) {
      showCitationHighlight(chip);
    }
  }, true);

  eventRoot.addEventListener('pointerout', onCitationHighlightLeave, true);
  eventRoot.addEventListener('mouseout', onCitationHighlightLeave, true);
  eventRoot.addEventListener('focusout', onCitationHighlightLeave, true);
}

export function decorateCitationsInHtml(html, citationRegistry) {
  const template = document.createElement('template');
  template.innerHTML = html;
  const ignoredTags = new Set(['A', 'CODE', 'PRE', 'SCRIPT', 'STYLE', 'TEXTAREA']);

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
