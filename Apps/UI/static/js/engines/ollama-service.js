// Copyright NGGT.LightKeeper. All Rights Reserved.

import { OLLAMA_UNSUPPORTED_RUNTIME_PARAMS } from '../main/constants.js';

function omitUnsupportedKeys(source) {
  const cloned = { ...(source || {}) };
  OLLAMA_UNSUPPORTED_RUNTIME_PARAMS.forEach(function omitKey(key) {
    delete cloned[key];
  });
  return cloned;
}

export const ollamaServiceAdapter = {
  id: 'ollama-service',
  aliases: ['ollama', 'ollama-service'],
  addressKey: null,
  apiKeyKey: null,
  addressHint: 'Ollama uses the local service managed by ASLM.',
  supportsPresets: true,
  presetApiBase: '/api/ollama_presets',
  buildPresetConfig(options) {
    return { ...(options || {}) };
  },
  sanitizeRequestOptions(options) {
    return omitUnsupportedKeys(options);
  },
  sanitizeModelDefaults(defaults) {
    return omitUnsupportedKeys(defaults);
  }
};
