// Copyright NGGT.LightKeeper. All Rights Reserved.

import { escHtml, escapeAttributeValue } from '../main/utils.js';


// Preview data helpers.
// Parse citation preview JSON stored on one chip element.
function parseCitationPreviewData(chip) {
  try {
    const parsed = JSON.parse(String(chip && chip.getAttribute('data-citation-preview') || ''));
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch (_error) {
    return null;
  }
}

// Format one evidence-kind label for the preview footer.
function previewEvidenceLabel(value) {
  const evidence = String(value || '').trim();
  if (!evidence) {
    return '';
  }
  if (/parsed/i.test(evidence)) {
    return 'Parsed';
  }
  if (/preview/i.test(evidence)) {
    return 'Preview';
  }
  return evidence
    .replace(/_/g, ' ')
    .replace(/\b\w/g, function titleCase(letter) { return letter.toUpperCase(); });
}

// Build the hover-card HTML for one citation preview payload.
function renderCitationPreviewHtml(data) {
  const evidenceLabel = previewEvidenceLabel(data.evidenceKind);
  const faviconHtml = data.faviconUrl
    ? `<img class="msg-citation-preview-favicon" src="${escapeAttributeValue(data.faviconUrl)}" alt="" onerror="this.style.display='none';this.nextElementSibling.style.display='inline-flex';">`
    : '';
  const fallbackStyle = data.faviconUrl ? ' style="display:none;"' : '';
  const previewHtml = data.preview
    ? `<div class="msg-citation-preview-text">${escHtml(data.preview)}</div>`
    : '';
  const dateHtml = data.date
    ? `<div class="msg-citation-preview-date">${escHtml(data.date)}</div>`
    : '';
  const statusHtml = evidenceLabel
    ? `<span class="msg-citation-preview-status">${escHtml(evidenceLabel)}</span>`
    : '<span></span>';

  return `
    <div class="msg-citation-preview-head">
      ${faviconHtml}<span class="msg-citation-preview-fallback"${fallbackStyle}>${escHtml(String(data.domain || data.id || 'C').charAt(0).toUpperCase())}</span>
      <div class="msg-citation-preview-title-wrap">
        <div class="msg-citation-preview-title">${escHtml(data.title || data.domain || data.id || 'Source')}</div>
        <div class="msg-citation-preview-domain">${escHtml(data.domain || '')}</div>
      </div>
    </div>
    ${previewHtml}
    ${dateHtml}
    <div class="msg-citation-preview-footer">
      <div class="msg-citation-preview-actions">
        <a class="msg-citation-preview-btn" href="${escapeAttributeValue(data.url || '#')}" target="_blank" rel="noopener noreferrer" title="Open source" aria-label="Open source">
          <img src="/static/img/ui/open-source.svg" alt="" aria-hidden="true">
        </a>
        <button type="button" class="msg-citation-preview-btn" data-citation-copy-url="${escapeAttributeValue(data.url || '')}" title="Copy link" aria-label="Copy link">
          <img src="/static/img/ui/copy-link.svg" alt="" aria-hidden="true">
        </button>
      </div>
      ${statusHtml}
    </div>
  `;
}


// Clipboard helpers.
// Copy text with a hidden textarea fallback for older browsers.
function fallbackCopyText(text, onDone) {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.cssText = 'position:fixed;top:-9999px;left:-9999px;opacity:0';
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  try {
    document.execCommand('copy');
    onDone && onDone();
  } catch (_error) {
    // Ignore clipboard failures; the button simply will not flip to copied.
  }
  document.body.removeChild(textarea);
}

// Copy text using the Clipboard API with textarea fallback.
function copyTextToClipboard(text, onDone) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(onDone).catch(function fallbackClipboard() {
      fallbackCopyText(text, onDone);
    });
    return;
  }
  fallbackCopyText(text, onDone);
}


