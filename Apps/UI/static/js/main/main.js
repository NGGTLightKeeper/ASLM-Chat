'use strict';

$(function () {
  const $newChatBtn = $('#newChatBtn');
  const $historyList = $('#historyList');
  const $chatTitle = $('#chatTitle');
  const $messagesArea = $('#messagesArea');
  const $messagesInner = $('#messagesInner');
  const $welcomeScreen = $('#welcomeScreen');
  const $chatInput = $('#chatInput');
  const $sendBtn = $('#sendBtn');
  const $chatInputConv = $('#chatInputConv');
  const $sendBtnConv = $('#sendBtnConv');
  const $conversationInput = $('#conversationInput');
  const $engineSelector = $('#engineSelector');
  const $engineAddressGroup = $('#engineAddressGroup');
  const $engineAddressInput = $('#engineAddressInput');
  const $engineAddressStatus = $('#engineAddressStatus');
  const $engineAddressHint = $('#engineAddressHint');
  const $engineApiKeyGroup = $('#engineApiKeyGroup');
  const $engineApiKeyEnabled = $('#engineApiKeyEnabled');
  const $engineApiKeyInput = $('#engineApiKeyInput');
  const $engineApiKeyStatus = $('#engineApiKeyStatus');
  const $modelSelector = $('#modelSelector');

  let runtimeSettings = parseJsonScript('runtimeSettingsData') || {};
  let currentChatId = null;
  let engineSelectionVersion = 0;
  let activeEngine = 'ollama-service';
  let lmsLoadConfigDirty = false;
  const modelsCache = {};

  const ENGINE_ALIASES = {
    ollama: 'ollama-service',
    'ollama-service': 'ollama-service',
    lms: 'lms',
    'lm-studio': 'lms',
    openai: 'openai',
    'openai-api': 'openai'
  };

  const ENGINE_ADDRESS_KEYS = {
    lms: 'lms_url',
    openai: 'openai_url'
  };

  const ENGINE_ADDRESS_HINTS = {
    'ollama-service': 'Ollama uses the local service managed by ASLM.',
    lms: 'Example: http://127.0.0.1:1234',
    openai: 'Example: http://127.0.0.1:8000/v1'
  };

  activeEngine = normalizeEngineValue(
    runtimeSettings['llm-engine'] || $('body').data('llm-engine') || 'ollama-service'
  );

  const visionState = {
    supported: false,
    pending: []
  };

  const thinkState = {
    supported: false,
    paramName: 'think',
    enabled: true,
    levelSupported: false,
    levelParamName: 'think_level',
    level: 'medium'
  };

  const PARAMETER_DEFINITIONS = {
    temperature: {
      label: 'Temperature',
      type: 'range',
      group: 'settings',
      engines: ['ollama-service', 'lms', 'openai'],
      min: 0,
      max: 2,
      step: 0.1,
      decimals: 1,
      fallback: 0.8
    },
    num_ctx: {
      label: 'Context Length',
      type: 'range',
      group: 'settings',
      engines: ['ollama-service'],
      min: 256,
      max: 131072,
      step: 256,
      decimals: 0,
      fallback: 4096
    },
    num_predict: {
      label: 'Max Output Tokens',
      type: 'range',
      group: 'settings',
      engines: ['ollama-service'],
      min: -2,
      max: 32768,
      step: 32,
      decimals: 0,
      fallback: 512
    },
    num_keep: {
      label: 'Keep Prompt Tokens',
      type: 'range',
      group: 'settings',
      engines: ['ollama-service'],
      min: -1,
      max: 2048,
      step: 1,
      decimals: 0,
      fallback: 0
    },
    seed: {
      label: 'Seed',
      type: 'optional-number',
      group: 'advanced',
      engines: ['ollama-service', 'openai'],
      min: 0,
      max: 2147483647,
      step: 1,
      decimals: 0,
      fallback: null
    },
    top_p: {
      label: 'Top P',
      type: 'range',
      group: 'sampling',
      engines: ['ollama-service', 'openai'],
      min: 0,
      max: 1,
      step: 0.01,
      decimals: 2,
      fallback: 0.9
    },
    top_k: {
      label: 'Top K',
      type: 'range',
      group: 'sampling',
      engines: ['ollama-service'],
      min: 1,
      max: 1000,
      step: 1,
      decimals: 0,
      fallback: 40
    },
    min_p: {
      label: 'Min P',
      type: 'range',
      group: 'sampling',
      engines: ['ollama-service'],
      min: 0,
      max: 1,
      step: 0.01,
      decimals: 2,
      fallback: 0.0
    },
    repeat_last_n: {
      label: 'Repeat Window',
      type: 'range',
      group: 'sampling',
      engines: ['ollama-service'],
      min: -1,
      max: 4096,
      step: 1,
      decimals: 0,
      fallback: 64
    },
    repeat_penalty: {
      label: 'Repeat Penalty',
      type: 'range',
      group: 'sampling',
      engines: ['ollama-service'],
      min: 0,
      max: 3,
      step: 0.01,
      decimals: 2,
      fallback: 1.1
    },
    tfs_z: {
      label: 'TFS Z',
      type: 'range',
      group: 'sampling',
      engines: ['ollama-service'],
      min: 0,
      max: 2,
      step: 0.01,
      decimals: 2,
      fallback: 1.0
    },
    mirostat: {
      label: 'Mirostat',
      type: 'select',
      valueType: 'integer',
      group: 'sampling',
      engines: ['ollama-service'],
      options: [
        { value: 0, label: 'Off' },
        { value: 1, label: 'V1' },
        { value: 2, label: 'V2' }
      ],
      fallback: 0
    },
    mirostat_eta: {
      label: 'Mirostat Eta',
      type: 'range',
      group: 'sampling',
      engines: ['ollama-service'],
      min: 0,
      max: 1,
      step: 0.01,
      decimals: 2,
      fallback: 0.1
    },
    mirostat_tau: {
      label: 'Mirostat Tau',
      type: 'range',
      group: 'sampling',
      engines: ['ollama-service'],
      min: 0,
      max: 20,
      step: 0.1,
      decimals: 1,
      fallback: 5
    },
    stop: {
      label: 'Stop Sequences',
      type: 'json',
      group: 'advanced',
      engines: ['ollama-service', 'openai'],
      fallback: null
    },
    maxTokens: {
      label: 'Max Output Tokens',
      type: 'range',
      group: 'settings',
      engines: ['lms'],
      min: 1,
      max: 32768,
      step: 32,
      decimals: 0,
      fallback: 1024
    },
    topPSampling: {
      label: 'Top P',
      type: 'range',
      group: 'sampling',
      engines: ['lms'],
      min: 0,
      max: 1,
      step: 0.01,
      decimals: 2,
      fallback: 0.95
    },
    topKSampling: {
      label: 'Top K',
      type: 'range',
      group: 'sampling',
      engines: ['lms'],
      min: 1,
      max: 1000,
      step: 1,
      decimals: 0,
      fallback: 40
    },
    minPSampling: {
      label: 'Min P',
      type: 'range',
      group: 'sampling',
      engines: ['lms'],
      min: 0,
      max: 1,
      step: 0.01,
      decimals: 2,
      fallback: 0
    },
    repeatPenalty: {
      label: 'Repeat Penalty',
      type: 'range',
      group: 'sampling',
      engines: ['lms'],
      min: 0,
      max: 3,
      step: 0.01,
      decimals: 2,
      fallback: 1.0
    },
    xtcProbability: {
      label: 'XTC Probability',
      type: 'range',
      group: 'sampling',
      engines: ['lms'],
      min: 0,
      max: 1,
      step: 0.01,
      decimals: 2,
      fallback: 0
    },
    xtcThreshold: {
      label: 'XTC Threshold',
      type: 'range',
      group: 'sampling',
      engines: ['lms'],
      min: 0,
      max: 1,
      step: 0.01,
      decimals: 2,
      fallback: 0.1
    },
    cpuThreads: {
      label: 'CPU Threads',
      type: 'range',
      group: 'advanced',
      engines: ['lms'],
      min: 1,
      max: 64,
      step: 1,
      decimals: 0,
      fallback: 4
    },
    stopStrings: {
      label: 'Stop Sequences',
      type: 'json',
      group: 'advanced',
      engines: ['lms'],
      fallback: null
    },
    toolCallStopStrings: {
      label: 'Tool Stop Sequences',
      type: 'json',
      group: 'advanced',
      engines: ['lms'],
      fallback: null
    },
    contextOverflowPolicy: {
      label: 'Context Overflow Policy',
      type: 'select',
      valueType: 'string',
      group: 'custom',
      engines: ['lms'],
      options: [
        { value: 'stopAtLimit', label: 'Stop At Limit' },
        { value: 'truncateMiddle', label: 'Truncate Middle' },
        { value: 'rollingWindow', label: 'Rolling Window' }
      ],
      fallback: 'truncateMiddle'
    },
    draftModel: {
      label: 'Draft Model',
      type: 'select',
      valueType: 'string',
      group: 'advanced',
      engines: ['lms'],
      options: [
        { value: '', label: 'Disabled' }
      ],
      fallback: ''
    },
    max_completion_tokens: {
      label: 'Max Completion Tokens',
      type: 'range',
      group: 'settings',
      engines: ['openai'],
      min: 1,
      max: 32768,
      step: 32,
      decimals: 0,
      fallback: 1024
    },
    presence_penalty: {
      label: 'Presence Penalty',
      type: 'range',
      group: 'sampling',
      engines: ['openai'],
      min: -2,
      max: 2,
      step: 0.1,
      decimals: 1,
      fallback: 0.0
    },
    frequency_penalty: {
      label: 'Frequency Penalty',
      type: 'range',
      group: 'sampling',
      engines: ['openai'],
      min: -2,
      max: 2,
      step: 0.1,
      decimals: 1,
      fallback: 0.0
    },
    n: {
      label: 'Candidates',
      type: 'range',
      group: 'advanced',
      engines: ['openai'],
      min: 1,
      max: 8,
      step: 1,
      decimals: 0,
      fallback: 1
    },
    logprobs: {
      label: 'Logprobs',
      type: 'boolean',
      group: 'custom',
      engines: ['openai'],
      fallback: false
    },
    top_logprobs: {
      label: 'Top Logprobs',
      type: 'range',
      group: 'advanced',
      engines: ['openai'],
      min: 0,
      max: 20,
      step: 1,
      decimals: 0,
      fallback: 0
    },
    reasoning_effort: {
      label: 'Reasoning Effort',
      type: 'select',
      valueType: 'string',
      group: 'custom',
      engines: ['openai'],
      options: [
        { value: 'minimal', label: 'Minimal' },
        { value: 'low', label: 'Low' },
        { value: 'medium', label: 'Medium' },
        { value: 'high', label: 'High' },
        { value: 'xhigh', label: 'Extra High' }
      ],
      fallback: 'medium'
    },
    verbosity: {
      label: 'Verbosity',
      type: 'select',
      valueType: 'string',
      group: 'custom',
      engines: ['openai'],
      options: [
        { value: 'low', label: 'Low' },
        { value: 'medium', label: 'Medium' },
        { value: 'high', label: 'High' }
      ],
      fallback: 'medium'
    },
    response_format: {
      label: 'Response Format',
      type: 'json',
      group: 'advanced',
      engines: ['openai'],
      fallback: null
    },
    logit_bias: {
      label: 'Logit Bias',
      type: 'json',
      group: 'advanced',
      engines: ['openai'],
      fallback: null
    }
  };

  const LLM_LOAD_PARAMETER_DEFINITIONS = {
    contextLength: {
      label: 'Context Length',
      type: 'optional-number',
      path: 'contextLength',
      min: 1,
      max: 131072,
      step: 256,
      decimals: 0,
      fallback: null
    },
    gpu_ratio: {
      label: 'GPU Ratio',
      type: 'optional-number',
      path: 'gpu.ratio',
      min: 0,
      max: 1,
      step: 0.01,
      decimals: 2,
      fallback: null
    },
    gpu_mainGpu: {
      label: 'Main GPU',
      type: 'optional-number',
      path: 'gpu.mainGpu',
      min: 0,
      max: 16,
      step: 1,
      decimals: 0,
      fallback: null
    },
    gpu_splitStrategy: {
      label: 'GPU Split Strategy',
      type: 'select',
      valueType: 'string',
      path: 'gpu.splitStrategy',
      options: [
        { value: '', label: 'Automatic' },
        { value: 'evenly', label: 'Evenly' },
        { value: 'favorMainGpu', label: 'Favor Main GPU' }
      ],
      fallback: ''
    },
    gpu_disabledGpus: {
      label: 'Disabled GPUs',
      type: 'json',
      path: 'gpu.disabledGpus',
      fallback: null
    },
    gpuStrictVramCap: {
      label: 'Strict VRAM Cap',
      type: 'boolean',
      path: 'gpuStrictVramCap',
      fallback: false
    },
    offloadKVCacheToGpu: {
      label: 'Offload KV Cache To GPU',
      type: 'boolean',
      path: 'offloadKVCacheToGpu',
      fallback: false
    },
    ropeFrequencyBase: {
      label: 'RoPE Frequency Base',
      type: 'optional-number',
      path: 'ropeFrequencyBase',
      min: 0,
      max: 1000000,
      step: 1,
      decimals: 0,
      fallback: null
    },
    ropeFrequencyScale: {
      label: 'RoPE Frequency Scale',
      type: 'optional-number',
      path: 'ropeFrequencyScale',
      min: 0,
      max: 1000,
      step: 0.01,
      decimals: 2,
      fallback: null
    },
    evalBatchSize: {
      label: 'Eval Batch Size',
      type: 'optional-number',
      path: 'evalBatchSize',
      min: 1,
      max: 8192,
      step: 1,
      decimals: 0,
      fallback: null
    },
    flashAttention: {
      label: 'Flash Attention',
      type: 'boolean',
      path: 'flashAttention',
      fallback: false
    },
    keepModelInMemory: {
      label: 'Keep Model In Memory',
      type: 'boolean',
      path: 'keepModelInMemory',
      fallback: false
    },
    seed: {
      label: 'Seed',
      type: 'optional-number',
      path: 'seed',
      min: 0,
      max: 2147483647,
      step: 1,
      decimals: 0,
      fallback: null
    },
    useFp16ForKVCache: {
      label: 'Use FP16 For KV Cache',
      type: 'boolean',
      path: 'useFp16ForKVCache',
      fallback: false
    },
    tryMmap: {
      label: 'Try Memory Map',
      type: 'boolean',
      path: 'tryMmap',
      fallback: false
    },
    numExperts: {
      label: 'Num Experts',
      type: 'optional-number',
      path: 'numExperts',
      min: 1,
      max: 256,
      step: 1,
      decimals: 0,
      fallback: null
    },
    llamaKCacheQuantizationType: {
      label: 'K Cache Quantization',
      type: 'select',
      valueType: 'string',
      path: 'llamaKCacheQuantizationType',
      options: [
        { value: '', label: 'Automatic' },
        { value: 'f32', label: 'f32' },
        { value: 'f16', label: 'f16' },
        { value: 'q8_0', label: 'q8_0' },
        { value: 'q4_0', label: 'q4_0' },
        { value: 'q4_1', label: 'q4_1' },
        { value: 'iq4_nl', label: 'iq4_nl' },
        { value: 'q5_0', label: 'q5_0' },
        { value: 'q5_1', label: 'q5_1' }
      ],
      fallback: ''
    },
    llamaVCacheQuantizationType: {
      label: 'V Cache Quantization',
      type: 'select',
      valueType: 'string',
      path: 'llamaVCacheQuantizationType',
      options: [
        { value: '', label: 'Automatic' },
        { value: 'f32', label: 'f32' },
        { value: 'f16', label: 'f16' },
        { value: 'q8_0', label: 'q8_0' },
        { value: 'q4_0', label: 'q4_0' },
        { value: 'q4_1', label: 'q4_1' },
        { value: 'iq4_nl', label: 'iq4_nl' },
        { value: 'q5_0', label: 'q5_0' },
        { value: 'q5_1', label: 'q5_1' }
      ],
      fallback: ''
    }
  };

  const LLM_PARAMETER_OPTION_SETS = {
    reasoning_effort: ['minimal', 'low', 'medium', 'high', 'xhigh'],
    think_level: ['low', 'medium', 'high'],
    thinking_level: ['low', 'medium', 'high'],
    verbosity: ['low', 'medium', 'high']
  };

  function parseJsonScript(id) {
    const element = document.getElementById(id);
    if (!element) {
      return null;
    }

    try {
      return JSON.parse(element.textContent);
    } catch (_error) {
      return null;
    }
  }

  function normalizeEngineValue(engine) {
    const normalized = String(engine || '').trim().toLowerCase();
    return ENGINE_ALIASES[normalized] || normalized || 'ollama-service';
  }

  function getEngineAddressKey(engine) {
    return ENGINE_ADDRESS_KEYS[normalizeEngineValue(engine)] || null;
  }

  function getEngineAddress(engine) {
    const key = getEngineAddressKey(engine);
    return key ? (runtimeSettings[key] || '') : '';
  }

  function setEngineAddressStatus(text, state) {
    $engineAddressStatus.text(text || '');
    $engineAddressStatus.removeClass('is-pending is-error');

    if (state) {
      $engineAddressStatus.addClass(`is-${state}`);
    }
  }

  function setEngineApiKeyStatus(text, state) {
    $engineApiKeyStatus.text(text || '');
    $engineApiKeyStatus.removeClass('is-pending is-error');

    if (state) {
      $engineApiKeyStatus.addClass(`is-${state}`);
    }
  }

  function getActiveEngine() {
    return activeEngine;
  }

  function updateEngineAddressUi() {
    const engine = getActiveEngine();
    const addressKey = getEngineAddressKey(engine);
    const hasEditableAddress = Boolean(addressKey);
    const hasApiKeySupport = engine === 'openai';
    const hasStoredApiKey = hasApiKeySupport && !!runtimeSettings.has_openai_api_key;

    $engineAddressGroup.toggle(hasEditableAddress);
    $engineAddressHint.text(ENGINE_ADDRESS_HINTS[engine] || 'Configure the selected engine endpoint.');
    $engineApiKeyGroup.toggle(hasApiKeySupport);

    if (!hasEditableAddress) {
      setEngineAddressStatus('Managed', null);
    } else {
      $engineAddressInput.val(getEngineAddress(engine));
      setEngineAddressStatus('Saved', null);
    }

    if (!hasApiKeySupport) {
      $engineApiKeyEnabled.prop('checked', false);
      $engineApiKeyInput.val('').hide();
      setEngineApiKeyStatus('Off', null);
      return;
    }

    $engineApiKeyEnabled.prop('checked', hasStoredApiKey);
    $engineApiKeyInput.val('');
    $engineApiKeyInput.toggle(hasStoredApiKey);
    $engineApiKeyInput.attr(
      'placeholder',
      hasStoredApiKey ? 'Stored API key. Enter a new one to replace it' : 'Enter a new API key'
    );
    setEngineApiKeyStatus(hasStoredApiKey ? 'On' : 'Off', null);
  }

  function resetModelUiState(message) {
    const placeholderText = message || 'Models load on demand';
    $modelSelector.empty().append(
      $('<option>').val('').text(placeholderText)
    );
    resetDynamicPanels();
    renderLoadParameters();
    updateVisibleDividers();
    visionState.supported = false;
    thinkState.supported = false;
    thinkState.levelSupported = false;
    updateVisionControls();
    updateThinkControls();
  }

  function clearModelCache(engine) {
    const canonicalEngine = normalizeEngineValue(engine);
    delete modelsCache[canonicalEngine];
  }

  function getSupportedParameterDefinitions(engine) {
    const canonicalEngine = normalizeEngineValue(engine);
    return Object.entries(PARAMETER_DEFINITIONS).filter(function ([, definition]) {
      return (definition.engines || []).includes(canonicalEngine);
    });
  }

  function getAvailableModelsForEngine(engine) {
    const canonicalEngine = normalizeEngineValue(engine);

    if (Array.isArray(modelsCache[canonicalEngine]) && modelsCache[canonicalEngine].length > 0) {
      return modelsCache[canonicalEngine].slice();
    }

    return $modelSelector.find('option').map(function () {
      return $(this).val();
    }).get().filter(Boolean);
  }

  function renderModelOptions(models, preferredModel) {
    const uniqueModels = Array.from(new Set(models || []));
    const fallbackModel = uniqueModels[0] || '';
    const selectedModel = uniqueModels.includes(preferredModel) ? preferredModel : fallbackModel;

    $modelSelector.empty();

    if (!uniqueModels.length) {
      $modelSelector.append('<option value="">No models available</option>');
      return '';
    }

    uniqueModels.forEach(function (modelName) {
      const $option = $('<option>').val(modelName).text(modelName);
      if (modelName === selectedModel) {
        $option.prop('selected', true);
      }
      $modelSelector.append($option);
    });

    return selectedModel;
  }

  async function fetchModelsForEngine(engine) {
    const response = await fetch(`/api/models/?engine=${encodeURIComponent(engine)}`);
    if (!response.ok) {
      throw new Error(`Failed to load models: ${response.status}`);
    }
    const data = await response.json();
    return data.models || [];
  }

  async function ensureModelsLoadedForActiveEngine(options) {
    const loadOptions = options || {};
    const engine = getActiveEngine();
    const preferredModel = loadOptions.preferredModel || $modelSelector.val() || '';
    let selectedModel = '';

    if (Array.isArray(modelsCache[engine]) && modelsCache[engine].length > 0) {
      selectedModel = renderModelOptions(modelsCache[engine], preferredModel);
      await loadModelInfo(selectedModel);
      return selectedModel;
    }

    resetModelUiState('Loading models...');
    const models = await fetchModelsForEngine(engine);
    modelsCache[engine] = models;
    selectedModel = renderModelOptions(models, preferredModel);
    await loadModelInfo(selectedModel);
    return selectedModel;
  }

  async function saveRuntimeSettings(patch) {
    const response = await fetch('/api/runtime_settings/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify(patch)
    });

    if (!response.ok) {
      const errorData = await response.json().catch(function () {
        return {};
      });
      throw new Error(errorData.error || `Failed to save settings: ${response.status}`);
    }

    runtimeSettings = await response.json();
    return runtimeSettings;
  }

  async function reloadSelectedModel(engine, modelName) {
    if (!modelName) {
      return;
    }

    const response = await fetch('/api/reload_model/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify({
        engine,
        model: modelName
      })
    });

    if (!response.ok) {
      const errorData = await response.json().catch(function () {
        return {};
      });
      throw new Error(errorData.error || `Failed to reload model: ${response.status}`);
    }
  }

  async function applyLmsLoadConfigChange() {
    if (getActiveEngine() !== 'lms') {
      return;
    }

    const loadConfig = collectParameterPayload('#group-load .dyn-load-param');
    runtimeSettings = await saveRuntimeSettings({ lms_load_config: loadConfig });
    lmsLoadConfigDirty = true;
  }

  async function applyEngineSelection(engine, options) {
    const settingsOptions = options || {};
    const normalizedEngine = normalizeEngineValue(engine);
    const selectionVersion = ++engineSelectionVersion;
    const previousEngine = activeEngine;
    const autoLoadModels = settingsOptions.autoLoadModels !== false;

    activeEngine = normalizedEngine;
    $('body').data('llm-engine', normalizedEngine);
    $engineSelector.val(normalizedEngine);
    updateEngineAddressUi();
    resetModelUiState('Models load on demand');

    if (settingsOptions.persist === false) {
      runtimeSettings['llm-engine'] = normalizedEngine;
      clearModelCache(normalizedEngine);
      if (autoLoadModels) {
        try {
          await ensureModelsLoadedForActiveEngine({
            preferredModel: settingsOptions.preferredModel || ''
          });
        } catch (error) {
          console.error('Failed to load models after engine initialization:', error);
          resetModelUiState('No models available');
        }
      }
      return;
    }

    try {
      setEngineAddressStatus('Switching...', 'pending');
      runtimeSettings = await saveRuntimeSettings({ 'llm-engine': normalizedEngine });
      runtimeSettings['llm-engine'] = normalizedEngine;
      clearModelCache(normalizedEngine);

      if (selectionVersion !== engineSelectionVersion) {
        return;
      }

      updateEngineAddressUi();
      setEngineAddressStatus(getEngineAddressKey(normalizedEngine) ? 'Saved' : 'Managed', null);

      if (autoLoadModels) {
        try {
          await ensureModelsLoadedForActiveEngine({
            preferredModel: settingsOptions.preferredModel || ''
          });
        } catch (error) {
          console.error('Failed to load models after engine switch:', error);
          resetModelUiState('No models available');
        }
      }
    } catch (error) {
      activeEngine = previousEngine;
      runtimeSettings['llm-engine'] = previousEngine;
      $('body').data('llm-engine', previousEngine);
      $engineSelector.val(previousEngine);
      updateEngineAddressUi();
      resetModelUiState('Models load on demand');
      throw error;
    }
  }

  function buildChatTitle(text, hasImages) {
    if (text) {
      return text.substring(0, 40) + (text.length > 40 ? '...' : '');
    }
    return hasImages ? 'Image chat' : 'New Chat';
  }

  function updateSendButtons() {
    const hasPendingImages = visionState.pending.length > 0;
    $sendBtn.prop('disabled', !$chatInput.val().trim() && !hasPendingImages);
    $sendBtnConv.prop('disabled', !$chatInputConv.val().trim() && !hasPendingImages);
  }

  function startNewChat() {
    $chatTitle.text('New Chat');
    document.title = 'ASLM Chat';
    $messagesInner.find('.msg').remove();
    $conversationInput.hide();
    $welcomeScreen.show();
    $chatInput.val('').css('height', 'auto').focus();
    $chatInputConv.val('').css('height', 'auto');
    currentChatId = null;
    $('#historyList .chat-item').removeClass('active').removeAttr('aria-current');
    $messagesArea.show();
    clearPendingImages();
    updateSendButtons();
  }

  function updateVisionControls() {
    const show = visionState.supported;
    $('#attachBtn').toggle(show);
    $('#attachBtnConv').toggle(show);
    $('#visionBadge').toggle(show);
    $('#visionBadgeConv').toggle(show);
  }

  function clearPendingImages() {
    visionState.pending = [];
    $('#imagePreviewStrip').empty().hide();
    $('#imagePreviewStripConv').empty().hide();
    $('#imageInput').val('');
    $('#imageInputConv').val('');
    updateSendButtons();
  }

  function rebuildPreviewStrips() {
    const $strips = $('#imagePreviewStrip, #imagePreviewStripConv');
    $strips.empty();

    if (visionState.pending.length === 0) {
      $strips.hide();
      updateSendButtons();
      return;
    }

    visionState.pending.forEach(function (img, idx) {
      const html = `
        <div class="img-preview-thumb" data-idx="${idx}">
          <img src="${img.dataUrl}" alt="Attached image">
          <button class="img-preview-remove" aria-label="Remove image">
            <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
      `;
      $strips.append(html);
    });

    $strips.show();
    updateSendButtons();
  }

  function handleFileInput(event) {
    const maxImages = 20;
    const files = Array.from(event.target.files || []);
    if (!files.length) {
      return;
    }

    files.forEach(function (file) {
      if (!file.type.startsWith('image/')) {
        return;
      }
      if (visionState.pending.length >= maxImages) {
        console.warn(`Max ${maxImages} images allowed`);
        return;
      }

      const reader = new FileReader();
      reader.onload = function (loadEvent) {
        if (visionState.pending.length >= maxImages) {
          return;
        }

        const dataUrl = loadEvent.target.result;
        const base64 = dataUrl.split(',')[1];
        visionState.pending.push({ dataUrl, base64 });
        rebuildPreviewStrips();
      };
      reader.readAsDataURL(file);
    });

    $(event.target).val('');
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
      .replace(/[_-]+/g, ' ')
      .replace(/\b\w/g, function (letter) {
        return letter.toUpperCase();
      });
  }

  function getNestedValue(source, path) {
    return String(path || '').split('.').reduce(function (current, key) {
      if (!current || typeof current !== 'object') {
        return undefined;
      }
      return current[key];
    }, source);
  }

  function setNestedValue(target, path, value) {
    const parts = String(path || '').split('.').filter(Boolean);
    if (!parts.length) {
      return;
    }

    let cursor = target;
    parts.forEach(function (part, index) {
      if (index === parts.length - 1) {
        cursor[part] = value;
        return;
      }

      if (!cursor[part] || typeof cursor[part] !== 'object') {
        cursor[part] = {};
      }
      cursor = cursor[part];
    });
  }

  function resetDynamicPanels() {
    $('.settings-section').filter(function () {
      return this.id.startsWith('group-')
        && this.id !== 'group-connection'
        && this.id !== 'group-system'
        && this.id !== 'group-model';
    }).hide().find('.settings-section-content').empty();

    $('.settings-divider[id^="divider-"]').not('#divider-connection').hide();
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
            ${(config.options || []).map(function (option) {
              const optionValue = typeof option === 'object' ? option.value : option;
              const optionLabel = typeof option === 'object' ? option.label : formatExperimentalParameterLabel(String(option));
              return `<option value="${escapeAttributeValue(String(optionValue))}"${String(optionValue) === String(normalizedValue) ? ' selected' : ''}>${optionLabel}</option>`;
            }).join('')}
          </select>
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
          <div
            class="setting-dependent-field${isEnabled ? '' : ' is-hidden'}"
            id="dyn_${key}_container">
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
              value="${isEnabled ? escapeAttributeValue(String(normalizedValue)) : ''}"
              ${isEnabled ? '' : 'disabled'}>
          </div>
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
            rows="4">${normalizedValue === null ? '' : escapeTextareaValue(JSON.stringify(normalizedValue, null, 2))}</textarea>
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
          ${options.map(function (optionValue) {
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
    const visibleGroups = ['load', 'custom', 'settings', 'sampling', 'advanced'].filter(function (groupName) {
      return $(`#group-${groupName}`).is(':visible');
    });

    if (visibleGroups.length > 0) {
      $('#divider-system').show();
    }

    visibleGroups.forEach(function (groupName, index) {
      const nextGroup = visibleGroups[index + 1];
      if (!nextGroup) {
        return;
      }

      if (nextGroup === 'sampling') {
        return;
      }

      if (groupName === 'custom') {
        return;
      }

      $(`#divider-${groupName}`).show();
    });
  }

  function renderLoadParameters() {
    const engine = getActiveEngine();
    const $group = $('#group-load');
    const $content = $('#group-load .settings-section-content');
    const loadConfig = runtimeSettings.lms_load_config || {};
    const selectedMainModel = $modelSelector.val() || '';
    const lmsModels = getAvailableModelsForEngine('lms');

    $content.empty();
    $group.hide();

    if (engine !== 'lms') {
      return;
    }

    Object.entries(LLM_LOAD_PARAMETER_DEFINITIONS).forEach(function ([key, config]) {
      const renderConfig = { ...config };

      if (key === 'draftModel') {
        const draftOptions = lmsModels
          .filter(function (modelName) {
            return modelName && modelName !== selectedMainModel;
          })
          .map(function (modelName) {
            return { value: modelName, label: modelName };
          });

        renderConfig.options = [{ value: '', label: 'Disabled' }, ...draftOptions];
      }

      const currentValue = getNestedValue(loadConfig, config.path || key);
      renderKnownParameter(key, renderConfig, currentValue, {
        groupId: '#group-load',
        paramClass: 'dyn-load-param',
        paramPath: config.path || key,
        compact: true
      });
    });
  }

  function updateThinkControls() {
    [
      { $toggle: $('#thinkToggleBtn'), $selector: $('#thinkLevelSelector') },
      { $toggle: $('#thinkToggleBtnConv'), $selector: $('#thinkLevelSelectorConv') }
    ].forEach(function (pair) {
      if (!thinkState.supported) {
        pair.$toggle.hide();
        pair.$selector.hide();
        return;
      }

      pair.$toggle.show().toggleClass('active', thinkState.enabled);

      if (thinkState.levelSupported && thinkState.enabled) {
        pair.$selector.show();
        pair.$selector.find('.think-level-btn').each(function () {
          $(this).toggleClass('active', $(this).data('value') === thinkState.level);
        });
      } else {
        pair.$selector.hide();
      }
    });
  }

  async function loadModelInfo(model) {
    if (!model) {
      resetDynamicPanels();
      renderLoadParameters();
      updateVisibleDividers();
      visionState.supported = false;
      thinkState.supported = false;
      updateVisionControls();
      updateThinkControls();
      return;
    }

    try {
      const response = await fetch(`/api/model_info/?engine=${encodeURIComponent(getActiveEngine())}&model=${encodeURIComponent(model)}`);
      if (!response.ok) {
        throw new Error(`Failed to load model info: ${response.status}`);
      }

      const data = await response.json();
      resetDynamicPanels();
      renderLoadParameters();

      visionState.supported = !!data.supports_vision;
      updateVisionControls();
      clearPendingImages();

      thinkState.supported = !!data.supports_thinking;
      thinkState.paramName = data.think_param_name || 'think';
      thinkState.levelSupported = !!data.supports_think_level;
      thinkState.levelParamName = data.think_level_param_name || 'think_level';
      thinkState.enabled = data.defaults && data.defaults[thinkState.paramName] !== undefined
        ? String(data.defaults[thinkState.paramName]).toLowerCase() === 'true' || data.defaults[thinkState.paramName] === true
        : true;
      thinkState.level = data.defaults && data.defaults[thinkState.levelParamName] !== undefined
        ? String(data.defaults[thinkState.levelParamName])
        : 'medium';
      updateThinkControls();

      if (!data.defaults) {
        return;
      }

      const defaults = { ...data.defaults };
      delete defaults[thinkState.paramName];
      delete defaults[thinkState.levelParamName];

      getSupportedParameterDefinitions(getActiveEngine()).forEach(function ([key, config]) {
        const renderedConfig = { ...config };
        if (key === 'num_ctx' && data.context_length) {
          renderedConfig.max = data.context_length;
        }

        const value = defaults[key] !== undefined ? defaults[key] : renderedConfig.fallback;
        renderKnownParameter(key, renderedConfig, value);
        delete defaults[key];
      });

      Object.entries(defaults).forEach(function ([key, value]) {
        if (value !== undefined && value !== null) {
          renderExperimentalParameter(key, value);
        }
      });

      updateVisibleDividers();
    } catch (error) {
      console.error('Failed to load model parameters', error);
    }
  }

  function collectParameterPayload(selector) {
    const payload = {};
    $(selector).each(function () {
      const param = $(this).data('param');
      const paramPath = $(this).data('paramPath') || param;
      const valueType = $(this).data('value-type') || 'number';
      const rawValue = $(this).is(':checkbox') ? ($(this).is(':checked') ? 'true' : 'false') : $(this).val();

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
    const payload = collectParameterPayload('#dynamicParameters .dyn-param');

    if (thinkState.supported) {
      payload[thinkState.paramName] = thinkState.enabled;
      if (thinkState.levelSupported) {
        payload[thinkState.levelParamName] = thinkState.level;
      }
    }

    return payload;
  }

  function timeNow(dateInput) {
    const date = dateInput ? new Date(dateInput) : new Date();
    return date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n/g, '<br>');
  }

  function escapeAttributeValue(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function escapeTextareaValue(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function renderMessageHtml($msgRow, rawText) {
    const $thoughtsWrapper = $msgRow.find('.msg-thoughts-wrapper');
    const $thoughtsContent = $msgRow.find('.msg-thoughts-content');
    const $bubble = $msgRow.find('.msg-bubble');

    if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
      $bubble.html(escHtml(rawText));
      return;
    }

    let allThinkContent = '';
    let allMainContent = '';
    let currentIndex = 0;

    while (true) {
      const thinkStart = rawText.indexOf('<think>', currentIndex);
      if (thinkStart === -1) {
        allMainContent += rawText.substring(currentIndex);
        break;
      }

      allMainContent += rawText.substring(currentIndex, thinkStart);
      const thinkEnd = rawText.indexOf('</think>', thinkStart + 7);

      if (thinkEnd !== -1) {
        allThinkContent += rawText.substring(thinkStart + 7, thinkEnd) + '\n';
        currentIndex = thinkEnd + 8;
      } else {
        allThinkContent += rawText.substring(thinkStart + 7);
        break;
      }
    }

    if (allThinkContent.trim()) {
      $thoughtsWrapper.show();
      $thoughtsContent.text(allThinkContent.trim());
    } else {
      $thoughtsWrapper.hide();
    }

    if (allMainContent.trim()) {
      $bubble.html(`<div class="markdown-body">${DOMPurify.sanitize(marked.parse(allMainContent))}</div>`);
    } else {
      $bubble.html('');
    }
  }

  function appendMessage(role, text, images, timestamp) {
    const isUser = role === 'user';
    const label = isUser ? 'You' : 'ASLM';
    const timeStr = timeNow(timestamp);

    let imagesHtml = '';
    if (isUser && images && images.length > 0) {
      const content = images.map(function (image) {
        const src = typeof image === 'string' ? image : image.dataUrl;
        return `<img src="${src}" alt="Attached image">`;
      }).join('');
      imagesHtml = `<div class="msg-images">${content}</div>`;
    }

    const $row = $(`
      <div class="msg ${role}">
        <div class="msg-avatar">${isUser ? 'U' : 'A'}</div>
        <div class="msg-body">
          <div class="msg-meta">
            <span>${label}</span>
            <span>${timeStr}</span>
          </div>
          ${!isUser ? `
          <div class="msg-thoughts-wrapper" style="display:none;">
            <div class="msg-thoughts-toggle">Thought Process</div>
            <div class="msg-thoughts-content" style="display:none;"></div>
          </div>
          ` : ''}
          <div class="msg-bubble">${imagesHtml}</div>
        </div>
      </div>
    `);

    if (isUser) {
      $row.find('.msg-bubble').append($('<span>').text(text));
    } else {
      renderMessageHtml($row, text);
    }

    $messagesInner.append($row);
    scrollBottom();
  }

  function appendTyping(timestamp) {
    const timeStr = timeNow(timestamp);
    const $row = $(`
      <div class="msg assistant">
        <div class="msg-avatar">A</div>
        <div class="msg-body">
          <div class="msg-meta">
            <span>ASLM</span>
            <span>${timeStr}</span>
          </div>
          <div class="msg-thoughts-wrapper" style="display:none;">
            <div class="msg-thoughts-toggle">Thought Process</div>
            <div class="msg-thoughts-content" style="display:none;"></div>
          </div>
          <div class="msg-bubble">
            <div class="typing-indicator">
              <div class="typing-dot"></div>
              <div class="typing-dot"></div>
              <div class="typing-dot"></div>
            </div>
          </div>
        </div>
      </div>
    `);

    $messagesInner.append($row);
    return $row;
  }

  function scrollBottom() {
    $messagesArea.scrollTop($messagesArea[0].scrollHeight);
  }

  function getCsrfToken() {
    const tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
    if (tokenInput) {
      return tokenInput.value;
    }
    return getCookie('csrftoken');
  }

  function getCookie(name) {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : null;
  }

  async function streamChat(text, imagesToSend, $msgBubble) {
    const $bubbleContent = $msgBubble.find('.msg-bubble');

    try {
      const selectedModel = await ensureModelsLoadedForActiveEngine({
        preferredModel: $modelSelector.val()
      });

      if (!selectedModel) {
        throw new Error(`No models available for ${getActiveEngine()}`);
      }

      if (getActiveEngine() === 'lms' && lmsLoadConfigDirty) {
        await reloadSelectedModel('lms', selectedModel);
        await loadModelInfo(selectedModel);
        lmsLoadConfigDirty = false;
      }

      const payload = {
        engine: getActiveEngine(),
        message: text,
        model: selectedModel,
        system_prompt: $('#systemPrompt').val(),
        chat_id: currentChatId,
        options: collectOptionsPayload()
      };

      if (imagesToSend.length > 0) {
        payload.images = imagesToSend.map(function (img) {
          return img.base64;
        });
      }

      const response = await fetch('/api/chat/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify(payload)
      });

      $msgBubble.removeClass('typing-indicator');
      $bubbleContent.empty();

      if (!response.ok) {
        try {
          const errorData = await response.json();
          $bubbleContent.html(`[Error: ${errorData.error || 'Server error'}]`);
        } catch (_error) {
          $bubbleContent.html(`[Error: ${response.status} ${response.statusText}]`);
        }
        return;
      }

      const returnedChatId = response.headers.get('X-Chat-ID');
      if (returnedChatId && currentChatId !== returnedChatId) {
        currentChatId = returnedChatId;

        if ($(`#historyList .chat-item[data-chat-id="${currentChatId}"]`).length === 0) {
          $('#historyList .empty-state').remove();

          const title = buildChatTitle(text, imagesToSend.length > 0);
          const $newItem = $(`
            <a class="chat-item active" aria-current="page"
               href="/chat/${currentChatId}/"
               data-chat-id="${currentChatId}">
              <div class="chat-item-icon">
                <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
                </svg>
              </div>
              <div class="chat-item-body">
                <span class="chat-item-title">${escHtml(title)}</span>
                <span class="chat-item-date">just now</span>
              </div>
            </a>
          `);

          $('#historyList .chat-item').removeClass('active').removeAttr('aria-current');
          $('#historyList').prepend($newItem);
        }

        const chatTitle = buildChatTitle(text, imagesToSend.length > 0);
        $chatTitle.text(chatTitle);
        document.title = `${chatTitle} - ASLM`;
        history.pushState({ chatId: currentChatId }, chatTitle, `/chat/${currentChatId}/`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let fullText = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        const chunk = decoder.decode(value, { stream: true });
        fullText += chunk;

        const area = $messagesArea[0];
        const isNearBottom = area.scrollHeight - area.clientHeight <= area.scrollTop + 50;
        const $row = $msgBubble.closest('.msg');
        renderMessageHtml($row, fullText);

        if (isNearBottom) {
          scrollBottom();
        }
      }
    } catch (error) {
      $msgBubble.removeClass('typing-indicator');
      $bubbleContent.html(`[Error: failed to connect to server - ${error.message}]`);
    }
  }

  function sendMessage(text, $input) {
    if (!text && visionState.pending.length === 0) {
      return;
    }

    const imagesToSend = visionState.pending.slice();

    if ($welcomeScreen.is(':visible')) {
      $welcomeScreen.hide();
      $conversationInput.show();
      $chatInputConv.val('').css('height', 'auto').focus();
    }

    appendMessage('user', text, imagesToSend);
    $input.val('').css('height', 'auto');
    clearPendingImages();
    updateSendButtons();

    const $msgBubble = appendTyping();
    scrollBottom();
    streamChat(text, imagesToSend, $msgBubble);
  }

  function wireInput($input, $button) {
    $input.on('input', function () {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 200) + 'px';
      updateSendButtons();
    });

    $input.on('keydown', function (event) {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        if (!$button.prop('disabled')) {
          sendMessage($input.val().trim(), $input);
        }
      }
    });

    $button.on('click', function () {
      if (!$button.prop('disabled')) {
        sendMessage($input.val().trim(), $input);
      }
    });
  }

  function loadChat(chatId, pushState) {
    if (!chatId || currentChatId === chatId) {
      return;
    }

    $.ajax({
      url: `/api/chat/${chatId}/`,
      method: 'GET',
      success: function (data) {
        if (data.messages === undefined) {
          return;
        }

        currentChatId = chatId;
        $('#historyList .chat-item').removeClass('active').removeAttr('aria-current');
        $(`#historyList .chat-item[data-chat-id="${chatId}"]`).addClass('active').attr('aria-current', 'page');

        const title = data.title || 'Chat';
        $chatTitle.text(title);
        document.title = `${title} - ASLM`;

        if (pushState !== false) {
          history.pushState({ chatId }, title, `/chat/${chatId}/`);
        }

        $messagesInner.find('.msg').remove();
        $welcomeScreen.hide();
        $messagesArea.show();
        $conversationInput.show();

        data.messages.forEach(function (message) {
          appendMessage(message.role, message.content, message.images || [], message.created_at);
        });

        scrollBottom();
      },
      error: function (error) {
        console.error('Failed to load chat history:', error);
      }
    });
  }

  if (typeof marked !== 'undefined' && typeof hljs !== 'undefined') {
    marked.setOptions({
      highlight: function (code, lang) {
        const language = hljs.getLanguage(lang) ? lang : 'plaintext';
        return hljs.highlight(code, { language }).value;
      },
      breaks: true
    });
  }

  wireInput($chatInput, $sendBtn);
  wireInput($chatInputConv, $sendBtnConv);
  updateSendButtons();

  $newChatBtn.on('click', function (event) {
    if ($(this).attr('href') === '/') {
      event.preventDefault();
      startNewChat();
    }
  });

  $('#imageInput, #imageInputConv').on('change', handleFileInput);

  $(document).on('click', '#attachBtn', function () {
    $('#imageInput').trigger('click');
  });

  $(document).on('click', '#attachBtnConv', function () {
    $('#imageInputConv').trigger('click');
  });

  $(document).on('click', '.img-preview-remove', function (event) {
    event.stopPropagation();
    const index = $(this).closest('.img-preview-thumb').data('idx');
    visionState.pending.splice(index, 1);
    rebuildPreviewStrips();
  });

  $(document).on('click', '.settings-section-header', function () {
    $(this).parent('.settings-section').toggleClass('collapsed');
  });

  $(document).on('click', '.think-toggle-btn', function () {
    if (!thinkState.supported) {
      return;
    }
    thinkState.enabled = !thinkState.enabled;
    updateThinkControls();
  });

  $(document).on('click', '.think-level-btn', function () {
    thinkState.level = $(this).data('value');
    updateThinkControls();
  });

  $(document).on('input', '.setting-range', function () {
    const param = $(this).data('param');
    const decimals = parseInt($(this).data('decimals') || '0', 10);
    $(`#val_${param}`).val(parseFloat(this.value).toFixed(decimals));
  });

  $(document).on('change blur', '.setting-number', function () {
    const param = $(this).data('param');
    const decimals = parseInt($(this).data('decimals') || '0', 10);
    const min = parseFloat(this.min);
    const max = parseFloat(this.max);
    let value = parseFloat(this.value);

    if (Number.isNaN(value)) {
      value = parseFloat($(`#dyn_${param}`).val());
    }

    value = Math.min(max, Math.max(min, value));
    this.value = value.toFixed(decimals);
    $(`#dyn_${param}`).val(value);
  });

  $(document).on('keydown', '.setting-number', function (event) {
    if (event.key === 'Enter') {
      $(this).trigger('blur');
    }
  });

  $(document).on('change', '.optional-param-toggle', function () {
    const targetId = $(this).data('target');
    const $target = $(`#${targetId}`);
    const $targetContainer = $(`#${targetId}_container`);
    const isEnabled = $(this).is(':checked');

    $target.prop('disabled', !isEnabled);
    $targetContainer.toggleClass('is-hidden', !isEnabled);
    if (isEnabled) {
      $target.trigger('focus');
    } else {
      $target.val('');
    }

    if ($(this).closest('#group-load').length > 0) {
      applyLmsLoadConfigChange().catch(function (error) {
        console.error('Failed to update LM Studio load config:', error);
      });
    }
  });

  $messagesInner.on('click', '.msg-thoughts-toggle', function (event) {
    event.stopPropagation();
    const $wrapper = $(this).closest('.msg-thoughts-wrapper');
    const $content = $wrapper.find('.msg-thoughts-content');

    $content.slideToggle(200);
    $wrapper.toggleClass('expanded');
  });

  $(document).on('click', '#historyList .chat-item', function (event) {
    event.preventDefault();
    const chatId = $(this).data('chat-id');
    loadChat(chatId, true);
  });

  $engineSelector.on('change', async function () {
    try {
      await applyEngineSelection($(this).val(), {
        persist: true
      });
    } catch (error) {
      console.error('Failed to switch engine:', error);
      setEngineAddressStatus('Error', 'error');
    }
  });

  $engineAddressInput.on('keydown', function (event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      $(this).trigger('blur');
    }
  });

  $engineAddressInput.on('blur', async function () {
    const engine = getActiveEngine();
    const addressKey = getEngineAddressKey(engine);
    const addressValue = $(this).val().trim();
    const selectionVersion = ++engineSelectionVersion;

    if (!addressKey) {
      return;
    }

    if ((runtimeSettings[addressKey] || '') === addressValue) {
      setEngineAddressStatus('Saved', null);
      return;
    }

    try {
      setEngineAddressStatus('Saving...', 'pending');
      runtimeSettings = await saveRuntimeSettings({ [addressKey]: addressValue });
      clearModelCache(engine);

      if (selectionVersion !== engineSelectionVersion) {
        return;
      }

      updateEngineAddressUi();
      resetModelUiState('Loading models...');
      await ensureModelsLoadedForActiveEngine({
        preferredModel: ''
      });
    } catch (error) {
      console.error('Failed to save engine address:', error);
      setEngineAddressStatus('Error', 'error');
    }
  });

  $engineApiKeyEnabled.on('change', async function () {
    if (getActiveEngine() !== 'openai') {
      return;
    }

    const isEnabled = $(this).is(':checked');
    $engineApiKeyInput.toggle(isEnabled);
    if (isEnabled) {
      setEngineApiKeyStatus('On', null);
      $engineApiKeyInput.trigger('focus');
      return;
    }

    try {
      setEngineApiKeyStatus('Saving...', 'pending');
      runtimeSettings = await saveRuntimeSettings({ openai_api_key: '' });
      updateEngineAddressUi();
    } catch (error) {
      console.error('Failed to update API key state:', error);
      setEngineApiKeyStatus('Error', 'error');
    }
  });

  $engineApiKeyInput.on('keydown', function (event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      $(this).trigger('blur');
    }
  });

  $engineApiKeyInput.on('blur', async function () {
    if (getActiveEngine() !== 'openai' || !$engineApiKeyEnabled.is(':checked')) {
      return;
    }

    const apiKeyValue = $(this).val().trim();
    if (!apiKeyValue) {
      setEngineApiKeyStatus(runtimeSettings.has_openai_api_key ? 'On' : 'Off', null);
      return;
    }

    try {
      setEngineApiKeyStatus('Saving...', 'pending');
      runtimeSettings = await saveRuntimeSettings({ openai_api_key: apiKeyValue });
      $engineApiKeyInput.val('');
      updateEngineAddressUi();
    } catch (error) {
      console.error('Failed to save API key:', error);
      setEngineApiKeyStatus('Error', 'error');
    }
  });

  $modelSelector.on('change', function () {
    loadModelInfo($(this).val());
  });

  $(document).on('change', '#group-load .dyn-load-param', function () {
    applyLmsLoadConfigChange().catch(function (error) {
      console.error('Failed to update LM Studio load config:', error);
    });
  });

  $(document).on('blur', '#group-load .dyn-load-param', function () {
    if ($(this).is(':checkbox')) {
      return;
    }

    applyLmsLoadConfigChange().catch(function (error) {
      console.error('Failed to update LM Studio load config:', error);
    });
  });

  window.addEventListener('popstate', function (event) {
    if (event.state && event.state.chatId) {
      loadChat(event.state.chatId, false);
    } else {
      startNewChat();
    }
  });

  const preloadChatId = $('body').data('preload-chat');
  if (preloadChatId) {
    loadChat(preloadChatId, false);
  }

  updateEngineAddressUi();
  resetModelUiState('Loading models...');
  applyEngineSelection(getActiveEngine(), {
    persist: false
  }).catch(function (error) {
    console.error('Failed to initialize engine state:', error);
  });
});
