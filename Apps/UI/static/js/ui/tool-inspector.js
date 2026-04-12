// Copyright NGGT.LightKeeper. All Rights Reserved.

// Tool inspector UI.
// Create the modal used to inspect tool inputs and outputs.
export function createToolInspector(context) {
  const { dom } = context;

  // Close the inspector modal.
  function close() {
    dom.$toolInspectorModal.removeClass('open');
  }

  // Open the inspector for one tool timeline segment.
  function open(segment) {
    const seg = segment || {};

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

    dom.$toolInspectorModal.addClass('open');
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
    open
  };
}
