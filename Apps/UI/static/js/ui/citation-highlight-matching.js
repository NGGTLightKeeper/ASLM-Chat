// Copyright NGGT.LightKeeper. All Rights Reserved.

/** Shared citation highlight needle selection and range matching. */

export function escapeRegex(value) {
  return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function isTableRowNeedle(value) {
  return String(value || '').split('|').length >= 4;
}

export function isWorthyNumberNeedle(value) {
  const text = String(value || '').trim();
  if (text.length < 4) {
    return false;
  }
  if (/[$€₽%％]/.test(text)) {
    return true;
  }
  if (/[.,]\d/.test(text) || /\d[.,]/.test(text)) {
    return true;
  }
  const digits = text.replace(/\D/g, '');
  return digits.length >= 4;
}

export function needleTooLongForContainer(needle, containerLength, maxRatio) {
  const limit = Math.max(24, Number(containerLength || 0) * (maxRatio || 0.72));
  return String(needle || '').length > limit;
}

function tokenizeNeedle(needle) {
  let normalized = String(needle || '').trim()
    .replace(/([\p{Ll}\p{Lo}])([\p{Lu}\p{Lt}])/gu, '$1 $2')
    .replace(/([\p{L}])([\p{N}])/gu, '$1 $2')
    .replace(/([\p{N}])([\p{L}])/gu, '$1 $2');
  return normalized.split(/[^\p{L}\p{N}$%.]+/u).filter(function keepToken(token) {
    return token.length > 0;
  });
}

export function shouldUseFlexibleNeedle(needle, sourceLength) {
  const text = String(needle || '').trim();
  if (!text || isTableRowNeedle(text)) {
    return false;
  }
  if (needleTooLongForContainer(text, sourceLength, 0.85)) {
    return false;
  }
  const tokens = tokenizeNeedle(text);
  return tokens.length >= 2 && text.length >= 12;
}

export function flexibleNeedlePattern(needle) {
  const tokens = tokenizeNeedle(needle);
  if (!tokens.length) {
    return '';
  }
  const gap = tokens.length >= 6 ? '[^\\p{L}\\p{N}$%.]{0,6}' : '[^\\p{L}\\p{N}$%.]{0,3}';
  return tokens.map(function flexibleToken(token) {
    return escapeRegex(token).replace(/\\[.,]/g, '[.,]');
  }).join(gap);
}

export function mergeHighlightRanges(ranges) {
  if (!ranges.length) {
    return [];
  }
  const sorted = ranges.slice().sort(function byStart(a, b) { return a.start - b.start; });
  const merged = [{ start: sorted[0].start, end: sorted[0].end }];
  for (let i = 1; i < sorted.length; i++) {
    const current = sorted[i];
    const last = merged[merged.length - 1];
    if (current.start <= last.end + 1) {
      last.end = Math.max(last.end, current.end);
    } else {
      merged.push({ start: current.start, end: current.end });
    }
  }
  return merged;
}

export function collectParagraphHighlightNeedles(annotation, containerText) {
  const matches = annotation && Array.isArray(annotation.matches) ? annotation.matches : [];
  const containerLength = String(containerText || '').length || 1;
  const seen = Object.create(null);
  const buckets = { quote: [], paragraph_sentence: [], entity: [], number: [] };

  function keepNeedle(value) {
    const text = String(value || '').trim();
    const key = text.toLowerCase();
    if (text.length < 3 || seen[key] || isTableRowNeedle(text)) {
      return false;
    }
    // For short containers (e.g. table cells) allow longer needles relative to container.
    const ratio = containerLength < 150 ? 0.85 : 0.72;
    if (needleTooLongForContainer(text, containerLength, ratio)) {
      return false;
    }
    seen[key] = true;
    return true;
  }

  matches.forEach(function routeMatch(match) {
    const type = String(match && match.type || '');
    const text = String(match && match.text || '').trim();
    if (!text) {
      return;
    }
    if (type === 'number' && !isWorthyNumberNeedle(text)) {
      return;
    }
    if (type === 'source_sentence') {
      return;
    }
    if (!keepNeedle(text)) {
      return;
    }
    if (buckets[type]) {
      buckets[type].push(text);
    }
  });

  const paragraphSentences = annotation && Array.isArray(annotation.paragraphSentences)
    ? annotation.paragraphSentences
    : [];
  paragraphSentences.forEach(function addSentence(sentence) {
    const text = String(sentence || '').trim();
    if (!text || isTableRowNeedle(text)) {
      return;
    }
    const key = text.toLowerCase();
    if (seen[key]) {
      return;
    }
    // Paragraph sentences come from the paragraph itself so they always exist in
    // the DOM — skip the needleTooLongForContainer check that would reject them
    // when the bullet is one long sentence.
    seen[key] = true;
    buckets.paragraph_sentence.push(text);
  });

  return [
    ...buckets.quote,
    ...buckets.paragraph_sentence,
    ...buckets.entity,
    ...buckets.number,
  ].sort(function longestFirst(a, b) { return b.length - a.length; });
}

export function collectPreviewHighlightNeedles(annotation, previewText) {
  const matches = annotation && Array.isArray(annotation.matches) ? annotation.matches : [];
  const previewLength = String(previewText || '').length || 1;
  const seen = Object.create(null);
  const needles = [];

  function keepNeedle(value) {
    const text = String(value || '').trim();
    const key = text.toLowerCase();
    if (text.length < 3 || seen[key] || isTableRowNeedle(text)) {
      return false;
    }
    if (needleTooLongForContainer(text, previewLength, 0.72)) {
      return false;
    }
    seen[key] = true;
    return true;
  }

  // The preview card shows source sentences — highlight those first; quotes from
  // the paragraph text won't appear in the source excerpt, so skip them here.
  matches.forEach(function routeMatch(match) {
    const type = String(match && match.type || '');
    const text = String(match && match.text || '').trim();
    if (!text) {
      return;
    }
    if (type === 'source_sentence' && keepNeedle(text)) {
      needles.push(text);
      return;
    }
    if (type === 'number' && isWorthyNumberNeedle(text) && keepNeedle(text)) {
      needles.push(text);
    }
  });

  if (!needles.length) {
    // Fallback: try quote or paragraph sentence — something is better than nothing.
    matches.forEach(function fallbackSentence(match) {
      const type = String(match && match.type || '');
      const text = String(match && match.text || '').trim();
      if ((type === 'quote' || type === 'paragraph_sentence') && keepNeedle(text)) {
        needles.push(text);
      }
    });
  }

  return needles.sort(function longestFirst(a, b) { return b.length - a.length; });
}

export function findRangesInText(source, needles) {
  const lower = source.toLowerCase();
  const ranges = [];
  needles.forEach(function findNeedle(needle) {
    const target = needle.toLowerCase();
    let foundExact = false;
    let index = lower.indexOf(target);
    while (index !== -1) {
      foundExact = true;
      const end = index + target.length;
      ranges.push({ start: index, end });
      index = lower.indexOf(target, index + Math.max(1, target.length));
    }
    if (!foundExact && shouldUseFlexibleNeedle(needle, source.length)) {
      const flexiblePattern = flexibleNeedlePattern(needle);
      if (!flexiblePattern) {
        return;
      }
      const regex = new RegExp(flexiblePattern, 'giu');
      let regexMatch = regex.exec(source);
      while (regexMatch) {
        const start = regexMatch.index;
        const end = start + regexMatch[0].length;
        if (end - start >= Math.max(needle.length * 0.7, 16)) {
          ranges.push({ start, end });
        }
        regexMatch = regex.exec(source);
      }
    }
  });
  return mergeHighlightRanges(ranges);
}