// Citation preview cards.
// Bind hover and focus preview cards for citation chips under one root.
export function bindCitationPreviewCards(root) {
  const eventRoot = root || document;
  if (!eventRoot || eventRoot.__aslmCitationPreviewBound) {
    return;
  }
  eventRoot.__aslmCitationPreviewBound = true;

  let openTimer = null;
  let closeTimer = null;
  let activeChip = null;
  let previewEl = null;

  // Cancel a pending delayed open timer.
  function cancelOpen() {
    clearTimeout(openTimer);
    openTimer = null;
  }

  // Cancel a pending delayed close timer.
  function cancelClose() {
    clearTimeout(closeTimer);
    closeTimer = null;
  }

  // Hide the floating preview card.
  function hidePreview() {
    if (previewEl) {
      previewEl.classList.remove('is-visible');
    }
    activeChip = null;
  }

  // Schedule hiding the preview after the pointer leaves the chip.
  function scheduleClose() {
    cancelOpen();
    cancelClose();
    closeTimer = setTimeout(hidePreview, 180);
  }

  // Create or return the singleton preview card element.
  function ensurePreview() {
    if (previewEl) {
      return previewEl;
    }
    previewEl = document.createElement('div');
    previewEl.className = 'msg-citation-preview-card';
    previewEl.setAttribute('role', 'dialog');
    previewEl.addEventListener('mouseenter', cancelClose);
    previewEl.addEventListener('mouseleave', scheduleClose);
    previewEl.addEventListener('click', function onPreviewClick(event) {
      event.stopPropagation();
      const copyButton = event.target.closest('[data-citation-copy-url]');
      if (!copyButton) {
        return;
      }
      const url = copyButton.getAttribute('data-citation-copy-url') || '';
      if (!url) {
        return;
      }
      copyTextToClipboard(url, function onCopied() {
        const originalHtml = copyButton.innerHTML;
        copyButton.classList.add('is-copied');
        copyButton.innerHTML = '<img src="/static/img/ui/copy-success.svg" alt="" aria-hidden="true">';
        setTimeout(function restoreCopyButton() {
          copyButton.classList.remove('is-copied');
          copyButton.innerHTML = originalHtml;
        }, 1200);
      });
    });
    document.body.appendChild(previewEl);
    return previewEl;
  }

  // Position the preview card near the active citation chip.
  function positionPreview(chip) {
    const card = ensurePreview();
    const chipRect = chip.getBoundingClientRect();
    const cardRect = card.getBoundingClientRect();
    const gap = 10;
    let left = chipRect.left + (chipRect.width / 2) - (cardRect.width / 2);
    let top = chipRect.bottom + gap;

    left = Math.max(12, Math.min(left, window.innerWidth - cardRect.width - 12));
    if (top + cardRect.height > window.innerHeight - 12) {
      top = chipRect.top - cardRect.height - gap;
    }
    card.style.left = `${Math.max(12, left)}px`;
    card.style.top = `${Math.max(12, top)}px`;
  }

  // Render and show the preview card for one chip.
  function showPreview(chip) {
    const data = parseCitationPreviewData(chip);
    if (!data || !data.url) {
      return;
    }
    activeChip = chip;
    const card = ensurePreview();
    card.innerHTML = renderCitationPreviewHtml(data);
    card.classList.add('is-visible');
    positionPreview(chip);
  }

  // Open the preview after a short hover delay.
  function scheduleOpen(chip) {
    cancelOpen();
    cancelClose();
    openTimer = setTimeout(function delayedCitationPreview() {
      showPreview(chip);
    }, 320);
  }

  eventRoot.addEventListener('mouseover', function onCitationMouseOver(event) {
    const chip = event.target.closest && event.target.closest('.msg-citation-chip[data-citation-preview]');
    if (chip && eventRoot.contains(chip)) {
      scheduleOpen(chip);
    }
  });

  eventRoot.addEventListener('mouseout', function onCitationMouseOut(event) {
    const chip = event.target.closest && event.target.closest('.msg-citation-chip[data-citation-preview]');
    if (!chip || !eventRoot.contains(chip)) {
      return;
    }
    if (!event.relatedTarget || !chip.contains(event.relatedTarget)) {
      scheduleClose();
    }
  });

  eventRoot.addEventListener('focusin', function onCitationFocus(event) {
    const chip = event.target.closest && event.target.closest('.msg-citation-chip[data-citation-preview]');
    if (chip && eventRoot.contains(chip)) {
      showPreview(chip);
    }
  });

  eventRoot.addEventListener('focusout', function onCitationBlur(event) {
    const chip = event.target.closest && event.target.closest('.msg-citation-chip[data-citation-preview]');
    if (chip && eventRoot.contains(chip)) {
      scheduleClose();
    }
  });

  window.addEventListener('scroll', function onCitationPreviewScroll() {
    if (activeChip && previewEl && previewEl.classList.contains('is-visible')) {
      positionPreview(activeChip);
    }
  }, true);

  window.addEventListener('resize', function onCitationPreviewResize() {
    if (activeChip && previewEl && previewEl.classList.contains('is-visible')) {
      positionPreview(activeChip);
    }
  });
}
