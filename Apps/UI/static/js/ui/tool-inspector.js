// Copyright NGGT.LightKeeper. All Rights Reserved.

// Tool inspector UI.
// Create the modal used to inspect tool inputs and outputs.
export function createToolInspector(context) {
  const { dom } = context;
  let openResearchKey = '';
  let previouslyFocused = null;

  // Toggle the modal into generic-tool or Deep Research mode.
  function setMode(mode) {
    const researchMode = mode === 'research';
    dom.$toolInspectorModal
      .toggleClass('is-deep-research', researchMode)
      .attr('data-inspector-mode', researchMode ? 'research' : 'tool');
    dom.$toolInspectorModal.find('.tool-inspector-generic-body').toggle(!researchMode);
    dom.$toolInspectorModal.find('.tool-inspector-research').toggle(researchMode);
  }

  // Present the overlay and move keyboard focus into the dialog.
  function show() {
    if (!dom.$toolInspectorModal.hasClass('open')) {
      previouslyFocused = document.activeElement;
    }
    dom.$toolInspectorModal
      .addClass('open')
      .attr('aria-hidden', 'false');
    $('body').addClass('is-tool-inspector-open');
    window.requestAnimationFrame(function focusInspector() {
      dom.$toolInspectorModal.find('.tool-inspector-panel').trigger('focus');
    });
  }

  // Close the inspector modal.
  function close() {
    dom.$toolInspectorModal
      .removeClass('open is-deep-research')
      .attr('aria-hidden', 'true')
      .removeAttr('data-inspector-mode');
    $('body').removeClass('is-tool-inspector-open');
    openResearchKey = '';
    setResearchEditing(false);
    if (previouslyFocused && document.contains(previouslyFocused) && typeof previouslyFocused.focus === 'function') {
      previouslyFocused.focus();
    }
    previouslyFocused = null;
  }

  // Open the inspector for one tool timeline segment.
  function open(segment) {
    const seg = segment || {};
    openResearchKey = '';
    setMode('tool');

    dom.$toolInspectorModal.find('.tool-inspector-title').text(seg.toolName || seg.alias || seg.toolId || 'Tool');
    dom.$toolInspectorModal.find('.tool-inspector-server').text(seg.serverName || seg.serverId || '');

    const argsText = Object.keys(seg.arguments || {}).length > 0
      ? JSON.stringify(seg.arguments, null, 2)
      : '(no arguments)';
    dom.$toolInspectorModal.find('.tool-inspector-in').text(argsText);

    const resultText = seg.result !== null && seg.result !== undefined
      ? String(seg.result)
      : '(pending)';
    dom.$toolInspectorModal.find('.tool-inspector-out').text(resultText);

    show();
  }

  // Open the rich Deep Research inspector.
  function openResearch(payload) {
    const view = payload || {};
    openResearchKey = String(view.key || '').trim();
    setMode('research');
    setResearchEditing(false);
    dom.$toolInspectorModal.find('.tool-inspector-title').text(view.title || 'Deep Research');
    dom.$toolInspectorModal.find('.tool-inspector-server').text(view.server || '');
    dom.$toolInspectorModal.find('.tool-inspector-research-body').html(view.bodyHtml || '');
    dom.$toolInspectorModal.find('.tool-inspector-research-footer').html(view.footerHtml || '');
    dom.$toolInspectorModal.find('.tool-inspector-research-error').empty().hide();
    show();
  }

  // Refresh an already-open research inspector without stealing focus.
  function updateResearch(payload) {
    const view = payload || {};
    if (!openResearchKey || String(view.key || '') !== openResearchKey || !dom.$toolInspectorModal.hasClass('open')) {
      return;
    }
    if (view.title !== undefined) {
      dom.$toolInspectorModal.find('.tool-inspector-title').text(view.title || 'Deep Research');
    }
    if (view.server !== undefined) {
      dom.$toolInspectorModal.find('.tool-inspector-server').text(view.server || '');
    }
    if (view.bodyHtml !== undefined) {
      dom.$toolInspectorModal.find('.tool-inspector-research-body').html(view.bodyHtml || '');
    }
    if (view.footerHtml !== undefined) {
      dom.$toolInspectorModal.find('.tool-inspector-research-footer').html(view.footerHtml || '');
    }
  }

  // Switch between the public activity view and the plan editor.
  function setResearchEditing(editing, value) {
    const isEditing = editing === true;
    const $research = dom.$toolInspectorModal.find('.tool-inspector-research');
    $research.toggleClass('is-editing', isEditing);
    $research.find('.tool-inspector-research-main').toggle(!isEditing);
    $research.find('.deep-research-plan-editor').toggle(isEditing);
    if (isEditing && value !== undefined) {
      const $textarea = $research.find('.deep-research-plan-textarea');
      $textarea.val(String(value || ''));
      $research.find('.tool-inspector-research-error').empty().hide();
      window.requestAnimationFrame(function focusResearchPlan() {
        $textarea.trigger('focus');
        const textarea = $textarea.get(0);
        if (textarea && textarea.setSelectionRange) {
          textarea.setSelectionRange(textarea.value.length, textarea.value.length);
        }
      });
    }
  }

  // Display a control or validation error inside the research inspector.
  function showResearchError(message) {
    const text = String(message || '').trim();
    dom.$toolInspectorModal.find('.tool-inspector-research-error')
      .text(text)
      .toggle(!!text);
  }

  function getOpenResearchKey() {
    return openResearchKey;
  }

  function isResearchEditing() {
    return dom.$toolInspectorModal.find('.tool-inspector-research').hasClass('is-editing');
  }

  function getResearchEditorValue() {
    return String(dom.$toolInspectorModal.find('.deep-research-plan-textarea').val() || '');
  }


  // Global modal events.
  // Bind close actions shared by the whole page.
  function bindGlobalEvents() {
    $('#toolInspectorClose').on('click', close);

    dom.$toolInspectorModal.on('click', function onBackdropClick(event) {
      if ($(event.target).is(dom.$toolInspectorModal)) {
        close();
      }
    });

    $(document).on('keydown', function onEscape(event) {
      if (event.key === 'Escape') {
        close();
      }
    });
  }

  return {
    bindGlobalEvents,
    close,
    getOpenResearchKey,
    getResearchEditorValue,
    isResearchEditing,
    open,
    openResearch,
    setResearchEditing,
    showResearchError,
    updateResearch
  };
}
