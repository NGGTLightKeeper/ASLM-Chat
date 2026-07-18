// Copyright NGGT.LightKeeper. All Rights Reserved.

import {
  LLM_PARAMETER_OPTION_SETS,
  OLLAMA_UNSUPPORTED_RUNTIME_PARAMS,
  PARAMETER_DEFINITIONS
} from '../main/constants.js';
import { getEngineAdapter, normalizeEngineValue } from '../engines/engine-registry.js';
import {
  deleteNestedValue,
  escapeAttributeValue,
  escapeTextareaValue,
  isThinkingParameterKey,
  setNestedValue
} from '../main/utils.js';
import { getJson, patchJson, postJson } from '../main/api.js';
import { t } from '../main/i18n.js';
import { messageDialog } from './dialogs.js';

// Parameters UI.
// Create helpers for model controls, tool selection, and option payloads.
export function createParametersUi(context) {
  const { dom, state } = context;

  // Tool selection helpers.
  // Normalize one tool server id for Set usage.
  function normalizeToolServerId(serverId) {
    return String(serverId || '').trim();
  }

  // Collect normalized ids for all bundled tool servers.
  function availableToolServerIds() {
    return new Set((state.availableToolServers || []).map(function mapServer(server) {
      return normalizeToolServerId(server && server.id);
    }).filter(Boolean));
  }

  // Replace the available tool server list and prune invalid selections.
  function updateAvailableToolServers(tools) {
    const all = Array.isArray(tools) ? tools.slice() : [];
    state.availableToolServers = all.filter(function filterBundled(server) {
      return !server || !server.user_mcp;
    });
    state.userMcpToolServers = all.filter(function filterUserMcp(server) {
      return server && server.user_mcp;
    });

    const validIds = new Set();
    state.availableToolServers.forEach(function collectId(server) {
      validIds.add(normalizeToolServerId(server.id));
    });
    state.userMcpToolServers.forEach(function collectUserMcpId(server) {
      validIds.add(normalizeToolServerId(server.id));
    });

    Array.from(state.selectedToolServerIds).forEach(function pruneSelected(id) {
      if (!validIds.has(id)) {
        state.selectedToolServerIds.delete(id);
      }
    });

    // Drop any selected tool whose Docker requirement is currently unmet.
    state.availableToolServers.forEach(function pruneUnavailable(server) {
      if (server && server.requires_docker && server.docker_available === false) {
        state.selectedToolServerIds.delete(normalizeToolServerId(server.id));
      }
    });

    renderToolControls();
  }

  // Apply selected tool ids, even if the live server list is not loaded yet.
  function applySelectedToolServerIds(ids) {
    // Chats can be restored before model capabilities arrive, so keep the raw
    // selection here and reconcile it against the live server list later.
    state.selectedToolServerIds = new Set(
      (Array.isArray(ids) ? ids : (ids ? [ids] : []))
        .map(function normalizeId(id) {
          return normalizeToolServerId(id);
        })
        .filter(Boolean)
    );

    renderToolControls();
  }

  // Tool server list rendering.
  function toolServerIconClass(server) {
    const text = `${server && server.id ? server.id : ''} ${server && server.name ? server.name : ''}`.toLowerCase();
    if (text.includes('browser')) {
      return 'is-browser-agent';
    }
    if (text.includes('sandbox')) {
      return 'is-sandbox';
    }
    if (text.includes('web') || text.includes('search')) {
      return 'is-web-search';
    }
    return 'is-generic-tool';
  }

  // Build the "requires Docker" info affordance, mirroring the settings help icon.
  function buildDockerHelp() {
    const text = t('tools.requiresDocker', null, 'This tool requires Docker.');
    const $help = $('<span class="setting-help composer-tool-help" tabindex="0" role="button">').attr('aria-label', text);
    $help.append('<span class="setting-help-icon" aria-hidden="true"></span>');
    $('<span class="setting-help-popover" role="tooltip">')
      .append($('<p class="setting-help-desc">').text(text))
      .appendTo($help);
    // The row is a <label>; keep hover/focus on the icon from toggling the checkbox.
    $help.on('mousedown click', function stopHelp(ev) {
      ev.stopPropagation();
    });
    return $help;
  }

  // Build the refresh control that re-probes the host for Docker and reloads tools.
  function buildDockerRefreshButton() {
    const text = t('tools.refreshDocker', null, 'Re-check Docker');
    const $btn = $('<button type="button" class="composer-tool-refresh">').attr({ 'aria-label': text, title: text });
    $btn.append('<span class="composer-tool-refresh-icon" aria-hidden="true"></span>');
    $btn.on('mousedown', function stopDown(ev) {
      ev.stopPropagation();
    });
    $btn.on('click', async function onRefresh(ev) {
      ev.preventDefault();
      ev.stopPropagation();
      if ($btn.hasClass('is-loading')) {
        return;
      }
      $btn.addClass('is-loading');
      try {
        await postJson('/api/docker_status/refresh/', {});
      } catch (_err) {
        // Ignore; the reload below reflects whatever the server now reports.
      }
      try {
        await reloadAvailableToolServers();
      } catch (_err) {
        $btn.removeClass('is-loading');
      }
    });
    return $btn;
  }

  // Render bundled tool server checkboxes into one target.
  function renderToolServerList($target, hasToolSupport) {
    $target.empty();
    if (!hasToolSupport) {
      return;
    }

    state.availableToolServers.forEach(function renderServer(server) {
      const serverId = normalizeToolServerId(server.id);
      const label = server.name || serverId;
      const requiresDocker = Boolean(server.requires_docker);
      const unavailable = requiresDocker && server.docker_available === false;
      const checked = state.selectedToolServerIds.has(serverId) && !unavailable;

      const $row = $('<label class="tool-server-row composer-tool-row">');
      if (unavailable) {
        $row.addClass('is-unavailable');
      }
      const $icon = $('<span class="composer-tool-icon">').addClass(toolServerIconClass(server)).attr('aria-hidden', 'true');
      const $checkbox = $('<input type="checkbox" class="tool-server-checkbox">').val(serverId).prop('checked', checked);
      const $name = $('<span class="tool-server-name">').text(label);

      $checkbox.prop('disabled', unavailable);
      $checkbox.on('change', function onChange() {
        if (this.checked) {
          state.selectedToolServerIds.add(serverId);
        } else {
          state.selectedToolServerIds.delete(serverId);
        }
        renderToolControls();
      });

      const $lead = $('<span class="composer-tool-label">').append($name);
      if (requiresDocker) {
        $lead.append(buildDockerHelp());
      }
      $row.append($icon).append($lead);
      if (unavailable) {
        $row.append(buildDockerRefreshButton());
      }
      $row.append($checkbox);
      $target.append($row);
    });
  }

  // Rebuild the tool server checkbox list from the current state.
  function renderToolControls() {
    const hasToolSupport = state.toolState.supported
      && Array.isArray(state.availableToolServers)
      && state.availableToolServers.length > 0;

    dom.$groupTools.hide();
    dom.$dividerTools.hide();
    dom.$composerToolMenus.toggle(hasToolSupport);

    const $content = dom.$groupTools.find('.settings-section-content');
    $content.empty();
    dom.$composerToolLists.each(function renderComposerToolList() {
      renderToolServerList($(this), hasToolSupport);
    });

    renderMcpControls();
  }

  // Render the MCP flyout entry (server list + JSON editor action) into the composer "Other" menu.
  // Mirrors the skills entry so MCP appears as a row with a flyout, not a standalone section.
  function renderMcpControls() {
    const show = Boolean(state.toolState.supported);
    dom.$composerMcpHosts.empty();
    if (!show) {
      return;
    }

    const userList = Array.isArray(state.userMcpToolServers) ? state.userMcpToolServers : [];
    const chevron = '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round"></path></svg>';

    dom.$composerMcpHosts.each(function renderMcpHost() {
      const $host = $(this);

      const $entry = $('<div class="composer-skills-entry">');
      const $trigger = $('<button type="button" class="composer-tool-row composer-skills-trigger" aria-haspopup="menu">');
      const $icon = $('<span class="composer-tool-icon is-mcp" aria-hidden="true">');
      const $name = $('<span class="tool-server-name">').text(t('settings.mcp'));
      const $chev = $('<span class="composer-skills-chevron" aria-hidden="true">').html(chevron);
      $trigger.append($icon).append($name).append($chev);

      const $flyout = $('<div class="composer-skills-flyout composer-mcp-flyout" role="menu">').attr('aria-label', t('settings.mcp'));
      const $list = $('<div class="composer-skills-flyout-list">');

      if (!userList.length) {
        $list.append($('<div class="composer-skills-empty">').text(t('mcp.noServers', null, 'No MCP servers')));
      } else {
        userList.forEach(function renderUserMcpServer(server) {
          const serverId = normalizeToolServerId(server.id);
          const toolCount = Number(server.tool_count || (server.tools || []).length || 0);
          const displayName = server.name || serverId;
          const label = toolCount > 0
            ? t('mcp.serverTools', { name: displayName, count: toolCount })
            : displayName;
          const checked = state.selectedToolServerIds.has(serverId);

          const $row = $('<label class="tool-server-row composer-tool-row mcp-user-tool-server-row">');
          const $rowName = $('<span class="tool-server-name">').text(label);
          const $checkbox = $('<input type="checkbox" class="tool-server-checkbox">').val(serverId).prop('checked', checked);

          $row.on('mousedown click', function onRowPointer(ev) {
            ev.stopPropagation();
          });
          $checkbox.on('mousedown click', function onCheckboxPointer(ev) {
            ev.stopPropagation();
          });
          $checkbox.on('change', function onChange() {
            if (this.checked) {
              state.selectedToolServerIds.add(serverId);
            } else {
              state.selectedToolServerIds.delete(serverId);
            }
          });

          $row.append($rowName).append($checkbox);
          $list.append($row);
        });
      }

      const $reload = $('<button type="button" class="composer-menu-action composer-skills-manage" role="menuitem">')
        .append($('<span class="composer-tool-icon is-mcp" aria-hidden="true">'))
        .append($('<span>').text(t('mcp.reload', null, 'Reload MCP servers')));
      $reload.on('click', function onReloadMcp(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        reloadUserMcpServers($reload);
      });

      const $manage = $('<button type="button" class="composer-menu-action composer-skills-manage" role="menuitem">')
        .append($('<span class="composer-tool-icon is-mcp" aria-hidden="true">'))
        .append($('<span>').text(t('mcp.editConfig')));
      $manage.on('click', function onOpenMcp(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        openMcpJsonEditor();
      });

      const $divider = $('<div class="composer-skills-flyout-divider" aria-hidden="true">');

      $flyout.on('click', function onFlyoutClick(ev) {
        ev.stopPropagation();
      });
      $flyout.append($list).append($divider).append($reload).append($manage);
      $entry.append($trigger).append($flyout);
      $host.append($entry);
    });
  }

  // MCP JSON editor helpers.
  function escapeHtmlPlain(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  // Highlight JSON source for the MCP JSON editor.
  function highlightJsonHtml(source) {
    const text = String(source || '');
    if (typeof hljs === 'undefined' || !hljs.highlight) {
      return escapeHtmlPlain(text);
    }
    try {
      return hljs.highlight(text, { language: 'json', ignoreIllegals: true }).value;
    } catch (_err) {
      return escapeHtmlPlain(text);
    }
  }

  // Build line numbers for the MCP JSON editor gutter.
  function buildGutterLines(lineCount) {
    const lines = [];
    for (let i = 1; i <= lineCount; i += 1) {
      lines.push(String(i));
    }
    return lines.join('\n');
  }

  // Re-fetch the live tool server list and refresh the composer controls.
  async function reloadAvailableToolServers() {
    const engine = normalizeEngineValue(state.activeEngine || 'ollama-service');
    const modelName = String(dom.$modelSelector.val() || '').trim();
    const data = await getJson(
      `/api/tools/?engine=${encodeURIComponent(engine)}&model=${encodeURIComponent(modelName)}`
    );
    updateAvailableToolServers(data.tool_servers || data.tools || data.servers || []);
  }

  // Restart persistent user MCP sessions and apply the fresh server inventory.
  async function reloadUserMcpServers($button) {
    if ($button && $button.prop('disabled')) {
      return;
    }

    const engine = normalizeEngineValue(state.activeEngine || 'ollama-service');
    const modelName = String(dom.$modelSelector.val() || '').trim();
    if ($button) {
      $button.prop('disabled', true).attr('aria-busy', 'true');
    }

    try {
      const data = await postJson('/api/mcp_reload/', { engine, model: modelName });
      updateAvailableToolServers(data.tool_servers || data.tools || data.servers || []);
    } catch (err) {
      await messageDialog(
        t('errors.generic', null, 'Something went wrong'),
        err && err.message ? err.message : String(err)
      );
    } finally {
      if ($button) {
        $button.prop('disabled', false).removeAttr('aria-busy');
      }
    }
  }

  // Reload tool servers after MCP config is saved.
  async function refreshToolServersAfterMcpSave() {
    await reloadAvailableToolServers();
  }

  // Open the modal MCP JSON configuration editor.
  async function openMcpJsonEditor() {
    let data;
    try {
      data = await getJson('/api/mcp_config/');
    } catch (err) {
      await messageDialog(t('errors.generic', null, 'Something went wrong'), err && err.message ? err.message : String(err));
      return;
    }

    const initial = typeof data.content === 'string' ? data.content : '';

    const $modal = $('<div class="mcp-json-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="mcpJsonModalTitle">');
    const $box = $('<div class="mcp-json-modal">');
    const $title = $('<div class="mcp-json-modal-title" id="mcpJsonModalTitle">').text(t('mcp.modalTitle'));
    const $editor = $('<div class="mcp-json-editor">');
    const $body = $('<div class="mcp-json-editor-body">');
    const $gutter = $('<div class="mcp-json-editor-gutter" aria-hidden="true">');
    const $gutterInner = $('<div class="mcp-json-editor-gutter-inner">');
    const $cell = $('<div class="mcp-json-editor-cell">');
    const $hlWrap = $('<div class="mcp-json-highlight-layer">');
    const $pre = $('<pre class="mcp-json-highlight-pre">');
    const $code = $('<code class="hljs language-json">');
    const $ta = $('<textarea class="mcp-json-editor-textarea" spellcheck="false" autocapitalize="off" autocomplete="off" autocorrect="off">').val(initial);

    $pre.append($code);
    $hlWrap.append($pre);
    $gutter.append($gutterInner);
    $cell.append($hlWrap).append($ta);
    $body.append($gutter).append($cell);
    $editor.append($body);

    const $err = $('<div class="mcp-json-modal-error" role="alert">').hide();
    const $actions = $('<div class="mcp-json-modal-actions">');
    const $cancel = $('<button type="button" class="preset-action-btn">').text(t('mcp.cancel'));
    const $save = $('<button type="button" class="preset-action-btn preset-action-btn-primary">').text(t('mcp.save'));
    $actions.append($cancel).append($save);

    function syncLayers() {
      const raw = $ta.val();
      $code.html(highlightJsonHtml(raw));
      const lines = raw.length === 0 ? 1 : raw.split('\n').length;
      $gutterInner.text(buildGutterLines(lines));
      const sh = $ta.prop('scrollHeight');
      $pre.css('min-height', `${Math.max(sh, $ta.outerHeight() || 0)}px`);
    }

    function syncScroll() {
      const st = $ta.scrollTop();
      $hlWrap.css('transform', `translateY(-${st}px)`);
      $gutterInner.css('transform', `translateY(-${st}px)`);
    }

    $ta.on('input', function onInput() {
      syncLayers();
      syncScroll();
    });
    $ta.on('scroll', syncScroll);

    function closeModal() {
      $modal.remove();
    }

    $cancel.on('click', closeModal);
    $modal.on('click', function onBackdrop(ev) {
      if (ev.target === $modal[0]) {
        closeModal();
      }
    });

    $save.on('click', async function onSave(ev) {
      if (ev) {
        ev.preventDefault();
        ev.stopPropagation();
      }
      $err.hide();
      try {
        await patchJson('/api/mcp_config/', { content: $ta.val() });
        closeModal();
        try {
          await refreshToolServersAfterMcpSave();
        } catch (refreshErr) {
          if (typeof window.console !== 'undefined' && window.console.warn) {
            window.console.warn(refreshErr);
          }
        }
      } catch (err) {
        $err.text(err && err.message ? err.message : String(err)).show();
      }
    });

    $box.append($title).append($editor).append($err).append($actions);
    $modal.append($box);
    $('body').append($modal);
    requestAnimationFrame(function afterLayout() {
      syncLayers();
      syncScroll();
      $ta.trigger('focus');
    });
  }


  // Dynamic panel helpers.
  // Show a placeholder in the model selector while models are unavailable.
  function showModelPlaceholder(message) {
    const placeholderText = message || 'Models load on demand';
    dom.$modelSelector.empty().append(
      $('<option>').val('').text(placeholderText)
    );
  }

  // Hide and clear all model-dependent settings panels.
  function resetDynamicPanels() {
    $('.settings-section').filter(function filterPanels() {
      return this.id.startsWith('group-')
        && this.id !== 'group-connection'
        && this.id !== 'group-system'
        && this.id !== 'group-model'
        && this.id !== 'group-sandbox-default';
    }).hide().find('.settings-section-content').empty();

    $('.settings-divider[id^="divider-"]').not('#divider-connection, #divider-sandbox-default').hide();
  }


  // Parameter definition helpers.
  // Return parameter definitions supported by the current engine.
  function getSupportedParameterDefinitions(engine) {
    const canonicalEngine = normalizeEngineValue(engine);
    return Object.entries(PARAMETER_DEFINITIONS).filter(function filterSupported([key, definition]) {
      if (!(definition.engines || []).includes(canonicalEngine)) {
        return false;
      }

      if (isThinkingParameterKey(key)) {
        return false;
      }

      if (canonicalEngine === 'ollama-service' && OLLAMA_UNSUPPORTED_RUNTIME_PARAMS.has(key)) {
        return false;
      }

      return true;
    });
  }

  // Map one parameter key to its target settings group.
  function getParameterGroup(paramKey) {
    if (PARAMETER_DEFINITIONS[paramKey] && PARAMETER_DEFINITIONS[paramKey].group) {
      return `#group-${PARAMETER_DEFINITIONS[paramKey].group}`;
    }
    if (['temperature', 'num_ctx', 'num_predict', 'seed', 'num_keep'].includes(paramKey)) {
      return '#group-settings';
    }
    if (['top_k', 'top_p', 'min_p', 'repeat_penalty', 'presence_penalty', 'frequency_penalty', 'mirostat', 'tfs_z', 'typical_p', 'repeat_last_n'].includes(paramKey)) {
      return '#group-sampling';
    }
    if (['think', 'think_level', 'thinking', 'reasoning', 'thinking_level', 'reasoning_effort'].includes(paramKey)) {
      return '#group-custom';
    }
    return '#group-advanced';
  }

  // Infer the editor type for an unknown runtime parameter.
  function inferExperimentalParameterType(key, value) {
    if (typeof value === 'boolean') {
      return 'boolean';
    }

    if (typeof value === 'number') {
      return Number.isInteger(value) ? 'integer' : 'number';
    }

    if (Array.isArray(value) || (value && typeof value === 'object')) {
      return 'json';
    }

    if (typeof value === 'string' && LLM_PARAMETER_OPTION_SETS[key]) {
      return 'select';
    }

    return 'string';
  }

  // Convert a raw parameter key into a readable label.
  function formatExperimentalParameterLabel(key) {
    return key
      .replace(/[._-]+/g, ' ')
      .replace(/\b\w/g, function capitalize(letter) {
        return letter.toUpperCase();
      });
  }

  // Resolve the localized label for one parameter.
  function localizedParamLabel(key, config) {
    const fallback = (config && config.label) || formatExperimentalParameterLabel(key);
    return t(`parameters.${key}.label`, {}, fallback);
  }

  // Resolve the localized help note for one parameter.
  function localizedParamNote(key, config) {
    if (config && config.note) {
      return t(`parameters.${key}.note`, {}, config.note);
    }
    return getParameterNote(config, key);
  }

  // Build the help text shown under a parameter control.
  function getParameterNote(config, paramKey) {
    if (!config) {
      return '';
    }

    if (config.note && paramKey) {
      return t(`parameters.${paramKey}.note`, {}, config.note);
    }

    if (config.note) {
      return config.note;
    }

    if (config.type === 'range' || config.type === 'optional-number') {
      const parts = [`Range: ${config.min} - ${config.max}`];
      if (config.step !== undefined) {
        parts.push(`step ${config.step}`);
      }
      return parts.join(', ');
    }

    if (config.type === 'select' && Array.isArray(config.options)) {
      const labels = config.options.map(function mapLabels(option) {
        return typeof option === 'object' ? option.label : String(option);
      });
      return `Options: ${labels.join(', ')}`;
    }

    if (config.type === 'json') {
      return 'Accepts a JSON object/array. Plain text is also accepted when supported by the engine.';
    }

    if (config.type === 'string' && config.example) {
      return `Example: ${config.example}`;
    }

    return '';
  }

  // Format one metadata value for the parameter chip row.
  function formatParameterMetaValue(value) {
    if (value === null || value === undefined || value === '') {
      return 'auto';
    }
    return String(value);
  }

  // Build the metadata chips shown for a parameter.
  function getParameterMeta(config) {
    if (!config) {
      return [];
    }

    const meta = [];
    if (config.min !== undefined) {
      meta.push({ label: 'Min', value: formatParameterMetaValue(config.min) });
    }
    if (config.max !== undefined) {
      meta.push({ label: 'Max', value: formatParameterMetaValue(config.max) });
    }
    if (config.step !== undefined) {
      meta.push({ label: 'Step', value: formatParameterMetaValue(config.step) });
    }
    if (config.fallback !== undefined) {
      meta.push({ label: 'Default', value: formatParameterMetaValue(config.fallback) });
    }
    return meta;
  }

  // Resolve the placeholder text for a parameter input.
  function getInputPlaceholder(config) {
    if (!config) {
      return '';
    }

    if (config.placeholder) {
      return config.placeholder;
    }

    if (config.example) {
      return config.example;
    }

    if (config.type === 'optional-number' && config.min !== undefined && config.max !== undefined) {
      return `${config.min} - ${config.max}`;
    }

    if (config.type === 'json') {
      return 'Enter JSON value';
    }

    return '';
  }

  // Render the metadata chip row for a parameter.
  function renderParameterMeta(config) {
    const metaItems = getParameterMeta(config);
    if (!metaItems.length) {
      return '';
    }

    return `
      <div class="setting-meta" aria-hidden="true">
        ${metaItems.map(function renderMetaItem(item) {
          return `
            <span class="setting-meta-chip">
              <span class="setting-meta-label">${item.label}</span>
              <span class="setting-meta-value">${escapeAttributeValue(item.value)}</span>
            </span>
          `;
        }).join('')}
      </div>
    `;
  }

  // Build sensible slider steps for token-based controls.
  function buildTokenStepValues(minValue, maxValue) {
    const values = [];
    const normalizedMin = Math.max(128, Number(minValue) || 128);
    const normalizedMax = Math.max(normalizedMin, Number(maxValue) || normalizedMin);

    for (let value = normalizedMin; value <= Math.min(normalizedMax, 1024); value += 128) {
      values.push(value);
    }

    if (normalizedMax > 1024) {
      const start = values.length && values[values.length - 1] >= 1024 ? 2048 : 1024;
      for (let value = start; value <= normalizedMax; value += 1024) {
        if (!values.includes(value)) {
          values.push(value);
        }
      }
    }

    if (!values.length || values[values.length - 1] !== normalizedMax) {
      values.push(normalizedMax);
    }

    return values;
  }

  // Snap a token-range value to the nearest allowed slider step.
  function resolveTokenRangeValue(rawValue, allowedValues) {
    const numericValue = Number(rawValue);
    if (!allowedValues.length) {
      return Number.isFinite(numericValue) ? numericValue : 0;
    }

    if (!Number.isFinite(numericValue)) {
      return allowedValues[0];
    }

    return allowedValues.reduce(function findClosest(closest, candidate) {
      return Math.abs(candidate - numericValue) < Math.abs(closest - numericValue) ? candidate : closest;
    }, allowedValues[0]);
  }


  // Parameter rendering.
  // Render one supported parameter control into its target group.
  // Build the help icon plus its hover/focus popover (description and allowed
  // values) for one parameter. Returns '' when there is nothing to show.
  function buildParamHelpHtml(key, config) {
    const note = localizedParamNote(key, config);
    const metrics = getParameterMeta(config);
    if (!note && !metrics.length) {
      return '';
    }
    const descHtml = note ? `<p class="setting-help-desc">${note}</p>` : '';
    const metricsHtml = metrics.length
      ? `<div class="setting-help-metrics">${metrics.map(function metricRow(item) {
          return `<div class="setting-help-metric"><span class="setting-help-metric-key">${item.label}</span><span class="setting-help-metric-val">${escapeAttributeValue(item.value)}</span></div>`;
        }).join('')}</div>`
      : '';
    const aria = escapeAttributeValue(t('settings.paramInfo', null, 'Parameter details'));
    return `<span class="setting-help" tabindex="0" role="button" aria-label="${aria}">`
      + '<span class="setting-help-icon" aria-hidden="true"></span>'
      + `<span class="setting-help-popover" role="tooltip">${descHtml}${metricsHtml}</span>`
      + '</span>';
  }

  // Build the label lead (parameter name + help affordance) shared by all controls.
  function buildLabelLead(key, config) {
    return `<span class="setting-label-lead"><span class="setting-label-text">${localizedParamLabel(key, config)}</span>${buildParamHelpHtml(key, config)}</span>`;
  }

  // Inline width for the numeric value field. The minimum is fixed (in CSS) while
  // the width grows with the widest value the field can show, so long integers
  // (e.g. a six-digit context length) no longer overflow the box.
  function buildSettingNumberStyle(config) {
    const max = Number(config.max);
    const intDigits = Number.isFinite(max) ? String(Math.floor(Math.abs(max))).length : 4;
    const decimals = Number(config.decimals) || 0;
    const chars = intDigits + (decimals > 0 ? decimals + 1 : 0) + (Number(config.min) < 0 ? 1 : 0);
    return `width: calc(${chars}ch + 16px);`;
  }

  // Render one supported parameter control into its target group.
  function renderKnownParameter(key, config, value, renderOptions) {
    const options = renderOptions || {};
    const groupId = options.groupId || getParameterGroup(key);
    const $group = $(groupId);
    const $content = $(`${groupId} .settings-section-content`);
    const paramClass = options.paramClass || 'dyn-param';
    const paramPath = options.paramPath || key;
    const compactClass = options.compact ? ' setting-control-compact' : '';
    const noteText = localizedParamNote(key, config);
    const labelLead = buildLabelLead(key, config);
    const numberStyle = buildSettingNumberStyle(config);
    let html = '';

    if (config.type === 'select') {
      const valueType = config.valueType || 'string';
      const normalizedValue = value === undefined || value === null ? config.fallback : value;
      html = `
        <div class="setting-group">
          <label class="setting-label" for="dyn_${key}">
            ${labelLead}
          </label>
          <select
            class="model-selector setting-select${compactClass} ${paramClass}"
            id="dyn_${key}"
            data-param="${key}"
            data-param-path="${paramPath}"
            data-value-type="${valueType}">
            ${(config.options || []).map(function renderOption(option) {
              const optionValue = typeof option === 'object' ? option.value : option;
              const optionLabel = typeof option === 'object' ? option.label : formatExperimentalParameterLabel(String(option));
              return `<option value="${escapeAttributeValue(String(optionValue))}"${String(optionValue) === String(normalizedValue) ? ' selected' : ''}>${optionLabel}</option>`;
            }).join('')}
          </select>        </div>
      `;
    } else if (config.type === 'boolean') {
      const normalizedValue = value === undefined || value === null ? !!config.fallback : !!value;
      html = `
        <div class="setting-group">
          <label class="setting-label setting-label-switch" for="dyn_${key}">
            ${labelLead}
            <span class="setting-switch-control">
              <input
                class="setting-switch-input ${paramClass}"
                id="dyn_${key}"
                type="checkbox"
                data-param="${key}"
                data-param-path="${paramPath}"
                data-value-type="boolean-switch"
                ${normalizedValue ? 'checked' : ''}>
              <span class="setting-switch-slider" aria-hidden="true"></span>
            </span>
          </label>        </div>
      `;
    } else if (config.type === 'optional-number') {
      const isEnabled = value !== undefined && value !== null && value !== '';
      const normalizedValue = isEnabled ? Number(value) : '';
      const optionalValueType = config.decimals === 0 ? 'optional-integer' : 'optional-number';
      html = `
        <div class="setting-group">
          <label class="setting-label setting-label-switch" for="toggle_${key}">
            ${labelLead}
            <span class="setting-switch-control">
              <input
                class="setting-switch-input optional-param-toggle"
                id="toggle_${key}"
                type="checkbox"
                data-target="dyn_${key}"
                ${isEnabled ? 'checked' : ''}>
              <span class="setting-switch-slider" aria-hidden="true"></span>
            </span>
          </label>
          <div class="setting-dependent-field${isEnabled ? '' : ' is-hidden'}" id="dyn_${key}_container">
            <input
              type="number"
              class="setting-input${compactClass} ${paramClass}"
              id="dyn_${key}"
              data-param="${key}"
              data-param-path="${paramPath}"
              data-value-type="${optionalValueType}"
              data-decimals="${config.decimals}"
              min="${config.min}"
              max="${config.max}"
              step="${config.step}"
              placeholder="${escapeAttributeValue(getInputPlaceholder(config))}"
              title="${escapeAttributeValue(noteText || '')}"
              value="${isEnabled ? escapeAttributeValue(String(normalizedValue)) : ''}"
              ${isEnabled ? '' : 'disabled'}>
          </div>        </div>
      `;
    } else if (config.type === 'json') {
      const normalizedValue = value === undefined || value === null ? config.fallback : value;
      html = `
        <div class="setting-group">
          <label class="setting-label" for="dyn_${key}">
            ${labelLead}
          </label>
          <textarea
            class="setting-textarea${compactClass} ${paramClass}"
            id="dyn_${key}"
            data-param="${key}"
            data-param-path="${paramPath}"
            data-value-type="json"
            placeholder="${escapeAttributeValue(getInputPlaceholder(config))}"
            rows="4">${normalizedValue === null ? '' : escapeTextareaValue(JSON.stringify(normalizedValue, null, 2))}</textarea>        </div>
      `;
    } else if (config.type === 'string') {
      const normalizedValue = value === undefined || value === null ? config.fallback : value;
      html = `
        <div class="setting-group">
          <label class="setting-label" for="dyn_${key}">
            ${labelLead}
          </label>
          <input
            type="text"
            class="setting-input${compactClass} ${paramClass}"
            id="dyn_${key}"
            data-param="${key}"
            data-param-path="${paramPath}"
            data-value-type="string"
            placeholder="${escapeAttributeValue(getInputPlaceholder(config))}"
            title="${escapeAttributeValue(noteText || '')}"
            value="${escapeAttributeValue(String(normalizedValue || ''))}">        </div>
      `;
    } else if (config.type === 'token-range') {
      const allowedValues = buildTokenStepValues(config.min, config.max);
      const resolvedValue = resolveTokenRangeValue(
        value === undefined || value === null ? config.fallback : value,
        allowedValues
      );
      const sliderIndex = Math.max(allowedValues.indexOf(resolvedValue), 0);
      html = `
        <div class="setting-group">
          <label class="setting-label" for="dyn_${key}">
            ${labelLead}
            <input
              type="number"
              class="setting-number"
              style="${numberStyle}"
              id="val_${key}"
              data-param="${key}"
              data-decimals="${config.decimals}"
              data-scale="token-range"
              value="${resolvedValue}"
              min="${config.min}"
              max="${config.max}"
              step="128">
          </label>
          <input
            type="range"
            class="setting-range ${paramClass}"
            id="dyn_${key}"
            data-param="${key}"
            data-param-path="${paramPath}"
            data-value-type="integer"
            data-decimals="${config.decimals}"
            data-scale="token-range"
            data-allowed-values="${escapeAttributeValue(JSON.stringify(allowedValues))}"
            min="0"
            max="${Math.max(allowedValues.length - 1, 0)}"
            step="1"
            value="${sliderIndex}">        </div>
      `;
    } else {
      const numericValue = Number(value === undefined || value === null ? config.fallback : value);
      html = `
        <div class="setting-group">
          <label class="setting-label" for="dyn_${key}">
            ${labelLead}
            <input
              type="number"
              class="setting-number"
              style="${numberStyle}"
              id="val_${key}"
              data-param="${key}"
              data-decimals="${config.decimals}"
              value="${numericValue.toFixed(config.decimals)}"
              min="${config.min}"
              max="${config.max}"
              step="${config.step}">
          </label>
          <input
            type="range"
            class="setting-range ${paramClass}"
            id="dyn_${key}"
            data-param="${key}"
            data-param-path="${paramPath}"
            data-value-type="${config.decimals === 0 ? 'integer' : 'number'}"
            data-decimals="${config.decimals}"
            min="${config.min}"
            max="${config.max}"
            step="${config.step}"
            value="${numericValue}">        </div>
      `;
    }

    $content.append(html);
    $group.show();
  }

  // Render an unknown parameter using a best-effort generic editor.
  function renderExperimentalParameter(key, value) {
    const groupId = getParameterGroup(key);
    const $group = $(groupId);
    const $content = $(`${groupId} .settings-section-content`);
    const valueType = inferExperimentalParameterType(key, value);
    const label = formatExperimentalParameterLabel(key);
    let controlHtml = '';

    if (valueType === 'boolean') {
      controlHtml = `
        <select
          class="model-selector setting-select dyn-param"
          id="dyn_${key}"
          data-param="${key}"
          data-value-type="boolean">
          <option value="true"${value ? ' selected' : ''}>True</option>
          <option value="false"${!value ? ' selected' : ''}>False</option>
        </select>
      `;
    } else if (valueType === 'select') {
      const options = LLM_PARAMETER_OPTION_SETS[key] || [];
      controlHtml = `
        <select
          class="model-selector setting-select dyn-param"
          id="dyn_${key}"
          data-param="${key}"
          data-value-type="string">
          ${options.map(function renderExperimentalOption(optionValue) {
            return `<option value="${optionValue}"${optionValue === value ? ' selected' : ''}>${formatExperimentalParameterLabel(optionValue)}</option>`;
          }).join('')}
        </select>
      `;
    } else if (valueType === 'json') {
      controlHtml = `
        <textarea
          class="setting-textarea dyn-param"
          id="dyn_${key}"
          data-param="${key}"
          data-value-type="json"
          rows="4">${escapeTextareaValue(JSON.stringify(value, null, 2))}</textarea>
      `;
    } else {
      const inputType = valueType === 'string' ? 'text' : 'number';
      controlHtml = `
        <input
          type="${inputType}"
          class="setting-input dyn-param"
          id="dyn_${key}"
          data-param="${key}"
          data-value-type="${valueType}"
          value="${escapeAttributeValue(String(value ?? ''))}">
      `;
    }

    const html = `
      <div class="setting-group">
        <label class="setting-label" for="dyn_${key}">
          ${label}
        </label>
        ${controlHtml}
      </div>
    `;

    $content.append(html);
    $group.show();
  }

  // Show only the dividers required by the visible settings groups.
  function updateVisibleDividers() {
    $('#divider-system').hide();

    const visibleGroups = ['load', 'custom', 'settings', 'sampling', 'advanced'].filter(function isVisible(groupName) {
      return $(`#group-${groupName}`).is(':visible');
    });

    if (visibleGroups.length > 0) {
      $('#divider-system').show();
    }

    visibleGroups.forEach(function showDivider(groupName, index) {
      const nextGroup = visibleGroups[index + 1];
      if (!nextGroup) {
        return;
      }

      if (nextGroup === 'sampling' || groupName === 'custom') {
        return;
      }

      $(`#divider-${groupName}`).show();
    });
  }


  // Thinking controls.
  // Rebuild both think-level button strips from the model payload.
  function renderThinkLevelControls() {
    $('.think-toggle-btn').not('.think-level-selector .think-toggle-btn').remove();

    const metadataOptions = Array.isArray(state.thinkState.levelOptions)
      ? state.thinkState.levelOptions
      : [];
    const canDisableThinking = !!state.thinkState.toggleSupported;
    const baseOptions = state.thinkState.levelSupported
      ? metadataOptions
      : (state.thinkState.supported ? ['on'] : []);
    const normalizedOptions = (canDisableThinking ? ['off'] : []).concat(baseOptions)
      .map(function normalizeOption(optionValue) {
        return String(optionValue || '').trim().toLowerCase();
      })
      .filter(function uniqueOption(optionValue, index, options) {
        return optionValue && options.indexOf(optionValue) === index;
      });

    function labelForThinkOption(normalizedValue) {
      const labels = {
        off: 'Off',
        on: 'On',
        minimal: 'Minimal',
        low: 'Low',
        medium: 'Medium',
        high: 'High',
        xhigh: 'XHigh',
        max: 'Max',
        ultra: 'Ultra'
      };
      if (labels[normalizedValue]) {
        return labels[normalizedValue];
      }
      return normalizedValue
        .replace(/[_-]+/g, ' ')
        .replace(/\b\w/g, function capitalize(letter) {
          return letter.toUpperCase();
        });
    }

    [
      { $selector: dom.$thinkLevelSelector, buttonId: 'thinkToggleBtn' },
      { $selector: dom.$thinkLevelSelectorConv, buttonId: 'thinkToggleBtnConv' }
    ].forEach(function rebuildSelector(pair) {
      const $selector = pair.$selector;
      let $trigger = $selector.find('.think-toggle-btn').first();
      let $menu = $selector.find('.think-level-menu').first();

      if (!$trigger.length) {
        $trigger = $('<button type="button" class="think-toggle-btn">');
      }
      $trigger
        .attr({
          id: pair.buttonId,
          title: 'Reasoning effort',
          'aria-haspopup': 'menu',
          'aria-expanded': 'false'
        })
        .empty()
        .append($('<span class="think-toggle-label">').text('Off'))
        .append(
          $('<svg class="think-toggle-chevron" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true">')
            .append($('<path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round">'))
        );

      if (!$menu.length) {
        $menu = $('<div class="think-level-menu" role="menu" aria-label="Reasoning effort" style="display:none;">');
      }
      $menu.empty().append($('<div class="think-level-menu-title">').text(t('composer.intelligence')));

      normalizedOptions.forEach(function appendOption(optionValue) {
        const normalizedValue = String(optionValue || '').trim().toLowerCase();
        if (!normalizedValue) {
          return;
        }

        $menu.append(
          $('<button type="button" class="think-level-btn">')
            .attr('data-value', normalizedValue)
            .attr('role', 'menuitem')
            .append($('<span class="think-level-btn-label">').text(labelForThinkOption(normalizedValue)))
            .append($('<span class="think-level-check" aria-hidden="true">').text('\u2713'))
        );
      });

      $selector.empty().append($trigger).append($menu);
    });

    dom.$thinkToggleBtn = dom.$thinkLevelSelector.find('.think-toggle-btn').first();
    dom.$thinkToggleBtnConv = dom.$thinkLevelSelectorConv.find('.think-toggle-btn').first();
  }

  // Resolve the display label for one thinking level value.
  function getThinkLevelLabel(value) {
    const normalizedValue = String(value || '').trim().toLowerCase();
    const $matchingButton = dom.$thinkLevelSelector
      .add(dom.$thinkLevelSelectorConv)
      .find(`.think-level-btn[data-value="${normalizedValue}"]`)
      .first();
    if ($matchingButton.length) {
      return $matchingButton.find('.think-level-btn-label').text() || $matchingButton.text().trim();
    }
    return normalizedValue || 'Off';
  }

  // Update think toggles and think-level selectors for both composers.
  function updateThinkControls() {
    const hasLevelOptions = state.thinkState.levelSupported
      && Array.isArray(state.thinkState.levelOptions)
      && state.thinkState.levelOptions.length > 0;
    const canDisableThinking = !!state.thinkState.toggleSupported;
    const showThinkControl = state.thinkState.supported
      && (hasLevelOptions || state.thinkState.toggleSupported || state.thinkState.supported);
    let selectedValue = '';
    if (hasLevelOptions) {
      selectedValue = canDisableThinking && (!state.thinkState.enabled || String(state.thinkState.level || '').toLowerCase() === 'off')
        ? 'off'
        : String(state.thinkState.level || state.thinkState.levelOptions[0] || '').toLowerCase();
    } else {
      selectedValue = state.thinkState.enabled ? 'on' : 'off';
    }
    const selectedLabel = getThinkLevelLabel(selectedValue);

    [dom.$thinkLevelSelector, dom.$thinkLevelSelectorConv].forEach(function updatePair($selector) {
      const $toggle = $selector.find('.think-toggle-btn').first();

      if (!showThinkControl) {
        $selector.hide();
        $toggle.attr('aria-expanded', 'false');
        $selector.find('.think-level-menu').hide();
        return;
      }

      $selector.show();
      $toggle.show();
      $toggle
        .toggleClass('active', selectedValue !== 'off')
        .find('.think-toggle-label')
        .text(selectedLabel);
      $selector.find('.think-level-btn').each(function toggleButton() {
        $(this).toggleClass('active', $(this).data('value') === selectedValue);
      });
    });
  }


  // Model parameter rendering.
  // Render all supported and experimental parameters for the active model.
  function renderModelParameters(modelInfo, defaults) {
    const data = modelInfo || {};
    const engine = normalizeEngineValue(state.activeEngine);
    const remainingDefaults = { ...(defaults || {}) };
    // The caller clears dynamic panels before rebuilding model-dependent UI.
    // Repeating that reset here would also hide already-rendered non-dynamic
    // sections such as Tools.

    // Cloud-hosted models run on the engine's servers, so local execution
    // controls (the "load" group: GPU layers, main GPU, CPU threads, memory)
    // have no effect. The engine reports whether the model is cloud-hosted; we
    // derive which parameters to drop from each definition's own group instead
    // of a hardcoded list of option names.
    const hideLocalRuntimeParams = Boolean(data.is_cloud);

    getSupportedParameterDefinitions(engine).forEach(function renderDefinition([key, config]) {
      if (hideLocalRuntimeParams && config.group === 'load') {
        delete remainingDefaults[key];
        return;
      }

      const renderedConfig = { ...config };
      const runtimeLimits = data.runtime_limits || {};

      if (key === 'num_ctx' && data.context_length) {
        renderedConfig.max = data.context_length;
        renderedConfig.note = `Context window. Model limit: ${data.context_length}.`;
      }
      if (key === 'num_predict') {
        renderedConfig.max = Math.max(1024, Math.min(32768, data.context_length || renderedConfig.max || 32768));
        renderedConfig.note = `Maximum generated tokens. Limit: ${renderedConfig.max}.`;
      }
      if (key === 'max_output_tokens' && runtimeLimits.output_token_limit) {
        renderedConfig.max = runtimeLimits.output_token_limit;
        renderedConfig.note = `Maximum generated tokens. Model limit: ${runtimeLimits.output_token_limit}.`;
      }
      if (key === 'num_gpu' && runtimeLimits.model_layers) {
        renderedConfig.max = runtimeLimits.model_layers;
        renderedConfig.note = `GPU layers. Model layers: ${runtimeLimits.model_layers}.`;
      }
      if (key === 'main_gpu') {
        const gpuDevices = Array.isArray(runtimeLimits.gpu_devices) ? runtimeLimits.gpu_devices : [];
        renderedConfig.options = [{ value: '', label: 'Automatic' }].concat(
          gpuDevices.map(function mapDevice(device) {
            return {
              value: device.id,
              label: `GPU ${device.id} - ${device.name}`
            };
          })
        );
        renderedConfig.max = runtimeLimits.main_gpu_max || 0;
        renderedConfig.note = runtimeLimits.gpu_count > 0
          ? 'Primary GPU.'
          : 'No NVIDIA GPU detected by the local runtime.';
      }
      if (key === 'num_thread' && runtimeLimits.cpu_threads) {
        renderedConfig.max = runtimeLimits.cpu_threads;
        renderedConfig.note = `CPU threads. Detected: ${runtimeLimits.cpu_threads}.`;
      }

      const value = remainingDefaults[key] !== undefined ? remainingDefaults[key] : renderedConfig.fallback;
      renderKnownParameter(key, renderedConfig, value);
      delete remainingDefaults[key];
    });

    Object.entries(remainingDefaults).forEach(function renderUnknown([key, value]) {
      if (value !== undefined && value !== null) {
        renderExperimentalParameter(key, value);
      }
    });

    updateVisibleDividers();
  }


  // Payload collection.
  // Collect parameter values from a selector set into a nested payload object.
  function collectParameterPayload(selector) {
    const payload = {};
    $(selector).each(function collectValue() {
      const param = $(this).data('param');
      const paramPath = $(this).data('param-path') || $(this).data('paramPath') || param;
      const valueType = $(this).data('value-type') || 'number';
      const scale = $(this).data('scale');
      let rawValue = $(this).is(':checkbox') ? ($(this).is(':checked') ? 'true' : 'false') : $(this).val();

      if (scale === 'token-range') {
        const allowedValues = JSON.parse($(this).attr('data-allowed-values') || '[]');
        const resolvedValue = allowedValues[parseInt(rawValue, 10)] || allowedValues[0] || 0;
        rawValue = String(resolvedValue);
      }

      // Normalize each control according to the value type metadata stored on
      // the rendered input.
      if (valueType === 'boolean') {
        setNestedValue(payload, paramPath, String(rawValue).toLowerCase() === 'true');
        return;
      }

      if (valueType === 'boolean-switch') {
        setNestedValue(payload, paramPath, $(this).is(':checked'));
        return;
      }

      if (valueType === 'json') {
        if (String(rawValue || '').trim() === '') {
          deleteNestedValue(payload, paramPath);
          return;
        }
        try {
          setNestedValue(payload, paramPath, JSON.parse(rawValue));
        } catch (_error) {
          setNestedValue(payload, paramPath, rawValue);
        }
        return;
      }

      if (valueType === 'integer') {
        const integerValue = parseInt(rawValue, 10);
        if (!Number.isNaN(integerValue)) {
          setNestedValue(payload, paramPath, integerValue);
        }
        return;
      }

      if (valueType === 'optional-integer') {
        const toggleId = `#toggle_${param}`;
        if (!$(toggleId).is(':checked')) {
          deleteNestedValue(payload, paramPath);
          return;
        }

        const integerValue = parseInt(rawValue, 10);
        if (!Number.isNaN(integerValue)) {
          setNestedValue(payload, paramPath, integerValue);
        }
        return;
      }

      if (valueType === 'optional-number') {
        const toggleId = `#toggle_${param}`;
        if (!$(toggleId).is(':checked')) {
          deleteNestedValue(payload, paramPath);
          return;
        }

        const numericValue = parseFloat(rawValue);
        if (!Number.isNaN(numericValue)) {
          setNestedValue(payload, paramPath, numericValue);
        }
        return;
      }

      if (valueType === 'number') {
        const numericValue = parseFloat(rawValue);
        if (!Number.isNaN(numericValue)) {
          setNestedValue(payload, paramPath, numericValue);
        }
        return;
      }

      if (rawValue !== '') {
        setNestedValue(payload, paramPath, rawValue);
      }
    });

    return payload;
  }

  // Collect the final options payload sent to the backend.
  function collectOptionsPayload() {
    let payload = collectParameterPayload('#dynamicParameters .dyn-param');
    const adapter = getEngineAdapter(state.activeEngine);

    if (
      state.thinkState.supported
      && state.thinkState.toggleSupported
    ) {
      payload[state.thinkState.paramName] = state.thinkState.enabled;
    }
    if (
      state.thinkState.supported
      && state.thinkState.levelSupported
      && String(state.thinkState.level || '').toLowerCase() !== 'off'
    ) {
      payload[state.thinkState.levelParamName] = state.thinkState.level;
    }

    if (typeof adapter.sanitizeRequestOptions === 'function') {
      payload = adapter.sanitizeRequestOptions(payload);
    }

    return payload;
  }


  // Control synchronization.
  // Keep the numeric token range field in sync with its slider.
  function handleRangeInput($input) {
    const param = $input.data('param');
    const decimals = parseInt($input.data('decimals') || '0', 10);
    const scale = $input.data('scale');

    if (scale === 'token-range') {
      const allowedValues = JSON.parse($input.attr('data-allowed-values') || '[]');
      const index = parseInt($input.val(), 10);
      const resolvedValue = allowedValues[Math.max(index, 0)] || allowedValues[0] || 0;
      $(`#val_${param}`).val(resolvedValue);
      return;
    }

    $(`#val_${param}`).val(parseFloat($input.val()).toFixed(decimals));
  }

  // Clamp and sync the numeric input back into its paired slider.
  function handleNumberInput($input) {
    const param = $input.data('param');
    const decimals = parseInt($input.data('decimals') || '0', 10);
    const scale = $input.data('scale');

    if (scale === 'token-range') {
      const $range = $(`#dyn_${param}`);
      const allowedValues = JSON.parse($range.attr('data-allowed-values') || '[]');
      const resolvedValue = resolveTokenRangeValue($input.val(), allowedValues);
      const resolvedIndex = Math.max(allowedValues.indexOf(resolvedValue), 0);

      $input.val(String(resolvedValue));
      $range.val(resolvedIndex);
      return;
    }

    const min = parseFloat($input.attr('min'));
    const max = parseFloat($input.attr('max'));
    let value = parseFloat($input.val());

    if (Number.isNaN(value)) {
      value = parseFloat($(`#dyn_${param}`).val());
    }

    value = Math.min(max, Math.max(min, value));
    $input.val(value.toFixed(decimals));
    $(`#dyn_${param}`).val(value);
  }

  // Normalize optional numeric inputs while preserving empty disabled states.
  function normalizeOptionalNumericInput($input) {
    if ($input.prop('disabled')) {
      return;
    }

    const rawValue = String($input.val() || '').trim();
    if (!rawValue) {
      return;
    }

    const decimals = parseInt($input.data('decimals') || '0', 10);
    const min = parseFloat($input.attr('min'));
    const max = parseFloat($input.attr('max'));
    let numericValue = decimals === 0 ? parseInt(rawValue, 10) : parseFloat(rawValue);

    if (Number.isNaN(numericValue)) {
      return;
    }

    if (!Number.isNaN(min)) {
      numericValue = Math.max(min, numericValue);
    }
    if (!Number.isNaN(max)) {
      numericValue = Math.min(max, numericValue);
    }

    $input.val(decimals === 0 ? String(Math.round(numericValue)) : numericValue.toFixed(decimals));
  }

  // Show or hide one optional parameter input from its toggle state.
  function toggleOptionalParameter($toggle) {
    const targetId = $toggle.data('target');
    const $target = $(`#${targetId}`);
    const $targetContainer = $(`#${targetId}_container`);
    const isEnabled = $toggle.is(':checked');

    $target.prop('disabled', !isEnabled);
    $targetContainer.toggleClass('is-hidden', !isEnabled);
    if (isEnabled) {
      $target.trigger('focus');
    } else {
      $target.val('');
    }
  }

  // Return only selected tool ids that still exist in the live server list.
  function getSelectedToolServerIds() {
    const validIds = new Set();
    state.availableToolServers.forEach(function mapId(server) {
      validIds.add(normalizeToolServerId(server.id));
    });
    (state.userMcpToolServers || []).forEach(function mapUserMcpId(server) {
      validIds.add(normalizeToolServerId(server.id));
    });

    return Array.from(state.selectedToolServerIds).filter(function filterValid(id) {
      return validIds.has(id);
    });
  }

  return {
    applySelectedToolServerIds,
    collectOptionsPayload,
    getSelectedToolServerIds,
    getSupportedParameterDefinitions,
    handleNumberInput,
    handleRangeInput,
    normalizeOptionalNumericInput,
    renderModelParameters,
    reloadAvailableToolServers,
    renderThinkLevelControls,
    renderToolControls,
    resetDynamicPanels,
    showModelPlaceholder,
    toggleOptionalParameter,
    updateAvailableToolServers,
    updateThinkControls,
    updateVisibleDividers
  };
}
