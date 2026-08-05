// Copyright NEXTGGTECH. Elastic License 2.0.

import { t } from '../main/i18n.js';

// Shared in-app dialogs.
// Themed, promise-based replacements for window.confirm/prompt/alert. Each dialog
// mounts a fixed-position backdrop directly on <body> so it works anywhere in the app
// (independent of any feature-specific overlay).

// Show a confirm/cancel dialog.
// Resolves true when confirmed, false on cancel, Escape, or backdrop click.
export function confirmDialog(options) {
  return new Promise(function confirmDialogPromise(resolve) {
    const dialogOptions = options || {};
    const $backdrop = $('<div class="aslm-dialog-backdrop" role="dialog" aria-modal="true">');
    const $dialog = $('<div class="aslm-dialog">');
    const $title = $('<div class="aslm-dialog-title">').text(dialogOptions.title || t('dialog.confirm', null, 'Confirm'));
    const $message = $('<div class="aslm-dialog-message">').text(dialogOptions.message || '');
    const $actions = $('<div class="aslm-dialog-actions">');
    const cancelText = dialogOptions.cancelText === undefined ? t('dialog.cancel', null, 'Cancel') : String(dialogOptions.cancelText || '');
    const $confirm = $('<button type="button" class="preset-action-btn preset-action-btn-primary">')
      .toggleClass('preset-action-btn-danger', Boolean(dialogOptions.danger))
      .text(dialogOptions.confirmText || t('dialog.ok', null, 'OK'));

    let closed = false;
    function close(value) {
      if (closed) {
        return;
      }
      closed = true;
      $(document).off('keydown', onKeyDown);
      $backdrop.remove();
      resolve(value);
    }

    function onKeyDown(ev) {
      if (ev.key === 'Escape') {
        ev.preventDefault();
        close(false);
      } else if (ev.key === 'Enter') {
        ev.preventDefault();
        close(true);
      }
    }

    if (cancelText) {
      const $cancel = $('<button type="button" class="preset-action-btn">').text(cancelText);
      $cancel.on('click', function onCancel() {
        close(false);
      });
      $actions.append($cancel);
    }

    $confirm.on('click', function onConfirm() {
      close(true);
    });
    $backdrop.on('click', function onBackdropClick(ev) {
      if (ev.target === $backdrop[0]) {
        close(false);
      }
    });
    $(document).on('keydown', onKeyDown);

    $actions.append($confirm);
    $dialog.append($title).append($message).append($actions);
    $backdrop.append($dialog);
    $('body').append($backdrop);
    requestAnimationFrame(function focusConfirm() {
      $confirm.trigger('focus');
    });
  });
}

// Show a single text-input dialog.
// Resolves the trimmed string on submit, or null on cancel/Escape/backdrop click.
// When required is true (default), an empty submit is blocked with a validation error;
// when required is false, an empty submit resolves to ''.
export function textDialog(options) {
  return new Promise(function textDialogPromise(resolve) {
    const dialogOptions = options || {};
    const required = dialogOptions.required === undefined ? true : Boolean(dialogOptions.required);
    const $backdrop = $('<div class="aslm-dialog-backdrop" role="dialog" aria-modal="true">');
    const $dialog = $('<div class="aslm-dialog">');
    const $title = $('<div class="aslm-dialog-title">').text(dialogOptions.title || t('dialog.input', null, 'Input'));
    const $label = $('<label class="aslm-dialog-label">').text(dialogOptions.label || '');
    const $input = $('<input class="aslm-dialog-input" type="text">')
      .val(dialogOptions.value || '')
      .attr('placeholder', dialogOptions.placeholder || '');
    const $error = $('<div class="aslm-dialog-error" role="alert">').hide();
    const $actions = $('<div class="aslm-dialog-actions">');
    const $cancel = $('<button type="button" class="preset-action-btn">').text(dialogOptions.cancelText || t('dialog.cancel', null, 'Cancel'));
    const $confirm = $('<button type="button" class="preset-action-btn preset-action-btn-primary">').text(dialogOptions.confirmText || t('dialog.ok', null, 'OK'));

    let closed = false;
    function close(value) {
      if (closed) {
        return;
      }
      closed = true;
      $(document).off('keydown', onKeyDown);
      $backdrop.remove();
      resolve(value);
    }

    function submit() {
      const value = String($input.val() || '').trim();
      if (!value && required) {
        $error.text(t('dialog.valueRequired', null, 'Value is required.')).show();
        return;
      }
      close(value);
    }

    function onKeyDown(ev) {
      if (ev.key === 'Escape') {
        ev.preventDefault();
        close(null);
      }
    }

    $cancel.on('click', function onCancel() {
      close(null);
    });
    $confirm.on('click', submit);
    $input.on('keydown', function onInputKeyDown(ev) {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        submit();
      }
    });
    $backdrop.on('click', function onBackdropClick(ev) {
      if (ev.target === $backdrop[0]) {
        close(null);
      }
    });
    $(document).on('keydown', onKeyDown);

    $actions.append($cancel).append($confirm);
    $dialog.append($title).append($label.append($input)).append($error).append($actions);
    $backdrop.append($dialog);
    $('body').append($backdrop);
    requestAnimationFrame(function focusInput() {
      $input.trigger('focus');
      const input = $input.get(0);
      if (input && input.select) {
        input.select();
      }
    });
  });
}

