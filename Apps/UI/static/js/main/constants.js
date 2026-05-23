// Copyright NGGT.LightKeeper. All Rights Reserved.

// Ollama-only runtime keys hidden from the managed UI.
export const OLLAMA_UNSUPPORTED_RUNTIME_PARAMS = new Set([
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

// Thinking-related keys handled by dedicated controls.
export const THINK_PARAMETER_KEYS = new Set([
  'think',
  'think_level',
  'thinking',
  'reasoning',
  'thinking_level',
  'reasoning_effort'
]);

// Parameter definitions rendered into the dynamic settings UI.
export const PARAMETER_DEFINITIONS = {
  // Shared parameters.
  temperature: {
    label: 'Temperature',
    type: 'range',
    group: 'settings',
    engines: ['ollama-service', 'lms', 'openai', 'google-genai'],
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
    engines: ['ollama-service', 'openai', 'google-genai'],
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
    engines: ['ollama-service', 'openai', 'google-genai'],
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
    engines: ['ollama-service', 'google-genai'],
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
    engines: ['ollama-service', 'openai', 'google-genai'],
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
    engines: ['ollama-service', 'openai', 'google-genai'],
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

  // LM Studio parameters.
  maxTokens: {
    label: 'Max Output Tokens',
    type: 'range',
    group: 'settings',
    engines: ['lms'],
    min: 1,
    max: 32768,
    step: 32,
    decimals: 0,
    fallback: 4096
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

  // Google GenAI parameters.
  max_output_tokens: {
    label: 'Max Output Tokens',
    type: 'range',
    group: 'settings',
    engines: ['google-genai'],
    min: 1,
    max: 32768,
    step: 32,
    decimals: 0,
    fallback: 8192
  },
  candidate_count: {
    label: 'Candidates',
    type: 'range',
    group: 'advanced',
    engines: ['google-genai'],
    min: 1,
    max: 8,
    step: 1,
    decimals: 0,
    fallback: 1
  },
  stop_sequences: {
    label: 'Stop Sequences',
    type: 'json',
    group: 'advanced',
    engines: ['google-genai'],
    fallback: null
  },
  response_logprobs: {
    label: 'Response Logprobs',
    type: 'boolean',
    group: 'advanced',
    engines: ['google-genai'],
    fallback: false
  },
  response_mime_type: {
    label: 'Response MIME Type',
    type: 'select',
    valueType: 'string',
    group: 'advanced',
    engines: ['google-genai'],
    options: [
      { value: 'text/plain', label: 'Text' },
      { value: 'application/json', label: 'JSON' }
    ],
    fallback: 'text/plain'
  },

  // OpenAI-compatible parameters.
  max_completion_tokens: {
    label: 'Max Completion Tokens',
    type: 'range',
    group: 'settings',
    engines: ['openai'],
    min: 1,
    max: 32768,
    step: 32,
    decimals: 0,
    fallback: 4096
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

// Option sets reused by generic parameter editors.
export const LLM_PARAMETER_OPTION_SETS = {
  reasoning_effort: ['minimal', 'low', 'medium', 'high', 'xhigh'],
  think_level: ['low', 'medium', 'high'],
  thinking_level: ['minimal', 'low', 'medium', 'high'],
  verbosity: ['low', 'medium', 'high']
};
