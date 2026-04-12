// Copyright NGGT.LightKeeper. All Rights Reserved.

export const lmsAdapter = {
  id: 'lms',
  aliases: ['lms', 'lm-studio'],
  addressKey: 'lms_url',
  apiKeyKey: null,
  addressHint: 'Example: http://127.0.0.1:1234',
  supportsPresets: true,
  presetApiBase: '/api/lms_presets',
  buildPresetConfig(options) {
    return {
      operation: { ...(options || {}) }
    };
  },
  getModelRefreshInterval(isLocalAddress) {
    return isLocalAddress ? 3000 : 15000;
  }
};