// Show a simple acknowledgement dialog with a single OK button.
export function messageDialog(title, message) {
  return confirmDialog({
    title,
    message,
    confirmText: t('dialog.ok', null, 'OK'),
    cancelText: '',
    danger: false
  });
}

// Show a multi-line text editor dialog (used for editable pasted text artifacts).
// Resolves with the (trimmed or raw) text on confirm, or null on cancel.
export function largeTextDialog(options) {
  return new Promise(function largeTextDialogPromise(resolve) {
    const dialogOptions = options || {};
    const $backdrop = $('<div class="aslm-dialog-backdrop aslm-dialog-backdrop--editor" role="dialog" aria-modal="true">');
    const $dialog = $('<div class="aslm-dialog aslm-dialog--editor">');

    const titleText = dialogOptions.title || t('dialog.editPastedTitle', null, 'Edit pasted content');
    const $title = $('<div class="aslm-dialog-title">').text(titleText);

    const labelText = dialogOptions.label || '';
    const $label = labelText ? $('<div class="aslm-dialog-label">').text(labelText) : null;

    const initialValue = String(dialogOptions.value || dialogOptions.text || '');
    const $textarea = $('<textarea class="aslm-dialog-textarea" spellcheck="false"></textarea>')
      .val(initialValue)
      .attr('placeholder', dialogOptions.placeholder || t('dialog.editPastedPlaceholder', null, 'Edit the pasted text. Use Ctrl/Cmd+Enter to save.'));

    const $error = $('<div class="aslm-dialog-error" role="alert">').hide();
    const $actions = $('<div class="aslm-dialog-actions">');

    const cancelText = dialogOptions.cancelText === undefined ? t('dialog.cancel', null, 'Cancel') : String(dialogOptions.cancelText || '');
    const confirmText = dialogOptions.confirmText || t('dialog.save', null, 'Save changes');

    const $cancel = $('<button type="button" class="preset-action-btn">').text(cancelText);
    const $confirm = $('<button type="button" class="preset-action-btn preset-action-btn-primary">').text(confirmText);

    let closed = false;

    function close(value) {
      if (closed) {
        return;
      }
      closed = true;
      $(document).off('keydown', onKeyDown);
      $backdrop.remove();
      resolve(value);
    }

    function submit() {
      const raw = String($textarea.val() || '');
      // Allow empty on explicit save (user may want to clear), but respect required if set.
      const required = dialogOptions.required !== false; // default true like textDialog
      if (required && !raw.trim()) {
        $error.text(t('dialog.valueRequired', null, 'Value is required.')).show();
        return;
      }
      // Return the raw text (caller decides whether to trim). Preserve user's newlines.
      close(raw);
    }

    function onKeyDown(ev) {
      if (ev.key === 'Escape') {
        ev.preventDefault();
        close(null);
      } else if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) {
        // Ctrl/Cmd+Enter to save (common for text areas)
        ev.preventDefault();
        submit();
      }
    }

    $cancel.on('click', function onCancel() {
      close(null);
    });
    $confirm.on('click', submit);

    $textarea.on('keydown', function onTextareaKeyDown(ev) {
      if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) {
        ev.preventDefault();
        submit();
      }
    });

    $backdrop.on('click', function onBackdropClick(ev) {
      if (ev.target === $backdrop[0]) {
        close(null);
      }
    });

    $(document).on('keydown', onKeyDown);

    $actions.append($cancel).append($confirm);

    $dialog.append($title);
    if ($label) {
      $dialog.append($label);
    }
    $dialog.append($textarea).append($error).append($actions);
    $backdrop.append($dialog);
    $('body').append($backdrop);

    requestAnimationFrame(function focusTextarea() {
      $textarea.trigger('focus');
      // Move caret to end
      try {
        const ta = $textarea.get(0);
        if (ta) {
          const len = ta.value.length;
          ta.setSelectionRange(len, len);
        }
      } catch (_) {}
    });
  });
}
