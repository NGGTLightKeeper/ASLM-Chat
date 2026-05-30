// Copyright NGGT.LightKeeper. All Rights Reserved.

// Client-side translations from #aslmHostLocaleData (see host_locale_bridge).

let effectiveLocale = 'en';
let isRtlLayout = false;
let messages = {};

const PLACEHOLDER_RE = /\{(\w+)\}/g;


// Catalog lookup helpers.
// Resolve one dot-separated key against a nested message catalog.
function lookupNested(catalog, key) {
  const parts = String(key || '').split('.');
  let current = catalog;
  for (const part of parts) {
    if (!current || typeof current !== 'object' || !(part in current)) {
      return null;
    }
    current = current[part];
  }
  return current;
}

// Replace {name} placeholders in one template string.
function interpolate(template, params) {
  if (!params || typeof template !== 'string') {
    return template;
  }
  return template.replace(PLACEHOLDER_RE, function replace(match, name) {
    if (Object.prototype.hasOwnProperty.call(params, name)) {
      return String(params[name]);
    }
    return match;
  });
}


// Locale bootstrap.
// Load locale bootstrap JSON embedded by Django.
export function initI18n() {
  const el = document.getElementById('aslmHostLocaleData');
  if (!el) {
    return;
  }
  try {
    const data = JSON.parse(el.textContent || '{}');
    effectiveLocale = data.effectiveLocale || data.language || 'en';
    isRtlLayout = !!data.isRtl;
    messages = data.messages && typeof data.messages === 'object' ? data.messages : {};
  } catch (_error) {
    effectiveLocale = 'en';
    isRtlLayout = false;
    messages = {};
  }
}

// Read the active locale code chosen by the host bridge.
export function getEffectiveLocale() {
  return effectiveLocale;
}

// Report whether the active locale uses right-to-left layout.
export function isRtl() {
  return isRtlLayout;
}


// Translation API.
// Translate one dot-path key with optional params and fallback text.
export function t(key, params, fallback) {
  let value = lookupNested(messages, key);
  if (value == null && fallback !== undefined) {
    value = fallback;
  }
  if (value == null) {
    return typeof fallback === 'string' ? fallback : key;
  }
  if (typeof value !== 'string') {
    value = String(value);
  }
  return params ? interpolate(value, params) : value;
}

// Build a BCP-47 tag for Intl formatters (maps zh-Hans to zh-CN style).
export function intlLocaleTag() {
  const code = effectiveLocale || 'en';
  if (code === 'zh-Hans') {
    return 'zh-CN';
  }
  if (code === 'zh-Hant') {
    return 'zh-TW';
  }
  return code;
}
