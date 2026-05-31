// Copyright NGGT.LightKeeper. All Rights Reserved.

import { getCsrfToken } from '../main/api.js';
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
    dom.$attachBtn.show();
    dom.$attachBtnConv.show();
    if (dom.$modelVisionIndicator && dom.$modelVisionIndicator.length) {
      dom.$modelVisionIndicator.toggleClass('is-visible', state.visionState.supported);
    }
    $(document).trigger('aslm:modelCapabilitiesChanged');
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

    const fileId = String(attachment.fileId || attachment.file_id || '').trim();
    let contentUrl = String(attachment.contentUrl || attachment.content_url || '').trim();

    // If the server didn't return a content_url but we have a file_id, derive it
    // from the known upload serving endpoint so media players get a valid src.
    if (!contentUrl && fileId) {
      contentUrl = `/api/uploads/${encodeURIComponent(fileId)}/content/`;
    }

    const dataUrl = attachment.dataUrl || attachment.data_url || contentUrl || '';
    const previewDataUrl = attachment.previewDataUrl || attachment.preview_data_url || '';
    const mimeType = attachment.mimeType || attachment.mime_type || 'application/octet-stream';
    const base64 = attachment.base64 || attachment.data || dataUrlToBase64(dataUrl);

    return {
      id: attachment.id || null,
      kind: attachment.kind || 'file',
      fileId,
      name: attachment.name || '',
      mimeType,
      size: attachment.size || attachment.size_bytes || 0,
      base64,
      dataUrl: dataUrl || (base64 ? `data:${mimeType};base64,${base64}` : ''),
      previewDataUrl,
      contentUrl,
      recordType: attachment.recordType || attachment.record_type || '',
      status: attachment.status || 'ready',
      displayKind: attachment.displayKind || attachment.display_kind || '',
      typeLabel: attachment.typeLabel || attachment.type_label || ''
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
  // Build the subtitle shown under one pending attachment chip.
  function previewLabel(attachment) {
    return attachment.typeLabel || attachment.mimeType || 'File';
  }

  // Build the badge text shown on non-image attachment chips.
  function uploadIconLabel(attachment) {
    const kind = String(attachment.displayKind || attachment.kind || '').toLowerCase();
    if (kind === 'image') {
      return 'IMG';
    }
    if (kind === 'audio') {
      return 'AUDIO';
    }
    if (kind === 'video') {
      return 'VIDEO';
    }
    if (kind === 'archive') {
      return 'ZIP';
    }
    if (kind === 'code') {
      return '</>';
    }
    if (kind === 'table') {
      return 'CSV';
    }
    if (kind === 'document') {
      return 'DOC';
    }
    return 'FILE';
  }

  // Report whether one File object should be treated as an image.
  function isImageFile(file) {
    const name = String(file && file.name ? file.name : '').toLowerCase();
    const mimeType = String(file && file.type ? file.type : '').toLowerCase();
    return mimeType.startsWith('image/')
      || /\.(png|jpe?g|webp|gif|bmp|avif)$/i.test(name);
  }

  // Infer display kind and label for one selected file.
  function displayKindForFile(file) {
    const name = String(file && file.name ? file.name : '').toLowerCase();
    const mimeType = String(file && file.type ? file.type : '').toLowerCase();
    if (isImageFile(file)) {
      return ['image', 'Image'];
    }
    if (mimeType.startsWith('audio/') || /\.(mp3|wav|ogg|oga|m4a|aac|flac|opus)$/i.test(name)) {
      return ['audio', 'Audio'];
    }
    if (mimeType.startsWith('video/') || /\.(mp4|webm|mov|m4v|ogv|avi|mkv)$/i.test(name)) {
      return ['video', 'Video'];
    }
    if (name.endsWith('.zip') || mimeType === 'application/zip' || mimeType === 'application/x-zip-compressed') {
      return ['archive', 'ZIP archive'];
    }
    if (name.endsWith('.rar') || name.endsWith('.7z')) {
      return ['archive', 'Archive'];
    }
    if (name.endsWith('.pdf') || mimeType === 'application/pdf') {
      return ['document', 'PDF document'];
    }
    if (name.endsWith('.docx')) {
      return ['document', 'Word document'];
    }
    if (name.endsWith('.xlsx')) {
      return ['table', 'Excel spreadsheet'];
    }
    if (name.endsWith('.pptx')) {
      return ['presentation', 'PowerPoint presentation'];
    }
    if (/\.(py|js|ts|css|html|sql|sh|ps1)$/i.test(name)) {
      return ['code', 'Code file'];
    }
    if (/\.(txt|md|log|json|yaml|yml|xml|csv)$/i.test(name) || mimeType.startsWith('text/')) {
      return name.endsWith('.csv') ? ['table', 'CSV table'] : ['text', 'Text file'];
    }
    return ['file', 'File'];
  }

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

      const imagePreviewSrc = attachment.dataUrl || attachment.previewDataUrl || '';
      if ((attachment.kind === 'image' || attachment.displayKind === 'image') && imagePreviewSrc) {
        html = `
          <div class="img-preview-thumb" data-idx="${index}">
            <img src="${imagePreviewSrc}" alt="Attached image">
            <button class="img-preview-remove" aria-label="Remove attachment">
              ${icons.REMOVE_ATTACHMENT_ICON}
            </button>
          </div>
        `;
      } else {
        const isUploading = attachment.status === 'uploading';
        const isError = attachment.status === 'error';
        html = `
          <div class="file-preview-chip${isUploading ? ' is-uploading' : ''}${isError ? ' is-error' : ''}" data-idx="${index}">
            <div class="file-preview-icon" aria-hidden="true">${escHtml(uploadIconLabel(attachment))}</div>
            <div class="file-preview-name">${escHtml(attachment.name || 'File')}</div>
            <div class="file-preview-meta">${escHtml(isUploading ? 'Uploading...' : (isError ? 'Upload failed' : previewLabel(attachment)))}</div>
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
  // Read one File object as a data URL for local previews.
  function readFileAsDataUrl(file) {
    return new Promise(function resolveFile(resolve, reject) {
      const reader = new FileReader();
      reader.onload = function onLoad(loadEvent) {
        resolve(String(loadEvent.target.result || ''));
      };
      reader.onerror = function onError() {
        reject(reader.error || new Error('Failed to read file'));
      };
      reader.readAsDataURL(file);
    });
  }

  // Upload one file to the server and merge the response into pending state.
  async function uploadOneFile(file, pendingAttachment) {
    const formData = new FormData();
    formData.append('files', file, file.name || 'file');
    formData.append('scope', state.currentChatId || 'pending');
    formData.append('supports_vision', state.visionState.supported ? '1' : '0');
    Array.from(state.selectedToolServerIds || []).forEach(function appendToolServerId(serverId) {
      const normalized = String(serverId || '').trim();
      if (normalized) {
        formData.append('tool_server_ids', normalized);
      }
    });

    const response = await fetch('/api/uploads/', {
      method: 'POST',
      headers: {
        'X-CSRFToken': getCsrfToken()
      },
      body: formData
    });

    if (!response.ok) {
      throw new Error(`Upload failed: ${response.status}`);
    }

    const payload = await response.json();
    const uploadedFile = Array.isArray(payload.files) ? payload.files[0] : null;
    if (!uploadedFile || uploadedFile.status === 'error') {
      throw new Error((uploadedFile && uploadedFile.error) || 'Upload failed');
    }

    Object.assign(pendingAttachment, {
      fileId: uploadedFile.file_id || '',
      name: uploadedFile.name || pendingAttachment.name,
      mimeType: uploadedFile.mime_type || pendingAttachment.mimeType,
      size: uploadedFile.size_bytes || pendingAttachment.size,
      status: uploadedFile.status || 'ready',
      displayKind: uploadedFile.display_kind || pendingAttachment.displayKind,
      typeLabel: uploadedFile.type_label || pendingAttachment.typeLabel,
      contentUrl: uploadedFile.content_url || pendingAttachment.contentUrl || ''
    });
  }

  // Upload selected files and queue them for the next request.
  async function queueFiles(files) {
    const maxAttachments = 20;
    const selectedFiles = Array.from(files || []);

    if (!selectedFiles.length) {
      return;
    }

    selectedFiles.forEach(function queueFile(file) {
      const isImage = isImageFile(file);
      const [displayKind, typeLabel] = displayKindForFile(file);

      if (state.attachmentState.pending.length >= maxAttachments) {
        console.warn(`Max ${maxAttachments} attachments allowed`);
        return;
      }

      const canPreviewAsMedia = displayKind === 'audio' || displayKind === 'video';
      const objectPreviewUrl = canPreviewAsMedia && typeof URL !== 'undefined' && URL.createObjectURL
        ? URL.createObjectURL(file)
        : '';
      const pendingAttachment = {
        kind: isImage && state.visionState.supported ? 'image' : 'file',
        fileId: '',
        name: file.name || '',
        mimeType: file.type || 'application/octet-stream',
        size: file.size || 0,
        base64: '',
        dataUrl: '',
        previewDataUrl: objectPreviewUrl,
        status: 'uploading',
        displayKind,
        typeLabel
      };

      state.attachmentState.pending.push(pendingAttachment);
      rebuildPreviewStrips();

      const imagePreviewPromise = isImage
        ? readFileAsDataUrl(file).then(function applyDataUrl(dataUrl) {
          if (state.visionState.supported) {
            pendingAttachment.dataUrl = dataUrl;
            pendingAttachment.base64 = String(dataUrl || '').split(',')[1] || '';
          } else {
            pendingAttachment.previewDataUrl = dataUrl;
          }
          rebuildPreviewStrips();
        }).catch(function ignorePreviewError() {})
        : Promise.resolve();

      Promise.all([uploadOneFile(file, pendingAttachment), imagePreviewPromise])
        .then(function onUploaded() {
          if (pendingAttachment.status !== 'error') {
            pendingAttachment.status = 'ready';
          }
          rebuildPreviewStrips();
        })
        .catch(function onUploadError(error) {
          console.error(error);
          pendingAttachment.status = 'error';
          pendingAttachment.typeLabel = 'Upload failed';
          rebuildPreviewStrips();
        });
    });
  }


  // Clipboard and drag-drop helpers.
  // Build a filename for one pasted image blob.
  function clipboardImageName(mimeType, index) {
    const normalizedMime = String(mimeType || '').toLowerCase();
    const extensionByMime = {
      'image/avif': 'avif',
      'image/bmp': 'bmp',
      'image/gif': 'gif',
      'image/jpeg': 'jpg',
      'image/png': 'png',
      'image/webp': 'webp'
    };
    const extension = extensionByMime[normalizedMime] || 'png';
    return `pasted-image-${Date.now()}-${index + 1}.${extension}`;
  }

  // Normalize one clipboard image File with a generated filename when needed.
  function normalizeClipboardImageFile(file, index) {
    if (!file || !isImageFile(file)) {
      return null;
    }

    if (file.name) {
      return file;
    }

    try {
      return new File([file], clipboardImageName(file.type, index), {
        type: file.type || 'image/png',
        lastModified: Date.now()
      });
    } catch (_error) {
      return file;
    }
  }

  // Collect unique image files from a clipboard DataTransfer.
  function collectClipboardImageFiles(clipboardData) {
    const files = [];
    const seen = new Set();

    function addFile(file) {
      const normalizedFile = normalizeClipboardImageFile(file, files.length);
      if (!normalizedFile) {
        return;
      }
      const key = [
        normalizedFile.name || '',
        normalizedFile.type || '',
        normalizedFile.size || 0,
        normalizedFile.lastModified || 0
      ].join('|');
      if (seen.has(key)) {
        return;
      }
      seen.add(key);
      files.push(normalizedFile);
    }

    Array.from((clipboardData && clipboardData.items) || []).forEach(function collectItem(item) {
      if (!item || String(item.kind || '').toLowerCase() !== 'file') {
        return;
      }
      if (!String(item.type || '').toLowerCase().startsWith('image/')) {
        return;
      }
      addFile(item.getAsFile && item.getAsFile());
    });

    if (!files.length) {
      Array.from((clipboardData && clipboardData.files) || []).forEach(addFile);
    }

    return files;
  }

  // Queue pasted clipboard images when the clipboard carries files.
  function handleClipboardPaste(clipboardData) {
    const files = collectClipboardImageFiles(clipboardData);
    if (!files.length) {
      return false;
    }

    queueFiles(files);
    return true;
  }

  // Read selected files and queue them for the next request.
  function handleFileInput(event) {
    queueFiles(event.target.files || []);

    $(event.target).val('');
  }

  // Queue files dropped onto the chat shell overlay.
  function handleDroppedFiles(files) {
    queueFiles(files || []);
  }

  return {
    clearPendingAttachments,
    handleDroppedFiles,
    handleFileInput,
    handleClipboardPaste,
    normalizeAttachment,
    rebuildPreviewStrips,
    removePendingAttachment,
    resolveAttachmentData,
    setUpdateSendButtons,
    updateAttachmentControls
  };
}
