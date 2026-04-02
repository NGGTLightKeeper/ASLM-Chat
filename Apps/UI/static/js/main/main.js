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
  const $ollamaPresetGroup = $('#ollamaPresetGroup');
  const $ollamaPresetSelector = $('#ollamaPresetSelector');
  const $ollamaPresetCreateBtn = $('#ollamaPresetCreateBtn');
  const $ollamaPresetRenameBtn = $('#ollamaPresetRenameBtn');
  const $ollamaPresetDeleteBtn = $('#ollamaPresetDeleteBtn');
  const $groupTools = $('#group-tools');
  const $dividerTools = $('#divider-tools');
  const $toolInspectorModal = $('#toolInspectorModal');

  $('#toolInspectorClose').on('click', function () { $toolInspectorModal.removeClass('open'); });
  $toolInspectorModal.on('click', function (e) {
    if ($(e.target).is($toolInspectorModal)) { $toolInspectorModal.removeClass('open'); }
  });
  $(document).on('keydown', function (e) {
    if (e.key === 'Escape') { $toolInspectorModal.removeClass('open'); }
  });

  let runtimeSettings = parseJsonScript('runtimeSettingsData') || {};
  const defaultAvailableToolServers = parseJsonScript('availableToolServersData') || [];
  let availableToolServers = Array.isArray(defaultAvailableToolServers) ? defaultAvailableToolServers.slice() : [];
  let selectedToolServerIds = new Set();
  let currentChatId = null;
  let engineSelectionVersion = 0;
  let modelInfoRequestVersion = 0;
  let activeEngine = 'ollama-service';
  const modelsCache = {};
  let ollamaPresetState = {
    engine: '',
    model: '',
    activePresetId: '',
    presets: []
  };
  let ollamaPresetSyncTimer = null;
  let isChatGenerating = false;
  let currentAbortController = null;
  let queuedMessageCounter = 0;
  const chatRequestQueue = [];

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
  const OLLAMA_UNSUPPORTED_RUNTIME_PARAMS = new Set([
    'embedding_only',
    'f16_kv',
    'logits_all',
    'low_vram',
    'mirostat',
    'mirostat_eta',
    'mirostat_tau',
    'numa',
    'penalize_newline',
    'tfs_z',
    'use_mlock',
    'vocab_only'
  ]);

  activeEngine = normalizeEngineValue(
    runtimeSettings['llm-engine'] || $('body').data('llm-engine') || 'ollama-service'
  );

  const visionState = {
    supported: false
  };

  const fileState = {
    supported: false
  };

  const attachmentState = {
    pending: []
  };

  const thinkState = {
    supported: false,
    paramName: 'think',
    toggleSupported: false,
    enabled: true,
    levelSupported: false,
    levelParamName: 'think_level',
    levelOptions: ['low', 'medium', 'high'],
    level: 'medium'
  };

  const toolState = {
    supported: false
  };
  let currentModelInfo = null;

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
      type: 'token-range',
      group: 'settings',
      engines: ['ollama-service'],
      min: 128,
      max: 131072,
      step: 128,
      decimals: 0,
      fallback: 32768,
      note: 'Context window in tokens.'
    },
    num_predict: {
      label: 'Max Output Tokens',
      type: 'token-range',
      group: 'settings',
      engines: ['ollama-service'],
      min: 128,
      max: 32768,
      step: 128,
      decimals: 0,
      fallback: 8192,
      note: 'Maximum generated tokens.'
    },
    numa: {
      label: 'NUMA',
      type: 'boolean',
      group: 'load',
      engines: ['ollama-service'],
      fallback: false,
      note: 'NUMA-aware memory placement.'
    },
    num_batch: {
      label: 'Batch Size',
      type: 'optional-number',
      group: 'load',
      engines: ['ollama-service'],
      min: 1,
      max: 8192,
      step: 1,
      decimals: 0,
      fallback: null,
      note: 'Prompt batch size.'
    },
    num_gpu: {
      label: 'GPU Layers',
      type: 'optional-number',
      group: 'load',
      engines: ['ollama-service'],
      min: 0,
      max: 999,
      step: 1,
      decimals: 0,
      fallback: null,
      note: 'Layers offloaded to GPU.'
    },
    main_gpu: {
      label: 'Main GPU',
      type: 'select',
      valueType: 'integer',
      group: 'load',
      engines: ['ollama-service'],
      min: 0,
      max: 16,
      step: 1,
      decimals: 0,
      fallback: null,
      options: [
        { value: '', label: 'Automatic' }
      ],
      note: 'Primary GPU'
    },
    low_vram: {
      label: 'Low VRAM',
      type: 'boolean',
      group: 'load',
      engines: ['ollama-service'],
      fallback: false,
      note: 'Lower VRAM usage.'
    },
    f16_kv: {
      label: 'Use FP16 KV Cache',
      type: 'boolean',
      group: 'load',
      engines: ['ollama-service'],
      fallback: false,
      note: 'Use FP16 KV cache.'
    },
    logits_all: {
      label: 'Return Full Logits',
      type: 'boolean',
      group: 'load',
      engines: ['ollama-service'],
      fallback: false,
      note: 'Return logits for all tokens.'
    },
    vocab_only: {
      label: 'Vocabulary Only',
      type: 'boolean',
      group: 'load',
      engines: ['ollama-service'],
      fallback: false,
      note: 'Vocabulary-only load.'
    },
    use_mmap: {
      label: 'Use Memory Map',
      type: 'boolean',
      group: 'load',
      engines: ['ollama-service'],
      fallback: false,
      note: 'Use memory mapping.'
    },
    use_mlock: {
      label: 'Use Memory Lock',
      type: 'boolean',
      group: 'load',
      engines: ['ollama-service'],
      fallback: false,
      note: 'Lock model pages in RAM.'
    },
    embedding_only: {
      label: 'Embedding Only',
      type: 'boolean',
      group: 'load',
      engines: ['ollama-service'],
      fallback: false,
      note: 'Embedding-only load.'
    },
    num_thread: {
      label: 'CPU Threads',
      type: 'optional-number',
      group: 'load',
      engines: ['ollama-service'],
      min: 1,
      max: 128,
      step: 1,
      decimals: 0,
      fallback: null,
      note: 'CPU threads'
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
      fallback: 0,
      note: '-1 keeps all, 0 is automatic.'
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
      fallback: null,
      note: 'Deterministic seed.'
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
      fallback: 1.0,
      note: 'Tail-free sampling.'
    },
    typical_p: {
      label: 'Typical P',
      type: 'range',
      group: 'sampling',
      engines: ['ollama-service'],
      min: 0,
      max: 1,
      step: 0.01,
      decimals: 2,
      fallback: 1.0
    },
    presence_penalty: {
      label: 'Presence Penalty',
      type: 'range',
      group: 'sampling',
      engines: ['ollama-service', 'openai'],
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
      engines: ['ollama-service', 'openai'],
      min: -2,
      max: 2,
      step: 0.1,
      decimals: 1,
      fallback: 0.0
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
    logprobs: {
      label: 'Logprobs',
      type: 'boolean',
      group: 'custom',
      engines: ['ollama-service', 'openai'],
      fallback: false
    },
    top_logprobs: {
      label: 'Top Logprobs',
      type: 'range',
      group: 'advanced',
      engines: ['ollama-service', 'openai'],
      min: 0,
      max: 20,
      step: 1,
      decimals: 0,
      fallback: 0,
      note: 'Alternative token logprobs.'
    },
    keep_alive: {
      label: 'Keep Alive',
      type: 'string',
      group: 'load',
      engines: ['ollama-service'],
      fallback: '',
      note: 'How long to keep the model loaded.',
      example: '5m, 30s, 1h, -1'
    },
    format: {
      label: 'Response Format',
      type: 'json',
      group: 'advanced',
      engines: ['ollama-service'],
      fallback: null,
      note: 'JSON mode or JSON schema.'
    },
    penalize_newline: {
      label: 'Penalize Newline',
      type: 'boolean',
      group: 'advanced',
      engines: ['ollama-service'],
      fallback: false,
      note: 'Penalize newline tokens too.'
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

  function normalizeToolServerId(serverId) {
    return String(serverId || '').trim();
  }

  function updateAvailableToolServers(tools) {
    availableToolServers = Array.isArray(tools) ? tools.slice() : [];
    const validIds = new Set(availableToolServers.map(function (s) { return normalizeToolServerId(s.id); }));
    selectedToolServerIds.forEach(function (id) {
      if (!validIds.has(id)) selectedToolServerIds.delete(id);
    });
    renderToolControls();
  }

  function applySelectedToolServerIds(ids) {
    selectedToolServerIds = new Set();
    const validIds = new Set(availableToolServers.map(function (s) { return normalizeToolServerId(s.id); }));
    (Array.isArray(ids) ? ids : (ids ? [ids] : [])).forEach(function (id) {
      const normalized = normalizeToolServerId(id);
      if (validIds.has(normalized)) selectedToolServerIds.add(normalized);
    });
    renderToolControls();
  }

  function renderToolControls() {
    const hasToolSupport = toolState.supported && Array.isArray(availableToolServers) && availableToolServers.length > 0;

    $groupTools.toggle(hasToolSupport);
    $dividerTools.toggle(hasToolSupport);

    const $content = $groupTools.find('.settings-section-content');
    $content.empty();

    if (!hasToolSupport) return;

    const $list = $('<div class="tool-server-list" id="toolServerList">');
    availableToolServers.forEach(function (server) {
      const serverId = normalizeToolServerId(server.id);
      const toolCount = Number(server.tool_count || (server.tools || []).length || 0);
      const label = toolCount > 0 ? `${server.name || serverId} (${toolCount} tools)` : (server.name || serverId);
      const checked = selectedToolServerIds.has(serverId);

      const $row = $('<label class="tool-server-row">');
      const $checkbox = $('<input type="checkbox" class="tool-server-checkbox">').val(serverId).prop('checked', checked);
      const $name = $('<span class="tool-server-name">').text(label);

      $checkbox.on('change', function () {
        if (this.checked) {
          selectedToolServerIds.add(serverId);
        } else {
          selectedToolServerIds.delete(serverId);
        }
      });

      $row.append($checkbox).append($name);
      $list.append($row);
    });

    $content.append($list);
  }

  function resetModelUiState(message) {
    const placeholderText = message || 'Models load on demand';
    $modelSelector.empty().append(
      $('<option>').val('').text(placeholderText)
    );
    currentModelInfo = null;
    resetOllamaPresetUi();
    resetDynamicPanels();
    renderLoadParameters();
    updateVisibleDividers();
    visionState.supported = false;
    fileState.supported = false;
    thinkState.supported = false;
    thinkState.toggleSupported = false;
    thinkState.levelSupported = false;
    thinkState.levelOptions = ['low', 'medium', 'high'];
    thinkState.enabled = true;
    thinkState.level = 'medium';
    toolState.supported = false;
    updateAvailableToolServers(defaultAvailableToolServers);
    updateAttachmentControls();
    updateThinkControls();
    renderToolControls();
  }

  function clearModelCache(engine) {
    const canonicalEngine = normalizeEngineValue(engine);
    delete modelsCache[canonicalEngine];
  }

  function getSupportedParameterDefinitions(engine) {
    const canonicalEngine = normalizeEngineValue(engine);
    return Object.entries(PARAMETER_DEFINITIONS).filter(function ([key, definition]) {
      if (!(definition.engines || []).includes(canonicalEngine)) {
        return false;
      }
      if (canonicalEngine === 'ollama-service' && OLLAMA_UNSUPPORTED_RUNTIME_PARAMS.has(key)) {
        return false;
      }
      return true;
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

  function getSelectedModelName() {
    return String($modelSelector.val() || '').trim();
  }

  function getActiveOllamaPreset() {
    return (ollamaPresetState.presets || []).find(function (preset) {
      return preset.id === ollamaPresetState.activePresetId;
    }) || null;
  }

  function resetOllamaPresetUi() {
    ollamaPresetState = {
      engine: '',
      model: '',
      activePresetId: '',
      presets: []
    };
    $ollamaPresetSelector.empty().append('<option value="">Default</option>');
    $ollamaPresetGroup.hide();
    $ollamaPresetRenameBtn.prop('disabled', true);
    $ollamaPresetDeleteBtn.prop('disabled', true);
  }

  function applyOllamaPresetState(payload) {
    const activeEngine = getActiveEngine();
    if (!payload || !['ollama-service', 'lms'].includes(activeEngine) || !getSelectedModelName()) {
      resetOllamaPresetUi();
      return;
    }

    ollamaPresetState = {
      engine: activeEngine,
      model: payload.model || getSelectedModelName(),
      activePresetId: payload.active_preset_id || '',
      presets: Array.isArray(payload.presets) ? payload.presets : []
    };

    $ollamaPresetSelector.empty();
    ollamaPresetState.presets.forEach(function (preset) {
      const label = preset.is_default ? `${preset.name} (Default)` : preset.name;
      const $option = $('<option>').val(preset.id).text(label);
      if (preset.id === ollamaPresetState.activePresetId) {
        $option.prop('selected', true);
      }
      $ollamaPresetSelector.append($option);
    });

    const activePreset = getActiveOllamaPreset();
    const isDefaultPreset = !activePreset || !!activePreset.is_default;
    $ollamaPresetRenameBtn.prop('disabled', isDefaultPreset);
    $ollamaPresetDeleteBtn.prop('disabled', isDefaultPreset);
    $ollamaPresetGroup.show();
  }

  function isPresetCapableEngine(engine) {
    return ['ollama-service', 'lms'].includes(normalizeEngineValue(engine));
  }

  function getPresetApiBase(engine) {
    const normalizedEngine = normalizeEngineValue(engine);
    if (normalizedEngine === 'ollama-service') {
      return '/api/ollama_presets';
    }
    if (normalizedEngine === 'lms') {
      return '/api/lms_presets';
    }
    return '';
  }

  function buildActivePresetConfigPayload() {
    const engine = getActiveEngine();
    if (engine === 'lms') {
      return {
        load: collectParameterPayload('#group-load .dyn-load-param'),
        operation: collectOptionsPayload()
      };
    }
    return collectOptionsPayload();
  }

  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const errorData = await response.json().catch(function () {
        return {};
      });
      throw new Error(errorData.error || `Request failed: ${response.status}`);
    }

    return response.json();
  }

  async function syncActiveOllamaPreset() {
    const engine = getActiveEngine();
    const presetApiBase = getPresetApiBase(engine);
    if (!presetApiBase) {
      return;
    }

    const modelName = getSelectedModelName();
    if (!modelName) {
      return;
    }

    const payload = await postJson(`${presetApiBase}/sync/`, {
      model: modelName,
      config: buildActivePresetConfigPayload()
    });
    applyOllamaPresetState(payload);
  }

  function scheduleOllamaPresetSync() {
    if (!isPresetCapableEngine(getActiveEngine())) {
      return;
    }

    window.clearTimeout(ollamaPresetSyncTimer);
    ollamaPresetSyncTimer = window.setTimeout(function () {
      syncActiveOllamaPreset().catch(function (error) {
        console.error('Failed to sync Ollama preset:', error);
      });
    }, 220);
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
    async function runFetch() {
      const response = await fetch(`/api/models/?engine=${encodeURIComponent(engine)}`);
      if (!response.ok) {
        throw new Error(`Failed to load models: ${response.status}`);
      }
      const data = await response.json();
      return data.models || [];
    }

    const models = await runFetch();
    if (models.length > 0 || normalizeEngineValue(engine) !== 'ollama-service') {
      return models;
    }

    await new Promise(function (resolve) {
      window.setTimeout(resolve, 1200);
    });
    return runFetch();
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

  async function applyLmsLoadConfigChange() {
    if (getActiveEngine() !== 'lms') {
      return;
    }

    if (currentModelInfo) {
      currentModelInfo.load_defaults = collectParameterPayload('#group-load .dyn-load-param');
    }
    await syncActiveOllamaPreset();
  }

  async function applyEngineSelection(engine, options) {
    const settingsOptions = options || {};
    const normalizedEngine = normalizeEngineValue(engine);
    const selectionVersion = ++engineSelectionVersion;
    modelInfoRequestVersion += 1;
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

  function buildChatTitle(text, hasAttachments) {
    if (text) {
      return text.substring(0, 40) + (text.length > 40 ? '...' : '');
    }
    return hasAttachments ? 'Attachment chat' : 'New Chat';
  }

  const STOP_ICON = '<svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>';
  const SEND_ICON = '<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"></path></svg>';

  function updateSendButtons() {
    if (isChatGenerating) {
      $sendBtn.prop('disabled', false).addClass('stop-btn').html(STOP_ICON).attr('aria-label', 'Stop generation');
      $sendBtnConv.prop('disabled', false).addClass('stop-btn').html(STOP_ICON).attr('aria-label', 'Stop generation');
    } else {
      const hasPendingAttachments = attachmentState.pending.length > 0;
      $sendBtn.removeClass('stop-btn').html(SEND_ICON).attr('aria-label', 'Send Message').prop('disabled', !$chatInput.val().trim() && !hasPendingAttachments);
      $sendBtnConv.removeClass('stop-btn').html(SEND_ICON).attr('aria-label', 'Send Message').prop('disabled', !$chatInputConv.val().trim() && !hasPendingAttachments);
    }
  }

  function updateRegenButtons() {
    // Hide all regen buttons first.
    $messagesInner.find('.msg-regen-btn').hide();

    // Show regen on the very last assistant message.
    const $allMsgs = $messagesInner.find('.msg');
    const $lastAssistant = $messagesInner.find('.msg.assistant').last();
    if ($lastAssistant.length) {
      $lastAssistant.find('.msg-regen-btn').show();

      // Also show regen on the user message right before the last assistant message,
      // but only if that user message is immediately preceding.
      const $prev = $lastAssistant.prev('.msg.user');
      if ($prev.length) {
        $prev.find('.msg-regen-btn').show();
      }
    }
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
    clearPendingAttachments();
    updateSendButtons();
  }

  function updateAttachmentControls() {
    const canAttach = visionState.supported || fileState.supported;
    $('#attachBtn').toggle(canAttach);
    $('#attachBtnConv').toggle(canAttach);
    $('#visionBadge').toggle(visionState.supported);
    $('#visionBadgeConv').toggle(visionState.supported);
  }

  function clearPendingAttachments() {
    attachmentState.pending = [];
    $('#imagePreviewStrip').empty().hide();
    $('#imagePreviewStripConv').empty().hide();
    $('#imageInput').val('');
    $('#imageInputConv').val('');
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
    const base64 = attachment.base64 || attachment.data || (dataUrl ? dataUrl.replace(/^data:[^;]+;base64,/, '') : '');
    return {
      kind: attachment.kind || 'file',
      name: attachment.name || '',
      mimeType: attachment.mimeType || attachment.mime_type || 'application/octet-stream',
      size: attachment.size || attachment.size_bytes || 0,
      base64,
      dataUrl: dataUrl || (base64 ? `data:${attachment.mimeType || attachment.mime_type || 'application/octet-stream'};base64,${base64}` : '')
    };
  }

  function rebuildPreviewStrips() {
    const $strips = $('#imagePreviewStrip, #imagePreviewStripConv');
    $strips.empty();

    if (attachmentState.pending.length === 0) {
      $strips.hide();
      updateSendButtons();
      return;
    }

    attachmentState.pending.forEach(function (attachment, idx) {
      let html = '';
      if (attachment.kind === 'image') {
        html = `
          <div class="img-preview-thumb" data-idx="${idx}">
            <img src="${attachment.dataUrl}" alt="Attached image">
            <button class="img-preview-remove" aria-label="Remove attachment">
              <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>
        `;
      } else {
        html = `
          <div class="file-preview-chip" data-idx="${idx}">
            <div class="file-preview-name">${escHtml(attachment.name || 'File')}</div>
            <div class="file-preview-meta">${escHtml(attachment.mimeType || 'application/octet-stream')}</div>
            <button class="img-preview-remove" aria-label="Remove attachment">
              <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>
        `;
      }
      $strips.append(html);
    });

    $strips.show();
    updateSendButtons();
  }

  function handleFileInput(event) {
    const maxAttachments = 20;
    const files = Array.from(event.target.files || []);
    if (!files.length) {
      return;
    }

    files.forEach(function (file) {
      const isImage = file.type.startsWith('image/');
      if (isImage && !visionState.supported) {
        return;
      }
      if (!isImage && !fileState.supported) {
        return;
      }
      if (attachmentState.pending.length >= maxAttachments) {
        console.warn(`Max ${maxAttachments} attachments allowed`);
        return;
      }

      const reader = new FileReader();
      reader.onload = function (loadEvent) {
        if (attachmentState.pending.length >= maxAttachments) {
          return;
        }

        const dataUrl = loadEvent.target.result;
        const base64 = dataUrl.split(',')[1];
        attachmentState.pending.push({
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

  function deleteNestedValue(target, path) {
    const parts = String(path || '').split('.').filter(Boolean);
    if (!parts.length || !target || typeof target !== 'object') {
      return;
    }

    const trail = [];
    let cursor = target;

    for (let index = 0; index < parts.length - 1; index += 1) {
      const part = parts[index];
      if (!cursor || typeof cursor !== 'object' || !(part in cursor)) {
        return;
      }
      trail.push({ parent: cursor, key: part });
      cursor = cursor[part];
    }

    if (!cursor || typeof cursor !== 'object') {
      return;
    }

    delete cursor[parts[parts.length - 1]];

    for (let index = trail.length - 1; index >= 0; index -= 1) {
      const entry = trail[index];
      const child = entry.parent[entry.key];
      if (child && typeof child === 'object' && !Array.isArray(child) && Object.keys(child).length === 0) {
        delete entry.parent[entry.key];
      } else {
        break;
      }
    }
  }

  function flattenConfigLeaves(source, prefix) {
    if (!source || typeof source !== 'object' || Array.isArray(source)) {
      return prefix ? [{ path: prefix, value: source }] : [];
    }

    return Object.entries(source).flatMap(function ([key, value]) {
      const nextPath = prefix ? `${prefix}.${key}` : key;
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        return flattenConfigLeaves(value, nextPath);
      }
      return [{ path: nextPath, value }];
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
      const labels = config.options.map(function (option) {
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
        ${metaItems.map(function (item) {
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

    return allowedValues.reduce(function (closest, candidate) {
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
            ${(config.options || []).map(function (option) {
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

  function renderExperimentalLoadParameter(path, value) {
    const leafKey = String(path || '').split('.').filter(Boolean).pop() || String(path || 'value');
    const parameterKey = `load_${String(path || '').replace(/[^a-zA-Z0-9]+/g, '_')}`;
    const inferredType = inferExperimentalParameterType(leafKey, value);
    const valueType = inferredType === 'boolean' ? 'boolean' : inferredType === 'json' ? 'json' : inferredType;
    let controlHtml = '';

    if (valueType === 'boolean') {
      controlHtml = `
        <select
          class="model-selector setting-select dyn-load-param"
          id="dyn_${parameterKey}"
          data-param="${parameterKey}"
          data-param-path="${path}"
          data-value-type="boolean">
          <option value="true"${value ? ' selected' : ''}>True</option>
          <option value="false"${!value ? ' selected' : ''}>False</option>
        </select>
      `;
    } else if (valueType === 'json') {
      controlHtml = `
        <textarea
          class="setting-textarea dyn-load-param"
          id="dyn_${parameterKey}"
          data-param="${parameterKey}"
          data-param-path="${path}"
          data-value-type="json"
          rows="4">${escapeTextareaValue(JSON.stringify(value, null, 2))}</textarea>
      `;
    } else {
      const inputType = valueType === 'string' ? 'text' : 'number';
      controlHtml = `
        <input
          type="${inputType}"
          class="setting-input dyn-load-param"
          id="dyn_${parameterKey}"
          data-param="${parameterKey}"
          data-param-path="${path}"
          data-value-type="${valueType === 'integer' ? 'integer' : valueType === 'number' ? 'number' : 'string'}"
          value="${escapeAttributeValue(String(value ?? ''))}">
      `;
    }

    $('#group-load .settings-section-content').append(`
      <div class="setting-group">
        <label class="setting-label" for="dyn_${parameterKey}">
          ${formatExperimentalParameterLabel(path)}
        </label>
        ${controlHtml}
      </div>
    `);
    $('#group-load').show();
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
    const loadConfig = (currentModelInfo && currentModelInfo.load_defaults) || runtimeSettings.lms_load_config || {};
    const selectedMainModel = $modelSelector.val() || '';
    const lmsModels = getAvailableModelsForEngine('lms');

    $content.empty();
    $group.hide();

    if (engine !== 'lms') {
      return;
    }

    const remainingLoadConfig = JSON.parse(JSON.stringify(loadConfig || {}));

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
      deleteNestedValue(remainingLoadConfig, config.path || key);
    });

    flattenConfigLeaves(remainingLoadConfig, '').forEach(function (entry) {
      if (entry.value === undefined || entry.value === null) {
        return;
      }
      renderExperimentalLoadParameter(entry.path, entry.value);
    });
  }

  function renderThinkLevelControls() {
    const normalizedOptions = Array.isArray(thinkState.levelOptions) && thinkState.levelOptions.length > 0
      ? thinkState.levelOptions
      : ['low', 'medium', 'high'];

    ['#thinkLevelSelector', '#thinkLevelSelectorConv'].forEach(function (selectorId) {
      const $selector = $(selectorId);
      $selector.empty();

      normalizedOptions.forEach(function (optionValue) {
        const normalizedValue = String(optionValue || '').trim();
        if (!normalizedValue) {
          return;
        }

        const label = normalizedValue
          .replace(/[_-]+/g, ' ')
          .replace(/\b\w/g, function (letter) {
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
      { $toggle: $('#thinkToggleBtn'), $selector: $('#thinkLevelSelector') },
      { $toggle: $('#thinkToggleBtnConv'), $selector: $('#thinkLevelSelectorConv') }
    ].forEach(function (pair) {
      if (!thinkState.supported) {
        pair.$toggle.hide();
        pair.$selector.hide();
        return;
      }

      pair.$toggle.toggle(thinkState.toggleSupported && !thinkState.levelSupported);
      pair.$toggle.toggleClass('active', thinkState.enabled);

      if (thinkState.levelSupported) {
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
    const requestedEngine = getActiveEngine();
    const requestVersion = ++modelInfoRequestVersion;

    if (!model) {
      currentModelInfo = null;
      resetOllamaPresetUi();
      resetDynamicPanels();
      renderLoadParameters();
      updateVisibleDividers();
      visionState.supported = false;
      fileState.supported = false;
      thinkState.supported = false;
      thinkState.toggleSupported = false;
      thinkState.levelSupported = false;
      thinkState.levelOptions = ['low', 'medium', 'high'];
      toolState.supported = false;
      selectedToolServerIds = new Set();
      updateAvailableToolServers(defaultAvailableToolServers);
      updateAttachmentControls();
      updateThinkControls();
      renderToolControls();
      return;
    }

    try {
      const response = await fetch(`/api/model_info/?engine=${encodeURIComponent(requestedEngine)}&model=${encodeURIComponent(model)}`);
      if (!response.ok) {
        throw new Error(`Failed to load model info: ${response.status}`);
      }

      if (requestVersion !== modelInfoRequestVersion || requestedEngine !== getActiveEngine() || model !== getSelectedModelName()) {
        return;
      }

      const data = await response.json();
      currentModelInfo = data;
      resetDynamicPanels();
      applyOllamaPresetState(data.ollama_presets || data.lms_presets || null);
      renderLoadParameters();

      toolState.supported = !!data.supports_tool_calling;
      updateAvailableToolServers(data.available_tool_servers || defaultAvailableToolServers);
      if (!toolState.supported) {
        selectedToolServerIds = new Set();
      }
      renderToolControls();

      visionState.supported = !!data.supports_vision;
      fileState.supported = !!data.supports_files;
      updateAttachmentControls();
      clearPendingAttachments();

      thinkState.supported = !!data.supports_thinking;
      thinkState.paramName = data.think_param_name || 'think';
      thinkState.toggleSupported = data.supports_think_toggle === undefined
        ? !!data.supports_thinking
        : !!data.supports_think_toggle;
      thinkState.levelSupported = !!data.supports_think_level;
      thinkState.levelParamName = data.think_level_param_name || 'think_level';
      thinkState.levelOptions = Array.isArray(data.think_level_options) && data.think_level_options.length > 0
        ? data.think_level_options.map(function (value) { return String(value); })
        : ['low', 'medium', 'high'];
      thinkState.enabled = data.defaults && data.defaults[thinkState.paramName] !== undefined
        ? String(data.defaults[thinkState.paramName]).toLowerCase() === 'true' || data.defaults[thinkState.paramName] === true
        : true;
      thinkState.level = data.defaults && data.defaults[thinkState.levelParamName] !== undefined
        ? String(data.defaults[thinkState.levelParamName])
        : (thinkState.levelOptions[0] || 'medium');
      renderThinkLevelControls();
      updateThinkControls();

      if (!data.defaults) {
        updateVisibleDividers();
        return;
      }

      const defaults = { ...data.defaults };
      delete defaults[thinkState.paramName];
      delete defaults[thinkState.levelParamName];
      if (getActiveEngine() === 'ollama-service') {
        OLLAMA_UNSUPPORTED_RUNTIME_PARAMS.forEach(function (key) {
          delete defaults[key];
        });
      }

      getSupportedParameterDefinitions(getActiveEngine()).forEach(function ([key, config]) {
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
        if (key === 'num_gpu' && runtimeLimits.model_layers) {
          renderedConfig.max = runtimeLimits.model_layers;
          renderedConfig.note = `GPU layers. Model layers: ${runtimeLimits.model_layers}.`;
        }
        if (key === 'main_gpu') {
          const gpuDevices = Array.isArray(runtimeLimits.gpu_devices) ? runtimeLimits.gpu_devices : [];
          renderedConfig.options = [{ value: '', label: 'Automatic' }].concat(
            gpuDevices.map(function (device) {
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
      if (requestVersion !== modelInfoRequestVersion) {
        return;
      }
      currentModelInfo = null;
      resetOllamaPresetUi();
      resetDynamicPanels();
      renderLoadParameters();
      updateVisibleDividers();
      updateAvailableToolServers(defaultAvailableToolServers);
      visionState.supported = false;
      fileState.supported = false;
      thinkState.supported = false;
      thinkState.toggleSupported = false;
      thinkState.levelSupported = false;
      thinkState.levelOptions = ['low', 'medium', 'high'];
      toolState.supported = false;
      renderThinkLevelControls();
      updateAttachmentControls();
      updateThinkControls();
      renderToolControls();
      console.error('Failed to load model parameters', error);
    }
  }

  function collectParameterPayload(selector) {
    const payload = {};
    $(selector).each(function () {
      const param = $(this).data('param');
      const paramPath = $(this).data('paramPath') || param;
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
    if (getActiveEngine() === 'ollama-service') {
      OLLAMA_UNSUPPORTED_RUNTIME_PARAMS.forEach(function (key) {
        delete payload[key];
      });
    }

    if (thinkState.supported && thinkState.toggleSupported && !thinkState.levelSupported) {
      payload[thinkState.paramName] = thinkState.enabled;
    }
    if (thinkState.supported && thinkState.levelSupported) {
      payload[thinkState.levelParamName] = thinkState.level;
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

  function openToolInspector(seg) {
    const $modal = $('#toolInspectorModal');
    $modal.find('.tool-inspector-title').text(seg.toolName || seg.alias || seg.toolId || 'Tool');
    $modal.find('.tool-inspector-server').text(seg.serverName || seg.serverId || '');

    const argsText = Object.keys(seg.arguments || {}).length > 0
      ? JSON.stringify(seg.arguments, null, 2)
      : '(no arguments)';
    $modal.find('.tool-inspector-in').text(argsText);

    const resultText = seg.result !== null && seg.result !== undefined
      ? String(seg.result)
      : '(pending)';
    $modal.find('.tool-inspector-out').text(resultText);

    $modal.addClass('open');
  }

  function parseMessageTimeline(rawText) {
    const source = String(rawText || '');
    const segments = [];
    const toolSegmentByAlias = {};
    let cursor = 0;

    function sanitizeVisibleText(value) {
      return String(value || '')
        .replace(/<\|start\|>\s*(assistant|user|system)?\s*(<\|channel\|>\s*(final|analysis|commentary))?\s*(<\|message\|>)?/gi, '')
        .replace(/<\|start\|>/gi, '')
        .replace(/<\|channel\|>\s*(final|analysis|commentary)/gi, '')
        .replace(/<\|message\|>/gi, '')
        .replace(/<\|return\|>/gi, '')
        .replace(/<\|startoftext\|>/gi, '')
        .replace(/<\|im_(start|end)\|>/gi, '')
        .replace(/<\|(assistant|user|system|endoftext)\|>/gi, '');
    }

    function pushTextSegment(value) {
      const sanitizedValue = sanitizeVisibleText(value);
      if (!sanitizedValue || !sanitizedValue.trim()) {
        return;
      }
      segments.push({ type: 'text', content: sanitizedValue });
    }

    while (cursor < source.length) {
      const thinkStart = source.indexOf('<think>', cursor);
      const toolCallStart = source.indexOf('<tool_call>', cursor);
      const toolResultStart = source.indexOf('<tool_result>', cursor);

      const candidates = [
        thinkStart !== -1 ? { pos: thinkStart, kind: 'thought' } : null,
        toolCallStart !== -1 ? { pos: toolCallStart, kind: 'tool' } : null,
        toolResultStart !== -1 ? { pos: toolResultStart, kind: 'result' } : null,
      ].filter(Boolean);

      if (candidates.length === 0) {
        pushTextSegment(source.substring(cursor));
        break;
      }

      candidates.sort(function (a, b) { return a.pos - b.pos; });
      const next = candidates[0];

      if (next.pos > cursor) {
        pushTextSegment(source.substring(cursor, next.pos));
      }

      if (next.kind === 'thought') {
        const thinkEnd = source.indexOf('</think>', next.pos + 7);
        if (thinkEnd === -1) {
          const content = sanitizeVisibleText(source.substring(next.pos + 7)).trim();
          if (content) {
            segments.push({ type: 'thought', content });
          }
          break;
        }
        const content = sanitizeVisibleText(source.substring(next.pos + 7, thinkEnd)).trim();
        if (content) {
          segments.push({ type: 'thought', content });
        }
        cursor = thinkEnd + 8;
        continue;
      }

      if (next.kind === 'tool') {
        const toolEnd = source.indexOf('</tool_call>', next.pos + 11);
        if (toolEnd === -1) { break; }
        const payload = source.substring(next.pos + 11, toolEnd);
        try {
          const parsed = JSON.parse(payload);
          const alias = String(parsed.alias || '').trim();
          const seg = {
            type: 'tool',
            alias,
            serverId: String(parsed.server_id || '').trim(),
            serverName: String(parsed.server_name || '').trim(),
            toolId: String(parsed.tool_id || '').trim(),
            toolName: String(parsed.tool_name || '').trim(),
            arguments: parsed.arguments && typeof parsed.arguments === 'object' ? parsed.arguments : {},
            result: null,
          };
          segments.push(seg);
          if (alias) { toolSegmentByAlias[alias] = seg; }
        } catch (_error) {
          // Ignore malformed markers.
        }
        cursor = toolEnd + 12;
        continue;
      }

      if (next.kind === 'result') {
        const resultEnd = source.indexOf('</tool_result>', next.pos + 13);
        if (resultEnd === -1) { break; }
        const payload = source.substring(next.pos + 13, resultEnd);
        try {
          const parsed = JSON.parse(payload);
          const alias = String(parsed.alias || '').trim();
          const content = String(parsed.content || '');
          const target = toolSegmentByAlias[alias];
          if (target) {
            target.result = content;
          }
        } catch (_error) {
          // Ignore malformed markers.
        }
        cursor = resultEnd + 14;
        continue;
      }
    }

    const visibleText = segments
      .filter(function (segment) { return segment.type === 'text'; })
      .map(function (segment) { return segment.content; })
      .join('\n\n')
      .trim();

    return { segments, visibleText };
  }

  function renderMarkdownSegment(content) {
    if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
      return escHtml(content);
    }
    return DOMPurify.sanitize(marked.parse(content));
  }

  function getExpandedThoughtIndices($msgRow) {
    const rawValue = String($msgRow.attr('data-expanded-thoughts') || '').trim();
    if (!rawValue) {
      return new Set();
    }

    return new Set(
      rawValue
        .split(',')
        .map(function (value) { return parseInt(value, 10); })
        .filter(function (value) { return Number.isInteger(value) && value >= 0; })
    );
  }

  function setExpandedThoughtIndices($msgRow, expandedIndices) {
    const normalized = Array.from(expandedIndices)
      .filter(function (value) { return Number.isInteger(value) && value >= 0; })
      .sort(function (left, right) { return left - right; });

    if (normalized.length === 0) {
      $msgRow.removeAttr('data-expanded-thoughts');
      return;
    }

    $msgRow.attr('data-expanded-thoughts', normalized.join(','));
  }

  function renderActivityTimeline($msgRow, segments) {
    const $stream = $msgRow.find('.msg-activity-stream');
    const $bubble = $msgRow.find('.msg-bubble');
    if (!$stream.length) {
      return;
    }

    if (!Array.isArray(segments) || segments.length === 0) {
      $stream.hide().empty();
      $bubble.html('');
      $msgRow.removeAttr('data-expanded-thoughts');
      return;
    }

    const expandedThoughts = getExpandedThoughtIndices($msgRow);
    let thoughtIndex = -1;
    let toolSegmentIndex = 0;
    const toolSegments = segments.filter(function (s) { return s.type === 'tool'; });
    const html = segments.map(function (segment) {
      if (segment.type === 'thought') {
        thoughtIndex += 1;
        const isExpanded = expandedThoughts.has(thoughtIndex);
        return `
          <div class="msg-thoughts-wrapper${isExpanded ? ' expanded' : ''}" data-thought-index="${thoughtIndex}">
            <div class="msg-thoughts-toggle">Thought Process</div>
            <div class="msg-thoughts-content" style="display:${isExpanded ? 'block' : 'none'};">${escHtml(segment.content)}</div>
          </div>
        `;
      }

      if (segment.type === 'tool') {
        const label = escHtml(segment.toolName || segment.alias || segment.toolId || 'Tool');
        const badge = escHtml(segment.serverName || segment.serverId || 'server');
        const hasResult = segment.result !== null && segment.result !== undefined;
        const statusDot = hasResult
          ? '<span class="msg-tool-call-dot msg-tool-call-dot--done"></span>'
          : '<span class="msg-tool-call-dot msg-tool-call-dot--pending"></span>';

        return `
          <div class="msg-tool-call-card" data-tool-segment-index="${toolSegmentIndex++}">
            <div class="msg-tool-call-main">
              ${statusDot}
              <div class="msg-tool-call-name">${label}</div>
            </div>
            <div class="msg-tool-call-badge">${badge}</div>
          </div>
        `;
      }

      return `
        <div class="msg-stream-text">
          <div class="markdown-body">${renderMarkdownSegment(segment.content)}</div>
        </div>
      `;
    }).join('');

    $bubble.empty();
    $stream.html(html).show();
    setExpandedThoughtIndices($msgRow, expandedThoughts);

    $stream.find('.msg-tool-call-card[data-tool-segment-index]').each(function () {
      const idx = parseInt($(this).attr('data-tool-segment-index'), 10);
      const seg = toolSegments[idx];
      if (!seg) { return; }
      $(this).on('click', function () {
        openToolInspector(seg);
      });
    });
  }

  function renderMessageHtml($msgRow, rawText) {
    const parsed = parseMessageTimeline(rawText);
    renderActivityTimeline($msgRow, parsed.segments);
    $msgRow.find('.msg-bubble').attr('data-raw', rawText).attr('data-copy', parsed.visibleText);
  }

  function appendMessage(role, text, attachments, timestamp, options) {
    const viewOptions = options || {};
    const isUser = role === 'user';
    const label = isUser ? 'You' : 'ASLM';
    const timeStr = timeNow(timestamp);
    const queuedBadge = isUser && viewOptions.queued
      ? '<span class="msg-status-pill">Queued</span>'
      : '';
    const messageKey = viewOptions.messageKey || '';

    let attachmentsHtml = '';
    if (isUser && attachments && attachments.length > 0) {
      const imageHtml = attachments
        .filter(function (attachment) {
          return typeof attachment === 'string' || attachment.kind === 'image';
        })
        .map(function (attachment) {
          const normalizedAttachment = normalizeAttachment(attachment);
          const src = normalizedAttachment ? normalizedAttachment.dataUrl : '';
          return `<img src="${src}" alt="Attached image">`;
        }).join('');
      const fileHtml = attachments
        .filter(function (attachment) {
          return typeof attachment !== 'string' && attachment.kind === 'file';
        })
        .map(function (attachment) {
          return `
            <div class="msg-file-chip">
              <div class="msg-file-name">${escHtml(attachment.name || 'File')}</div>
              <div class="msg-file-meta">${escHtml(attachment.mimeType || attachment.mime_type || 'application/octet-stream')}</div>
            </div>
          `;
        }).join('');
      attachmentsHtml = `
        ${imageHtml ? `<div class="msg-images">${imageHtml}</div>` : ''}
        ${fileHtml ? `<div class="msg-files">${fileHtml}</div>` : ''}
      `;
    }

    const messageId = viewOptions.messageId || '';
    const copyBtn = `<button class="msg-action-btn msg-copy-btn" title="Copy" aria-label="Copy message">
          <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
        </button>`;
    const regenBtn = `<button class="msg-action-btn msg-regen-btn" title="Regenerate" aria-label="Regenerate response">
          <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 .49-3"/></svg>
        </button>`;
    const deleteBtn = `<button class="msg-action-btn msg-delete-btn" title="Delete" aria-label="Delete message">
          <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>
        </button>`;
    const msgActionsHtml = isUser
      ? `<div class="msg-actions">${copyBtn}${regenBtn}${deleteBtn}</div>`
      : `<div class="msg-actions">${copyBtn}${regenBtn}${deleteBtn}</div>`;

    const $row = $(`
      <div class="msg ${role}${viewOptions.queued ? ' is-queued' : ''}" data-message-key="${escapeAttributeValue(messageKey)}"${messageId ? ` data-message-id="${messageId}"` : ''}>
        <div class="msg-avatar">${isUser ? 'U' : 'A'}</div>
        <div class="msg-body">
          <div class="msg-meta">
            <span>${label}</span>
            <span>${timeStr}</span>
            ${queuedBadge}
          </div>
          ${!isUser ? '<div class="msg-activity-stream" style="display:none;"></div>' : ''}
          <div class="msg-bubble">${attachmentsHtml}</div>
          ${msgActionsHtml}
        </div>
      </div>
    `);

    if (isUser) {
      $row.find('.msg-bubble')
        .attr('data-raw', text)
        .attr('data-attachments', JSON.stringify(attachments || []))
        .append($('<span>').text(text));
    } else if (Array.isArray(viewOptions.activitySegments) && viewOptions.activitySegments.length > 0) {
      $row.find('.msg-bubble').attr('data-raw', text);
      renderActivityTimeline($row, viewOptions.activitySegments);
    } else {
      renderMessageHtml($row, text);
    }

    $messagesInner.append($row);
    updateRegenButtons();
    scrollBottom();
    return $row;
  }


  function setQueuedMessageState($row, queued) {
    if (!$row || !$row.length) {
      return;
    }

    $row.toggleClass('is-queued', !!queued);
    const $meta = $row.find('.msg-meta');
    let $badge = $meta.find('.msg-status-pill');

    if (queued) {
      if (!$badge.length) {
        $badge = $('<span class="msg-status-pill">Queued</span>');
        $meta.append($badge);
      }
    } else {
      $badge.remove();
    }
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
          <div class="msg-activity-stream" style="display:none;"></div>
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

  function clonePendingAttachments(attachments) {
    return (attachments || [])
      .map(normalizeAttachment)
      .filter(Boolean);
  }

  async function resolveModelForRequest(request) {
    const preferredModel = String(request.model || request.preferredModel || '').trim();
    if (preferredModel) {
      return preferredModel;
    }

    if (Array.isArray(modelsCache[request.engine]) && modelsCache[request.engine].length > 0) {
      return modelsCache[request.engine][0] || '';
    }

    const models = await fetchModelsForEngine(request.engine);
    modelsCache[request.engine] = models;
    return models[0] || '';
  }

  async function streamChat(request, $msgRow) {
    const $bubbleContent = $msgRow.find('.msg-bubble');

    try {
      const selectedModel = await resolveModelForRequest(request);
      if (!selectedModel) {
        throw new Error(`No models available for ${request.engine}`);
      }

      request.model = selectedModel;

      const payload = {
        engine: request.engine,
        message: request.text,
        model: selectedModel,
        system_prompt: request.systemPrompt,
        chat_id: request.chatId || currentChatId,
        options: request.options || {}
      };

      if (request.toolServerIds && request.toolServerIds.length > 0) {
        payload.tool_server_ids = request.toolServerIds;
      }

      if (request.attachments.length > 0) {
        payload.attachments = request.attachments.map(function (attachment) {
          return {
            kind: attachment.kind,
            name: attachment.name,
            mime_type: attachment.mimeType,
            size_bytes: attachment.size,
            data: attachment.base64
          };
        });
      }

      currentAbortController = new AbortController();
      const response = await fetch('/api/chat/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify(payload),
        signal: currentAbortController.signal
      });

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
        request.chatId = returnedChatId;
        chatRequestQueue.forEach(function (queuedRequest) {
          if (!queuedRequest.chatId) {
            queuedRequest.chatId = returnedChatId;
          }
        });

        if ($(`#historyList .chat-item[data-chat-id="${currentChatId}"]`).length === 0) {
          $('#historyList .empty-state').remove();

          const title = buildChatTitle(request.text, request.attachments.length > 0);
          const $newItem = $(buildChatItemHtml(currentChatId, title, 'just now', true));

          $('#historyList .chat-item').removeClass('active').removeAttr('aria-current');
          $('#historyList').prepend($newItem);
        }

        const chatTitle = buildChatTitle(request.text, request.attachments.length > 0);
        $chatTitle.text(chatTitle);
        document.title = `${chatTitle} - ASLM`;
        history.pushState({ chatId: currentChatId }, chatTitle, `/chat/${currentChatId}/`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let fullText = '';
      const signal = currentAbortController ? currentAbortController.signal : null;

      // Wrap reader.read() so it rejects immediately when the signal fires.
      function readOrAbort() {
        if (!signal) { return reader.read(); }
        if (signal.aborted) { return Promise.reject(new DOMException('Aborted', 'AbortError')); }
        return Promise.race([
          reader.read(),
          new Promise(function (_, reject) {
            signal.addEventListener('abort', function () {
              reject(new DOMException('Aborted', 'AbortError'));
            }, { once: true });
          })
        ]);
      }

      try {
        while (true) {
          const { done, value } = await readOrAbort();
          if (done) { break; }

          const chunk = decoder.decode(value, { stream: true });
          fullText += chunk;

          const area = $messagesArea[0];
          const isNearBottom = area.scrollHeight - area.clientHeight <= area.scrollTop + 50;
          renderMessageHtml($msgRow, fullText);

          if (isNearBottom) { scrollBottom(); }
        }
      } catch (readError) {
        if (readError.name !== 'AbortError') { throw readError; }
      } finally {
        reader.cancel();
        reader.releaseLock();
      }
    } catch (error) {
      if (error.name !== 'AbortError') {
        $bubbleContent.html(`[Error: failed to connect to server - ${error.message}]`);
      }
    } finally {
      currentAbortController = null;
    }
  }

  async function processChatQueue() {
    if (isChatGenerating || chatRequestQueue.length === 0) {
      return;
    }

    const request = chatRequestQueue.shift();
    if (!request) {
      return;
    }

    isChatGenerating = true;
    setQueuedMessageState(request.$userRow, false);
    updateSendButtons();

    const $assistantRow = appendTyping();
    scrollBottom();

    try {
      await streamChat(request, $assistantRow);
    } finally {
      // Inject action panel if not already present (streaming msg didn't have it)
      if ($assistantRow.find('.msg-actions').length === 0) {
        $assistantRow.find('.msg-body').append(`
          <div class="msg-actions">
            <button class="msg-action-btn msg-copy-btn" title="Copy" aria-label="Copy message">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
            </button>
            <button class="msg-action-btn msg-regen-btn" title="Regenerate" aria-label="Regenerate response">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 .49-3"/></svg>
            </button>
            <button class="msg-action-btn msg-delete-btn" title="Delete" aria-label="Delete message">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>
            </button>
          </div>`);
      }
      updateRegenButtons();
      isChatGenerating = false;
      updateSendButtons();
      if (chatRequestQueue.length > 0) {
        processChatQueue();
      }
    }
  }

  function buildQueuedRequest(text, attachmentsToSend) {
    return {
      id: `queued-${++queuedMessageCounter}`,
      text,
      attachments: clonePendingAttachments(attachmentsToSend),
      engine: getActiveEngine(),
      preferredModel: getSelectedModelName(),
      systemPrompt: $('#systemPrompt').val(),
      options: collectOptionsPayload(),
      toolServerIds: toolState.supported ? Array.from(selectedToolServerIds) : [],
      chatId: currentChatId
    };
  }

  function sendMessage(text, $input) {
    if (!text && attachmentState.pending.length === 0) {
      return;
    }

    const attachmentsToSend = clonePendingAttachments(attachmentState.pending);
    const queued = isChatGenerating || chatRequestQueue.length > 0;

    if ($welcomeScreen.is(':visible')) {
      $welcomeScreen.hide();
      $conversationInput.show();
      $chatInputConv.val('').css('height', 'auto').focus();
    }

    const request = buildQueuedRequest(text, attachmentsToSend);
    request.$userRow = appendMessage('user', text, attachmentsToSend, null, {
      queued,
      messageKey: request.id
    });

    $input.val('').css('height', 'auto');
    clearPendingAttachments();
    updateSendButtons();

    chatRequestQueue.push(request);
    processChatQueue();
  }

  function buildChatItemHtml(chatId, title, dateStr, active) {
    const activeAttr = active ? ' class="chat-item active" aria-current="page"' : ' class="chat-item"';
    return `
      <a${activeAttr} href="/chat/${chatId}/" data-chat-id="${escapeAttributeValue(chatId)}">
        <div class="chat-item-icon">
          <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
          </svg>
        </div>
        <div class="chat-item-body">
          <span class="chat-item-title">${escHtml(title)}</span>
          <span class="chat-item-date">${escHtml(dateStr)}</span>
        </div>
        <button class="chat-item-menu-btn" aria-label="Chat options">
          <svg width="14" height="14" fill="currentColor" viewBox="0 0 24 24">
            <circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="19" r="1.5"/>
          </svg>
        </button>
      </a>
    `;
  }

  // Chat item context menu
  let $activeMenuTarget = null;
  const $dropdown = $('#chatItemDropdown');

  function openChatMenu($item, event) {
    event.preventDefault();
    event.stopPropagation();

    $activeMenuTarget = $item;
    const rect = $item[0].getBoundingClientRect();
    $dropdown.css({
      top: rect.bottom + window.scrollY + 2,
      left: rect.left + window.scrollX,
      minWidth: rect.width,
    }).show();
  }

  function closeChatMenu() {
    $dropdown.hide();
    $activeMenuTarget = null;
  }

  $(document).on('click', function (e) {
    if (!$(e.target).closest('#chatItemDropdown, .chat-item-menu-btn').length) {
      closeChatMenu();
    }
  });

  $(document).on('click', '.chat-item-menu-btn', function (event) {
    const $item = $(this).closest('.chat-item');
    if ($activeMenuTarget && $activeMenuTarget.is($item)) {
      closeChatMenu();
    } else {
      openChatMenu($item, event);
    }
  });

  $('#chatRenameBtn').on('click', function () {
    if (!$activeMenuTarget) { return; }
    const $item = $activeMenuTarget;
    const chatId = $item.data('chat-id');
    const currentTitle = $item.find('.chat-item-title').text();
    closeChatMenu();

    const newTitle = window.prompt('Rename chat:', currentTitle);
    if (!newTitle || !newTitle.trim() || newTitle.trim() === currentTitle) { return; }

    $.ajax({
      url: `/api/chat/${chatId}/rename/`,
      method: 'PATCH',
      contentType: 'application/json',
      headers: { 'X-CSRFToken': getCsrfToken() },
      data: JSON.stringify({ title: newTitle.trim() }),
      success: function (data) {
        if (!data.ok) { return; }
        $item.find('.chat-item-title').text(data.title);
        if (chatId === currentChatId) {
          $chatTitle.text(data.title);
          document.title = `${data.title} - ASLM`;
        }
      }
    });
  });

  $('#chatDeleteBtn').on('click', function () {
    if (!$activeMenuTarget) { return; }
    const $item = $activeMenuTarget;
    const chatId = $item.data('chat-id');
    const title = $item.find('.chat-item-title').text();
    closeChatMenu();

    if (!window.confirm(`Delete "${title}"?`)) { return; }

    $.ajax({
      url: `/api/chat/${chatId}/delete/`,
      method: 'DELETE',
      headers: { 'X-CSRFToken': getCsrfToken() },
      success: function (data) {
        if (!data.ok) { return; }
        $item.remove();
        if (!$('#historyList .chat-item:not(.empty-state)').length) {
          $('#historyList').append('<div class="chat-item empty-state"><span class="chat-item-title">No previous chats</span></div>');
        }
        if (chatId === currentChatId) {
          startNewChat();
        }
      }
    });
  });

  function abortGeneration() {
    if (currentAbortController) {
      currentAbortController.abort();
    }
    isChatGenerating = false;
    updateSendButtons();
    // Tell the backend to stop Ollama immediately.
    fetch('/api/chat/abort/', {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrfToken() }
    }).catch(function () {});
  }

  function doRegenerate() {
    if (!currentChatId) { return; }

    $.ajax({
      url: `/api/chat/${currentChatId}/last/`,
      method: 'DELETE',
      contentType: 'application/json',
      headers: { 'X-CSRFToken': getCsrfToken() },
      success: function (data) {
        if (!data.ok) { return; }

        // Remove last assistant bubble from DOM.
        const $msgs = $messagesInner.find('.msg.assistant');
        if ($msgs.length) { $msgs.last().remove(); }
        updateSendButtons();

        if (!data.user_message) { return; }

        const text = data.user_message.content || '';
        const attachments = (data.user_message.attachments || [])
          .map(normalizeAttachment)
          .filter(Boolean);

        const request = buildQueuedRequest(text, attachments);
        request.$userRow = { length: 0 }; // No new user bubble — message already in DOM.
        request.chatId = currentChatId;

        chatRequestQueue.push(request);
        processChatQueue();
      },
      error: function () {
        console.error('Failed to delete last assistant message');
      }
    });
  }

  function regenerateLastResponse() {
    if (!currentChatId) { return; }
    if (isChatGenerating) {
      // Stop current generation first, then regenerate after backend confirms stop.
      abortGeneration();
      // Small delay to let the stream close before deleting the (partial) message.
      setTimeout(doRegenerate, 300);
    } else {
      doRegenerate();
    }
  }

  function regenerateFromUserMessage($userMsg) {
    if (!currentChatId || isChatGenerating) { return; }

    // Get the user's original text from the bubble data-raw attribute.
    const userText = $userMsg.find('.msg-bubble').attr('data-raw') || $userMsg.find('.msg-bubble').text();
    if (!userText.trim()) { return; }

    // Find the next assistant message (the response to this user message).
    const $nextAssistant = $userMsg.next('.msg.assistant');
    if (!$nextAssistant.length) { return; }

    const assistantMessageId = $nextAssistant.data('message-id');

    function doUserRegen() {
      // Remove assistant message from DOM.
      $nextAssistant.remove();
      updateRegenButtons();

      // Build a new request with the user's original text.
      let userAttachments = [];
      try {
        userAttachments = JSON.parse($userMsg.find('.msg-bubble').attr('data-attachments') || '[]');
      } catch (_error) {
        userAttachments = [];
      }

      const request = buildQueuedRequest(userText, userAttachments);
      request.$userRow = { length: 0 }; // User message already in DOM.
      request.chatId = currentChatId;

      chatRequestQueue.push(request);
      processChatQueue();
    }

    if (assistantMessageId) {
      // Delete the assistant message from backend first.
      $.ajax({
        url: `/api/message/${assistantMessageId}/delete/`,
        method: 'DELETE',
        headers: { 'X-CSRFToken': getCsrfToken() },
        success: function (data) {
          if (data.ok) {
            doUserRegen();
          }
        },
        error: function () {
          console.error('Failed to delete assistant message for regen', assistantMessageId);
        }
      });
    } else {
      doUserRegen();
    }
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
      if (isChatGenerating && currentAbortController) {
        abortGeneration();
        return;
      }
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
        applySelectedToolServerIds(data.active_tool_server_ids || []);
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
          appendMessage(
            message.role,
            message.content,
            (message.attachments || message.images || []).map(normalizeAttachment).filter(Boolean),
            message.created_at,
            {
            activitySegments: Array.isArray(message.activity_segments) ? message.activity_segments : [],
            messageId: message.id
            }
          );
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

  $messagesInner.on('click', '.msg-regen-btn', function () {
    const $msg = $(this).closest('.msg');
    if ($msg.hasClass('user')) {
      // User message regen: delete the next assistant message, then re-send.
      regenerateFromUserMessage($msg);
    } else {
      regenerateLastResponse();
    }
  });

  $messagesInner.on('click', '.msg-copy-btn', function () {
    const $btn = $(this);
    const $bubble = $btn.closest('.msg-body').find('.msg-bubble');
    const text = $bubble.attr('data-copy') || $bubble.attr('data-raw') || $bubble.text();

    function onCopied() {
      const orig = $btn.html();
      $btn.html('<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="20 6 9 12 4 10"/></svg>');
      setTimeout(function () { $btn.html(orig); }, 1200);
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(onCopied).catch(function () {
        fallbackCopy(text, onCopied);
      });
    } else {
      fallbackCopy(text, onCopied);
    }
  });

  function fallbackCopy(text, onSuccess) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;top:-9999px;left:-9999px;opacity:0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try {
      if (document.execCommand('copy')) { onSuccess && onSuccess(); }
    } catch (_) {}
    document.body.removeChild(ta);
  }

  $messagesInner.on('click', '.msg-delete-btn', function () {
    const $msg = $(this).closest('.msg');
    const messageId = $msg.data('message-id');
    if (!messageId) {
      $msg.remove();
      updateRegenButtons();
      return;
    }
    $.ajax({
      url: `/api/message/${messageId}/delete/`,
      method: 'DELETE',
      headers: { 'X-CSRFToken': getCsrfToken() },
      success: function (data) {
        if (data.ok) {
          $msg.remove();
          updateRegenButtons();
        }
      },
      error: function () {
        console.error('Failed to delete message', messageId);
      }
    });
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
    const index = $(this).closest('[data-idx]').data('idx');
    attachmentState.pending.splice(index, 1);
    rebuildPreviewStrips();
  });

  $(document).on('click', '.settings-section-header', function () {
    $(this).parent('.settings-section').toggleClass('collapsed');
  });

  $(document).on('click', '.think-toggle-btn', function () {
    if (!thinkState.supported || !thinkState.toggleSupported || thinkState.levelSupported) {
      return;
    }
    thinkState.enabled = !thinkState.enabled;
    updateThinkControls();
    scheduleOllamaPresetSync();
  });

  $(document).on('click', '.think-level-btn', function () {
    if (!thinkState.supported || !thinkState.levelSupported) {
      return;
    }
    thinkState.level = $(this).data('value');
    updateThinkControls();
    scheduleOllamaPresetSync();
  });

  $(document).on('input', '.setting-range', function () {
    const param = $(this).data('param');
    const decimals = parseInt($(this).data('decimals') || '0', 10);
    const scale = $(this).data('scale');
    if (scale === 'token-range') {
      const allowedValues = JSON.parse($(this).attr('data-allowed-values') || '[]');
      const index = parseInt(this.value, 10);
      const resolvedValue = allowedValues[Math.max(index, 0)] || allowedValues[0] || 0;
      $(`#val_${param}`).val(resolvedValue);
      return;
    }

    $(`#val_${param}`).val(parseFloat(this.value).toFixed(decimals));
  });

  $(document).on('change blur', '.setting-number', function () {
    const param = $(this).data('param');
    const decimals = parseInt($(this).data('decimals') || '0', 10);
    const scale = $(this).data('scale');
    if (scale === 'token-range') {
      const $range = $(`#dyn_${param}`);
      const allowedValues = JSON.parse($range.attr('data-allowed-values') || '[]');
      const resolvedValue = resolveTokenRangeValue(this.value, allowedValues);
      const resolvedIndex = Math.max(allowedValues.indexOf(resolvedValue), 0);

      this.value = String(resolvedValue);
      $range.val(resolvedIndex);
      scheduleOllamaPresetSync();
      return;
    }

    const min = parseFloat(this.min);
    const max = parseFloat(this.max);
    let value = parseFloat(this.value);

    if (Number.isNaN(value)) {
      value = parseFloat($(`#dyn_${param}`).val());
    }

    value = Math.min(max, Math.max(min, value));
    this.value = value.toFixed(decimals);
    $(`#dyn_${param}`).val(value);
    scheduleOllamaPresetSync();
  });

  $(document).on('keydown', '.setting-number', function (event) {
    if (event.key === 'Enter') {
      $(this).trigger('blur');
    }
  });

  $(document).on('change blur', '.dyn-param[data-value-type="optional-number"], .dyn-param[data-value-type="optional-integer"]', function () {
    if ($(this).prop('disabled')) {
      return;
    }

    const rawValue = String($(this).val() || '').trim();
    if (!rawValue) {
      return;
    }

    const decimals = parseInt($(this).data('decimals') || '0', 10);
    const min = parseFloat($(this).attr('min'));
    const max = parseFloat($(this).attr('max'));
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

    $(this).val(decimals === 0 ? String(Math.round(numericValue)) : numericValue.toFixed(decimals));
    scheduleOllamaPresetSync();
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

    scheduleOllamaPresetSync();
  });

  $messagesInner.on('mousedown', '.msg-thoughts-toggle', function (event) {
    event.preventDefault();
    event.stopPropagation();

    const $wrapper = $(this).closest('.msg-thoughts-wrapper');
    const $row = $(this).closest('.msg');
    const $content = $wrapper.find('.msg-thoughts-content');
    const thoughtIndex = parseInt($wrapper.attr('data-thought-index') || '-1', 10);
    const expandedThoughts = getExpandedThoughtIndices($row);
    const willExpand = !$wrapper.hasClass('expanded');

    if (Number.isInteger(thoughtIndex) && thoughtIndex >= 0) {
      if (willExpand) {
        expandedThoughts.add(thoughtIndex);
      } else {
        expandedThoughts.delete(thoughtIndex);
      }
      setExpandedThoughtIndices($row, expandedThoughts);
    }

    $wrapper.toggleClass('expanded', willExpand);
    $content.stop(true, true)[willExpand ? 'slideDown' : 'slideUp'](160);
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

  $ollamaPresetSelector.on('change', async function () {
    const presetId = $(this).val();
    const modelName = getSelectedModelName();
    const presetApiBase = getPresetApiBase(getActiveEngine());
    if (!presetApiBase || !presetId || !modelName) {
      return;
    }

    try {
      const payload = await postJson(`${presetApiBase}/select/`, {
        model: modelName,
        preset_id: presetId
      });
      applyOllamaPresetState(payload);
      await loadModelInfo(modelName);
    } catch (error) {
      console.error('Failed to select Ollama preset:', error);
    }
  });

  $ollamaPresetCreateBtn.on('click', async function () {
    const modelName = getSelectedModelName();
    const presetApiBase = getPresetApiBase(getActiveEngine());
    if (!presetApiBase || !modelName) {
      return;
    }

    const requestedName = window.prompt('Preset name', '');
    if (requestedName === null) {
      return;
    }

    try {
      const payload = await postJson(`${presetApiBase}/create/`, {
        model: modelName,
        name: requestedName.trim(),
        config: buildActivePresetConfigPayload()
      });
      applyOllamaPresetState(payload);
      await loadModelInfo(modelName);
    } catch (error) {
      console.error('Failed to create Ollama preset:', error);
    }
  });

  $ollamaPresetRenameBtn.on('click', async function () {
    const activePreset = getActiveOllamaPreset();
    const modelName = getSelectedModelName();
    const presetApiBase = getPresetApiBase(getActiveEngine());
    if (!presetApiBase || !modelName || !activePreset || activePreset.is_default) {
      return;
    }

    const requestedName = window.prompt('Preset name', activePreset.name || '');
    if (requestedName === null) {
      return;
    }

    try {
      const payload = await postJson(`${presetApiBase}/rename/`, {
        model: modelName,
        preset_id: activePreset.id,
        name: requestedName.trim()
      });
      applyOllamaPresetState(payload);
    } catch (error) {
      console.error('Failed to rename Ollama preset:', error);
    }
  });

  $ollamaPresetDeleteBtn.on('click', async function () {
    const activePreset = getActiveOllamaPreset();
    const modelName = getSelectedModelName();
    const presetApiBase = getPresetApiBase(getActiveEngine());
    if (!presetApiBase || !modelName || !activePreset || activePreset.is_default) {
      return;
    }

    if (!window.confirm(`Delete preset "${activePreset.name}"?`)) {
      return;
    }

    try {
      const payload = await postJson(`${presetApiBase}/delete/`, {
        model: modelName,
        preset_id: activePreset.id
      });
      applyOllamaPresetState(payload);
      await loadModelInfo(modelName);
    } catch (error) {
      console.error('Failed to delete Ollama preset:', error);
    }
  });

  $(document).on('change', '.dyn-param', function () {
    scheduleOllamaPresetSync();
  });

  $(document).on('blur', '.dyn-param', function () {
    if ($(this).is(':checkbox')) {
      return;
    }

    scheduleOllamaPresetSync();
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

  updateAvailableToolServers(defaultAvailableToolServers);
  applySelectedToolServerIds([]);
  updateEngineAddressUi();
  resetModelUiState('Loading models...');
  applyEngineSelection(getActiveEngine(), {
    persist: false
  }).catch(function (error) {
    console.error('Failed to initialize engine state:', error);
  });
});
