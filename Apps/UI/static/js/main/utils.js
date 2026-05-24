// Copyright NGGT.LightKeeper. All Rights Reserved.

import { THINK_PARAMETER_KEYS } from './constants.js';
import { intlLocaleTag } from './i18n.js';

// JSON helpers.
// Parse one JSON payload embedded in a script tag.
export function parseJsonScript(id) {
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


// Parameter helpers.
// Normalize one parameter name into a canonical lookup key.
export function normalizeParameterName(param) {
  return String(param || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

// Report whether a parameter key belongs to thinking controls.
export function isThinkingParameterKey(param) {
  return THINK_PARAMETER_KEYS.has(normalizeParameterName(param));
}


// Address helpers.
// Normalize an address so it can be safely passed to URL().
export function normalizeAddressForParsing(value) {
  const rawValue = String(value || '').trim();

  if (!rawValue) {
    return '';
  }

  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(rawValue)) {
    return rawValue;
  }

  return `http://${rawValue}`;
}

// Report whether a hostname resolves to a local or private network address.
export function isLocalHostname(hostname) {
  const normalizedHost = String(hostname || '')
    .trim()
    .toLowerCase()
    .replace(/^\[|\]$/g, '');

  if (!normalizedHost) {
    return true;
  }

  if (['localhost', '0.0.0.0', '127.0.0.1', '::1'].includes(normalizedHost)) {
    return true;
  }

  if (/^127(?:\.\d{1,3}){3}$/.test(normalizedHost)) {
    return true;
  }

  if (/^10(?:\.\d{1,3}){3}$/.test(normalizedHost)) {
    return true;
  }

  if (/^192\.168(?:\.\d{1,3}){2}$/.test(normalizedHost)) {
    return true;
  }

  if (/^169\.254(?:\.\d{1,3}){2}$/.test(normalizedHost)) {
    return true;
  }

  const privateRangeMatch = normalizedHost.match(/^172\.(\d{1,3})(?:\.\d{1,3}){2}$/);
  if (privateRangeMatch) {
    const secondOctet = Number(privateRangeMatch[1]);

    if (secondOctet >= 16 && secondOctet <= 31) {
      return true;
    }
  }

  if (/^(?:fc|fd)[0-9a-f:]*$/i.test(normalizedHost)) {
    return true;
  }

  return /^fe80:/i.test(normalizedHost);
}


// Formatting helpers.
// Format one timestamp in chat-friendly HH:MM form.
export function timeNow(dateInput) {
  const date = dateInput ? new Date(dateInput) : new Date();
  return date.toLocaleTimeString(intlLocaleTag(), { hour: '2-digit', minute: '2-digit' });
}

// Escape plain text for HTML content.
export function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>');
}

// Escape text for HTML attributes.
export function escapeAttributeValue(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// Escape text for textarea content.
export function escapeTextareaValue(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}


// Nested object helpers.
// Read one nested value by dot-separated path.
export function getNestedValue(source, path) {
  return String(path || '').split('.').reduce(function reduceValue(current, key) {
    if (!current || typeof current !== 'object') {
      return undefined;
    }

    return current[key];
  }, source);
}

// Write one nested value by dot-separated path.
export function setNestedValue(target, path, value) {
  const parts = String(path || '').split('.').filter(Boolean);

  if (!parts.length) {
    return;
  }

  let cursor = target;

  parts.forEach(function assignValue(part, index) {
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

// Delete one nested value and prune empty parent objects.
export function deleteNestedValue(target, path) {
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

// Flatten one nested config object into leaf-path records.
export function flattenConfigLeaves(source, prefix) {
  if (!source || typeof source !== 'object' || Array.isArray(source)) {
    return prefix ? [{ path: prefix, value: source }] : [];
  }

  return Object.entries(source).flatMap(function flattenEntry([key, value]) {
    const nextPath = prefix ? `${prefix}.${key}` : key;

    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return flattenConfigLeaves(value, nextPath);
    }

    return [{ path: nextPath, value }];
  });
}
