// Copyright NGGT.LightKeeper. All Rights Reserved.

/** Client-side translations from ``#aslmHostLocaleData`` (see host_locale_bridge). */

let effectiveLocale = 'en';
let isRtlLayout = false;
let messages = {};

const PLACEHOLDER_RE = /\{(\w+)\}/g;

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

/** Load locale bootstrap JSON embedded by Django. */
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

export function getEffectiveLocale() {
  return effectiveLocale;
}

export function isRtl() {
  return isRtlLayout;
}

/**
 * Translate a dot-path key. ``fallback`` is used when the key is missing.
 * ``params`` replaces ``{name}`` placeholders.
 */
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

/** BCP-47 tag for Intl formatters (maps zh-Hans → zh-CN style). */
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
