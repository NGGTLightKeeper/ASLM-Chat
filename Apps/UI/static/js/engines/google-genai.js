// Copyright NEXTGGTECH. Elastic License 2.0.

// Google GenAI adapter.
export const googleGenAiAdapter = {
  id: 'google-genai',
  aliases: ['google-genai', 'google_genai', 'google', 'gemini'],
  // Endpoint is fixed to generativelanguage.googleapis.com, so the address is
  // not user-editable (addressKey null hides the address control).
  addressKey: null,
  apiKeyKey: 'google_genai_api_key',
  // Gemini always needs an API key, so show the key field without an on/off toggle.
  apiKeyRequired: true,
  addressHint: 'Gemini uses generativelanguage.googleapis.com.',
  supportsPresets: true,
  presetApiBase: '/api/google_genai_presets',

  // Keep preset payloads in the same flat shape as the runtime options.
  buildPresetConfig(options) {
    return { ...(options || {}) };
  }
};
