// Copyright NGGT.LightKeeper. All Rights Reserved.

// OpenAI-compatible adapter.
export const openAiAdapter = {
  id: 'openai',
  aliases: ['openai', 'openai-api'],
  addressKey: 'openai_url',
  apiKeyKey: 'openai_api_key',
  addressHint: 'Example: http://127.0.0.1:8000/v1',
  supportsPresets: true,
  // Presets are scoped by endpoint URL on the backend so the same model name
  // from different providers keeps independent presets.
  presetApiBase: '/api/openai_presets',

  // Keep preset payloads in the same flat shape as the runtime options.
  buildPresetConfig(options) {
    return { ...(options || {}) };
  }
};
