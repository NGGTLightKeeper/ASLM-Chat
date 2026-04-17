// Copyright NGGT.LightKeeper. All Rights Reserved.

import { escHtml } from '../main/utils.js';

// Attachment UI.
// Create helpers for file picking, previews, and attachment state.
export function createAttachmentsUi(context) {
  const { dom, icons, state } = context;
  let updateSendButtons = function noop() {};

  // Integration hooks.
  // Register the send-button refresh callback owned by the message UI.
  function setUpdateSendButtons(fn) {
    updateSendButtons = typeof fn === 'function' ? fn : function noop() {};
  }

  // Return whether a URL contains inline base64 data.
  function isInlineDataUrl(value) {
    return String(value || '').startsWith('data:');
  }

  // Extract a base64 payload only from inline data URLs.
  function dataUrlToBase64(value) {
    const dataUrl = String(value || '');
    if (!isInlineDataUrl(dataUrl)) {
      return '';
    }
    return dataUrl.replace(/^data:[^;]+;base64,/, '');
  }

  // Convert a fetched Blob into a data URL.
  function readBlobAsDataUrl(blob) {
    return new Promise(function resolveBlob(resolve, reject) {
      const reader = new FileReader();
      reader.onload = function onLoad() {
        resolve(String(reader.result || ''));
      };
      reader.onerror = function onError() {
        reject(reader.error || new Error('Failed to read attachment'));
      };
      reader.readAsDataURL(blob);
    });
  }


  // Attachment controls.
  // Toggle attachment buttons and badges from model capabilities.
  function updateAttachmentControls() {
    const canAttach = state.visionState.supported || state.fileState.supported;

    dom.$attachBtn.toggle(canAttach);
    dom.$attachBtnConv.toggle(canAttach);
    dom.$visionBadge.toggle(state.visionState.supported);
    dom.$visionBadgeConv.toggle(state.visionState.supported);
  }

  // Clear all pending attachments from both composers.
  function clearPendingAttachments() {
    state.attachmentState.pending = [];
    dom.$imagePreviewStrip.empty().hide();
    dom.$imagePreviewStripConv.empty().hide();
    dom.$imageInput.val('');
    dom.$imageInputConv.val('');
    updateSendButtons();
  }


  // Attachment normalization.
  // Normalize one stored or runtime attachment into the shared UI shape.
  function normalizeAttachment(attachment) {
    if (!attachment) {
      return null;
    }

    if (typeof attachment === 'string') {
      const source = String(attachment || '');
      const isRemoteUrl = source.startsWith('/') || /^https?:\/\//i.test(source);
      const base64 = isRemoteUrl ? '' : dataUrlToBase64(source) || source;

      return {
        kind: 'image',
        name: '',
        mimeType: 'image/jpeg',
        size: 0,
        base64,
        dataUrl: source,
        contentUrl: isRemoteUrl ? source : ''
      };
    }

    const contentUrl = attachment.contentUrl || attachment.content_url || '';
    const dataUrl = attachment.dataUrl || attachment.data_url || contentUrl || '';
    const mimeType = attachment.mimeType || attachment.mime_type || 'application/octet-stream';
    const base64 = attachment.base64 || attachment.data || dataUrlToBase64(dataUrl);

    return {
      id: attachment.id || null,
      kind: attachment.kind || 'file',
      name: attachment.name || '',
      mimeType,
      size: attachment.size || attachment.size_bytes || 0,
      base64,
      dataUrl: dataUrl || (base64 ? `data:${mimeType};base64,${base64}` : ''),
      contentUrl,
      recordType: attachment.recordType || attachment.record_type || ''
    };
  }

  // Ensure a stored attachment has inline data before it is sent again.
  async function resolveAttachmentData(attachment) {
    const normalized = normalizeAttachment(attachment);
    if (!normalized) {
      return null;
    }

    if (normalized.base64) {
      return normalized;
    }

    const fetchUrl = normalized.contentUrl || (!isInlineDataUrl(normalized.dataUrl) ? normalized.dataUrl : '');
    if (!fetchUrl || typeof fetch === 'undefined') {
      return normalized;
    }

    const response = await fetch(fetchUrl);
    if (!response.ok) {
      throw new Error(`Failed to load attachment: ${response.status}`);
    }

    const blob = await response.blob();
    const dataUrl = await readBlobAsDataUrl(blob);
    const mimeType = blob.type || normalized.mimeType;

    return {
      ...normalized,
      mimeType,
      size: normalized.size || blob.size || 0,
      base64: dataUrlToBase64(dataUrl),
      dataUrl
    };
  }


  // Preview rendering.
  // Rebuild both preview strips from the current pending attachments.
  function rebuildPreviewStrips() {
    const $strips = dom.$imagePreviewStrip.add(dom.$imagePreviewStripConv);
    $strips.empty();

    if (state.attachmentState.pending.length === 0) {
      $strips.hide();
      updateSendButtons();
      return;
    }

    state.attachmentState.pending.forEach(function renderAttachment(attachment, index) {
      let html = '';

      if (attachment.kind === 'image') {
        html = `
          <div class="img-preview-thumb" data-idx="${index}">
            <img src="${attachment.dataUrl}" alt="Attached image">
            <button class="img-preview-remove" aria-label="Remove attachment">
              ${icons.REMOVE_ATTACHMENT_ICON}
            </button>
          </div>
        `;
      } else {
        html = `
          <div class="file-preview-chip" data-idx="${index}">
            <div class="file-preview-name">${escHtml(attachment.name || 'File')}</div>
            <div class="file-preview-meta">${escHtml(attachment.mimeType || 'application/octet-stream')}</div>
            <button class="img-preview-remove" aria-label="Remove attachment">
              ${icons.REMOVE_ATTACHMENT_ICON}
            </button>
          </div>
        `;
      }

      $strips.append(html);
    });

    $strips.show();
    updateSendButtons();
  }

  // Remove one pending attachment by index.
  function removePendingAttachment(index) {
    if (!Number.isInteger(index) || index < 0) {
      return;
    }

    state.attachmentState.pending.splice(index, 1);
    rebuildPreviewStrips();
  }


  // File input handling.
  // Read selected files and queue them for the next request.
  function handleFileInput(event) {
    const maxAttachments = 20;
    const files = Array.from(event.target.files || []);

    if (!files.length) {
      return;
    }

    files.forEach(function queueFile(file) {
      const isImage = file.type.startsWith('image/');

      if (isImage && !state.visionState.supported) {
        return;
      }

      if (!isImage && !state.fileState.supported) {
        return;
      }

      if (state.attachmentState.pending.length >= maxAttachments) {
        console.warn(`Max ${maxAttachments} attachments allowed`);
        return;
      }

      const reader = new FileReader();

      reader.onload = function onLoad(loadEvent) {
        if (state.attachmentState.pending.length >= maxAttachments) {
          return;
        }

        const dataUrl = loadEvent.target.result;
        const base64 = String(dataUrl || '').split(',')[1] || '';

        state.attachmentState.pending.push({
          kind: isImage ? 'image' : 'file',
          name: file.name || '',
          mimeType: file.type || 'application/octet-stream',
          size: file.size || 0,
          base64,
          dataUrl
        });

        rebuildPreviewStrips();
      };

      reader.readAsDataURL(file);
    });

    $(event.target).val('');
  }

  return {
    clearPendingAttachments,
    handleFileInput,
    normalizeAttachment,
    rebuildPreviewStrips,
    removePendingAttachment,
    resolveAttachmentData,
    setUpdateSendButtons,
    updateAttachmentControls
  };
}
