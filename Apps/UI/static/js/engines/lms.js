// Copyright NGGT.LightKeeper. All Rights Reserved.

// LM Studio adapter.
export const lmsAdapter = {
  id: 'lms',
  aliases: ['lms', 'lm-studio'],
  addressKey: 'lms_url',
  apiKeyKey: null,
  addressHint: 'Example: http://127.0.0.1:1234',
  supportsPresets: true,
  presetApiBase: '/api/lms_presets',

  // Convert the UI options payload into the LM Studio preset schema.
  buildPresetConfig(options) {
    return {
      operation: { ...(options || {}) }
    };
  },

  // Choose a refresh interval based on where LM Studio is hosted.
  getModelRefreshInterval(isLocalAddress) {
    return isLocalAddress ? 3000 : 15000;
  }
};
