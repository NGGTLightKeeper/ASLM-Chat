// Copyright NGGT.LightKeeper. All Rights Reserved.

import {
  DEFAULT_THINK_LEVEL_OPTIONS,
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

export function createParametersUi(context) {
  const { dom, state } = context;

  function normalizeToolServerId(serverId) {
    return String(serverId || '').trim();
  }

  function updateAvailableToolServers(tools) {
    state.availableToolServers = Array.isArray(tools) ? tools.slice() : [];
    const validIds = new Set(
      state.availableToolServers.map(function mapId(server) {
        return normalizeToolServerId(server.id);
      })
    );

    Array.from(state.selectedToolServerIds).forEach(function pruneSelected(id) {
      if (!validIds.has(id)) {
        state.selectedToolServerIds.delete(id);
      }
    });

    renderToolControls();
  }

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

  function renderToolControls() {
    const hasToolSupport = state.toolState.supported
      && Array.isArray(state.availableToolServers)
      && state.availableToolServers.length > 0;

    dom.$groupTools.toggle(hasToolSupport);
    dom.$dividerTools.toggle(hasToolSupport);

    const $content = dom.$groupTools.find('.settings-section-content');
    $content.empty();

    if (!hasToolSupport) {
      return;
    }

    const $list = $('<div class="tool-server-list" id="toolServerList">');
    state.availableToolServers.forEach(function renderServer(server) {
      const serverId = normalizeToolServerId(server.id);
      const toolCount = Number(server.tool_count || (server.tools || []).length || 0);
      const label = toolCount > 0 ? `${server.name || serverId} (${toolCount} tools)` : (server.name || serverId);
      const checked = state.selectedToolServerIds.has(serverId);

      const $row = $('<label class="tool-server-row">');
      const $checkbox = $('<input type="checkbox" class="tool-server-checkbox">').val(serverId).prop('checked', checked);
      const $name = $('<span class="tool-server-name">').text(label);

      $checkbox.on('change', function onChange() {
        if (this.checked) {
          state.selectedToolServerIds.add(serverId);
        } else {
          state.selectedToolServerIds.delete(serverId);
        }
      });

      $row.append($checkbox).append($name);
      $list.append($row);
    });

    $content.append($list);
  }

  function showModelPlaceholder(message) {
    const placeholderText = message || 'Models load on demand';
    dom.$modelSelector.empty().append(
      $('<option>').val('').text(placeholderText)
    );
  }

  function resetDynamicPanels() {
    $('.settings-section').filter(function filterPanels() {
      return this.id.startsWith('group-')
        && this.id !== 'group-connection'
        && this.id !== 'group-system'
        && this.id !== 'group-model';
    }).hide().find('.settings-section-content').empty();

    $('.settings-divider[id^="divider-"]').not('#divider-connection').hide();
  }

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

  function formatExperimentalParameterLabel(key) {
    return key
      .replace(/[._-]+/g, ' ')
      .replace(/\b\w/g, function capitalize(letter) {
        return letter.toUpperCase();
      });
  }

  function getParameterNote(config) {
    if (!config) {
      return '';
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

  function formatParameterMetaValue(value) {
    if (value === null || value === undefined || value === '') {
      return 'auto';
    }
    return String(value);
  }

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

  function renderKnownParameter(key, config, value, renderOptions) {
    const options = renderOptions || {};
    const groupId = options.groupId || getParameterGroup(key);
    const $group = $(groupId);
    const $content = $(`${groupId} .settings-section-content`);
    const paramClass = options.paramClass || 'dyn-param';
    const paramPath = options.paramPath || key;
    const compactClass = options.compact ? ' setting-control-compact' : '';
    const switchRowClass = options.compact ? ' setting-switch-row-compact' : '';
    const noteText = getParameterNote(config);
    const noteHtml = noteText ? `<p class="setting-note">${noteText}</p>` : '';
    const metaHtml = renderParameterMeta(config);
    let html = '';

    if (config.type === 'select') {
      const valueType = config.valueType || 'string';
      const normalizedValue = value === undefined || value === null ? config.fallback : value;
      html = `
        <div class="setting-group">
          <label class="setting-label" for="dyn_${key}">
            ${config.label}
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
          </select>
          ${noteHtml}
          ${metaHtml}
        </div>
      `;
    } else if (config.type === 'boolean') {
      const normalizedValue = value === undefined || value === null ? !!config.fallback : !!value;
      html = `
        <div class="setting-group">
          <label class="setting-label" for="dyn_${key}">
            ${config.label}
          </label>
          <label class="setting-switch-row${switchRowClass}" for="dyn_${key}">
            <span class="setting-switch-text">Enabled</span>
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
          </label>
          ${noteHtml}
          ${metaHtml}
        </div>
      `;
    } else if (config.type === 'optional-number') {
      const isEnabled = value !== undefined && value !== null && value !== '';
      const normalizedValue = isEnabled ? Number(value) : '';
      const optionalValueType = config.decimals === 0 ? 'optional-integer' : 'optional-number';
      html = `
        <div class="setting-group">
          <label class="setting-label" for="dyn_${key}">
            ${config.label}
          </label>
          <label class="setting-switch-row${switchRowClass}" for="toggle_${key}">
            <span class="setting-switch-text">Specify value</span>
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
          </div>
          ${noteHtml}
          ${metaHtml}
        </div>
      `;
    } else if (config.type === 'json') {
      const normalizedValue = value === undefined || value === null ? config.fallback : value;
      html = `
        <div class="setting-group">
          <label class="setting-label" for="dyn_${key}">
            ${config.label}
          </label>
          <textarea
            class="setting-textarea${compactClass} ${paramClass}"
            id="dyn_${key}"
            data-param="${key}"
            data-param-path="${paramPath}"
            data-value-type="json"
            placeholder="${escapeAttributeValue(getInputPlaceholder(config))}"
            rows="4">${normalizedValue === null ? '' : escapeTextareaValue(JSON.stringify(normalizedValue, null, 2))}</textarea>
          ${noteHtml}
          ${metaHtml}
        </div>
      `;
    } else if (config.type === 'string') {
      const normalizedValue = value === undefined || value === null ? config.fallback : value;
      html = `
        <div class="setting-group">
          <label class="setting-label" for="dyn_${key}">
            ${config.label}
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
            value="${escapeAttributeValue(String(normalizedValue || ''))}">
          ${noteHtml}
          ${metaHtml}
        </div>
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
            ${config.label}
            <input
              type="number"
              class="setting-number"
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
            value="${sliderIndex}">
          ${noteHtml}
          ${metaHtml}
        </div>
      `;
    } else {
      const numericValue = Number(value === undefined || value === null ? config.fallback : value);
      html = `
        <div class="setting-group">
          <label class="setting-label" for="dyn_${key}">
            ${config.label}
            <input
              type="number"
              class="setting-number"
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
            value="${numericValue}">
          ${noteHtml}
          ${metaHtml}
        </div>
      `;
    }

    $content.append(html);
    $group.show();
  }

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

  function renderThinkLevelControls() {
    const normalizedOptions = Array.isArray(state.thinkState.levelOptions) && state.thinkState.levelOptions.length > 0
      ? state.thinkState.levelOptions
      : DEFAULT_THINK_LEVEL_OPTIONS;

    [dom.$thinkLevelSelector, dom.$thinkLevelSelectorConv].forEach(function rebuildSelector($selector) {
      $selector.empty();

      normalizedOptions.forEach(function appendOption(optionValue) {
        const normalizedValue = String(optionValue || '').trim();
        if (!normalizedValue) {
          return;
        }

        const label = normalizedValue
          .replace(/[_-]+/g, ' ')
          .replace(/\b\w/g, function capitalize(letter) {
            return letter.toUpperCase();
          });

        $selector.append(
          $('<button type="button" class="think-level-btn">')
            .attr('data-value', normalizedValue)
            .text(label)
        );
      });
    });
  }

  function updateThinkControls() {
    [
      { $toggle: dom.$thinkToggleBtn, $selector: dom.$thinkLevelSelector },
      { $toggle: dom.$thinkToggleBtnConv, $selector: dom.$thinkLevelSelectorConv }
    ].forEach(function updatePair(pair) {
      if (!state.thinkState.supported) {
        pair.$toggle.hide();
        pair.$selector.hide();
        return;
      }

      pair.$toggle.toggle(state.thinkState.toggleSupported && !state.thinkState.levelSupported);
      pair.$toggle.toggleClass('active', state.thinkState.enabled);

      if (state.thinkState.levelSupported) {
        pair.$selector.show();
        pair.$selector.find('.think-level-btn').each(function toggleButton() {
          $(this).toggleClass('active', $(this).data('value') === state.thinkState.level);
        });
      } else {
        pair.$selector.hide();
      }
    });
  }

  function renderModelParameters(modelInfo, defaults) {
    const data = modelInfo || {};
    const engine = normalizeEngineValue(state.activeEngine);
    const remainingDefaults = { ...(defaults || {}) };
    // The caller clears dynamic panels before rebuilding model-dependent UI.
    // Repeating that reset here would also hide already-rendered non-dynamic
    // sections such as Tools.

    getSupportedParameterDefinitions(engine).forEach(function renderDefinition([key, config]) {
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

  function collectOptionsPayload() {
    let payload = collectParameterPayload('#dynamicParameters .dyn-param');
    const adapter = getEngineAdapter(state.activeEngine);

    if (state.thinkState.supported && state.thinkState.toggleSupported && !state.thinkState.levelSupported) {
      payload[state.thinkState.paramName] = state.thinkState.enabled;
    }
    if (state.thinkState.supported && state.thinkState.levelSupported) {
      payload[state.thinkState.levelParamName] = state.thinkState.level;
    }

    if (typeof adapter.sanitizeRequestOptions === 'function') {
      payload = adapter.sanitizeRequestOptions(payload);
    }

    return payload;
  }

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

  function getSelectedToolServerIds() {
    const validIds = new Set(
      state.availableToolServers.map(function mapId(server) {
        return normalizeToolServerId(server.id);
      })
    );

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
