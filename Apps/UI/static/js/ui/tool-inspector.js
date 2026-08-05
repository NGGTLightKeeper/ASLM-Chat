// Copyright NEXTGGTECH. Elastic License 2.0.

// Tool inspector UI.
// Create the modal used to inspect tool inputs and outputs.
export function createToolInspector(context) {
  const { dom } = context;
  let openResearchKey = '';
  let openResearchView = 'activity';
  let previouslyFocused = null;
  let renderedResearchBodyHtml = null;
  let renderedResearchFooterHtml = null;

  // Capture UI-only state that is not represented by the research snapshot.
  // Polling may change the timeline markup, but it must not collapse controls
  // the user opened or jump the inspector back to the top.
  function captureResearchBodyState($body) {
    const body = $body.get(0);
    if (!body) {
      return null;
    }
    const details = [];
    $body.find('details').each(function captureDetails(index) {
      details.push({ index, open: this.open === true });
    });
    const expandedSearches = [];
    $body.find('.msg-search-card').each(function captureSearch(index) {
      if (this.classList.contains('is-expanded')) {
        const key = String(this.getAttribute('data-search-key') || '').trim();
        const toolIndex = String(this.getAttribute('data-tool-segment-index') || '').trim();
        expandedSearches.push({ key, toolIndex, index });
      }
    });
    const distanceFromBottom = body.scrollHeight - body.clientHeight - body.scrollTop;
    return {
      details,
      expandedSearches,
      scrollTop: body.scrollTop,
      wasNearBottom: distanceFromBottom <= 24
    };
  }

  // Restore disclosure/search expansion and scrolling after a meaningful
  // timeline update. CSS uses the is-expanded class for the source-chip tray.
  function restoreResearchBodyState($body, state) {
    const body = $body.get(0);
    if (!body || !state) {
      return;
    }
    const detailNodes = $body.find('details').get();
    state.details.forEach(function restoreDetails(item) {
      if (detailNodes[item.index]) {
        detailNodes[item.index].open = item.open;
      }
    });
    const searchNodes = $body.find('.msg-search-card').get();
    state.expandedSearches.forEach(function restoreSearch(item) {
      let search = null;
      if (item.key) {
        search = searchNodes.find(function matchSearchKey(node) {
          return String(node.getAttribute('data-search-key') || '').trim() === item.key;
        });
      }
      if (!search && item.toolIndex) {
        search = searchNodes.find(function matchToolIndex(node) {
          return String(node.getAttribute('data-tool-segment-index') || '').trim() === item.toolIndex;
        });
      }
      search = search || searchNodes[item.index];
      if (search) {
        search.classList.add('is-expanded');
        search.querySelectorAll('.msg-search-chip--more').forEach(function expandMoreButton(button) {
          button.setAttribute('aria-expanded', 'true');
        });
      }
    });
    body.scrollTop = state.wasNearBottom
      ? Math.max(0, body.scrollHeight - body.clientHeight)
      : state.scrollTop;
  }

  // Avoid replacing live DOM for identical polling snapshots. Replacing it
  // restarts animations and destroys browser-managed interaction state.
  function updateResearchHtml($target, html, kind) {
    const nextHtml = String(html || '');
    const previousHtml = kind === 'body' ? renderedResearchBodyHtml : renderedResearchFooterHtml;
    if (previousHtml === nextHtml) {
      return;
    }
    const bodyState = kind === 'body' ? captureResearchBodyState($target) : null;
    $target.html(nextHtml);
    if (kind === 'body') {
      renderedResearchBodyHtml = nextHtml;
      restoreResearchBodyState($target, bodyState);
    } else {
      renderedResearchFooterHtml = nextHtml;
    }
  }

  // Toggle the modal into generic-tool or Deep Research mode.
  function setMode(mode) {
    const researchMode = mode === 'research';
    dom.$toolInspectorModal
      .toggleClass('is-deep-research', researchMode)
      .toggleClass('is-deep-research-report', researchMode && openResearchView === 'report')
      .attr('data-inspector-mode', researchMode ? 'research' : 'tool');
    if (!researchMode) {
      dom.$toolInspectorModal.removeAttr('data-research-view');
    }
    dom.$toolInspectorModal.find('.tool-inspector-generic-body').toggle(!researchMode);
    dom.$toolInspectorModal.find('.tool-inspector-research').toggle(researchMode);
    dom.$toolInspectorModal.find('.tool-inspector-research-tools').toggle(researchMode);
  }

  function setResearchView(viewMode) {
    openResearchView = viewMode === 'report' ? 'report' : 'activity';
    dom.$toolInspectorModal
      .toggleClass('is-deep-research-report', openResearchView === 'report')
      .attr('data-research-view', openResearchView);
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
      .removeClass('open is-deep-research is-deep-research-report')
      .attr('aria-hidden', 'true')
      .removeAttr('data-inspector-mode data-research-view');
    $('body').removeClass('is-tool-inspector-open');
    openResearchKey = '';
    openResearchView = 'activity';
    renderedResearchBodyHtml = null;
    renderedResearchFooterHtml = null;
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
    setResearchView(view.viewMode);
    setResearchEditing(false);
    dom.$toolInspectorModal.find('.tool-inspector-title').text(view.title || 'Deep Research');
    dom.$toolInspectorModal.find('.tool-inspector-server').text(view.server || '');
    dom.$toolInspectorModal.find('.tool-inspector-research-tools').html(view.toolbarHtml || '');
    renderedResearchBodyHtml = String(view.bodyHtml || '');
    renderedResearchFooterHtml = String(view.footerHtml || '');
    dom.$toolInspectorModal.find('.tool-inspector-research-body').html(renderedResearchBodyHtml);
    dom.$toolInspectorModal.find('.tool-inspector-research-footer').html(renderedResearchFooterHtml);
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
    if (view.viewMode !== undefined) {
      setResearchView(view.viewMode);
    }
    if (view.toolbarHtml !== undefined) {
      dom.$toolInspectorModal.find('.tool-inspector-research-tools').html(view.toolbarHtml || '');
    }
    if (view.bodyHtml !== undefined) {
      updateResearchHtml(
        dom.$toolInspectorModal.find('.tool-inspector-research-body'),
        view.bodyHtml,
        'body'
      );
    }
    if (view.footerHtml !== undefined) {
      updateResearchHtml(
        dom.$toolInspectorModal.find('.tool-inspector-research-footer'),
        view.footerHtml,
        'footer'
      );
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

  function getOpenResearchView() {
    return openResearchView;
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
    getOpenResearchView,
    getResearchEditorValue,
    isResearchEditing,
    open,
    openResearch,
    setResearchEditing,
    showResearchError,
    updateResearch
  };
}
