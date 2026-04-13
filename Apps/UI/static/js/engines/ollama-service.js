// Copyright NGGT.LightKeeper. All Rights Reserved.

import { OLLAMA_UNSUPPORTED_RUNTIME_PARAMS } from '../main/constants.js';

// Option helpers.
// Remove runtime keys unsupported by the managed Ollama service.
function omitUnsupportedKeys(source) {
  const cloned = { ...(source || {}) };

  OLLAMA_UNSUPPORTED_RUNTIME_PARAMS.forEach(function omitKey(key) {
    delete cloned[key];
  });

  return cloned;
}


// Ollama service adapter.
export const ollamaServiceAdapter = {
  id: 'ollama-service',
  aliases: ['ollama', 'ollama-service'],
  addressKey: null,
  apiKeyKey: null,
  addressHint: 'Ollama uses the local service managed by ASLM.',
  supportsPresets: true,
  presetApiBase: '/api/ollama_presets',

  // Keep preset payloads in the same flat shape as the runtime options.
  buildPresetConfig(options) {
    return { ...(options || {}) };
  },

  // Remove unsupported request fields before sending them to the runtime.
  sanitizeRequestOptions(options) {
    return omitUnsupportedKeys(options);
  },

  // Remove unsupported default fields before rendering them in the UI.
  sanitizeModelDefaults(defaults) {
    return omitUnsupportedKeys(defaults);
  }
};
