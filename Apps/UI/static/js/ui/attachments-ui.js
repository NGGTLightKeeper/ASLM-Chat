// Copyright NGGT.LightKeeper. All Rights Reserved.

import { escHtml } from '../main/utils.js';

export function createAttachmentsUi(context) {
  const { dom, icons, state } = context;
  let updateSendButtons = function noop() {};

  function setUpdateSendButtons(fn) {
    updateSendButtons = typeof fn === 'function' ? fn : function noop() {};
  }

  function updateAttachmentControls() {
    const canAttach = state.visionState.supported || state.fileState.supported;
    dom.$attachBtn.toggle(canAttach);
    dom.$attachBtnConv.toggle(canAttach);
    dom.$visionBadge.toggle(state.visionState.supported);
    dom.$visionBadgeConv.toggle(state.visionState.supported);
  }

  function clearPendingAttachments() {
    state.attachmentState.pending = [];
    dom.$imagePreviewStrip.empty().hide();
    dom.$imagePreviewStripConv.empty().hide();
    dom.$imageInput.val('');
    dom.$imageInputConv.val('');
    updateSendButtons();
  }

  function normalizeAttachment(attachment) {
    if (!attachment) {
      return null;
    }

    if (typeof attachment === 'string') {
      return {
        kind: 'image',
        name: '',
        mimeType: 'image/jpeg',
        size: 0,
        base64: attachment.replace(/^data:[^;]+;base64,/, ''),
        dataUrl: attachment
      };
    }

    const dataUrl = attachment.dataUrl || attachment.data_url || '';
    const mimeType = attachment.mimeType || attachment.mime_type || 'application/octet-stream';
    const base64 = attachment.base64 || attachment.data || (dataUrl ? dataUrl.replace(/^data:[^;]+;base64,/, '') : '');
    return {
      kind: attachment.kind || 'file',
      name: attachment.name || '',
      mimeType,
      size: attachment.size || attachment.size_bytes || 0,
      base64,
      dataUrl: dataUrl || (base64 ? `data:${mimeType};base64,${base64}` : '')
    };
  }

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

  function removePendingAttachment(index) {
    if (!Number.isInteger(index) || index < 0) {
      return;
    }

    state.attachmentState.pending.splice(index, 1);
    rebuildPreviewStrips();
  }

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
    setUpdateSendButtons,
    updateAttachmentControls
  };
}
