// Copyright NGGT.LightKeeper. All Rights Reserved.

// Cookie helpers.
// Read one cookie value by name.
export function getCookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

// Resolve the current CSRF token from the page or cookies.
export function getCsrfToken() {
  const tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
  if (tokenInput) {
    return tokenInput.value;
  }

  return getCookie('csrftoken');
}


// JSON request helpers.
// Send one JSON request and normalize the response payload.
export async function requestJson(url, options) {
  const requestOptions = options || {};
  const method = requestOptions.method || 'GET';
  const headers = {
    ...(requestOptions.headers || {})
  };

  if (!headers['X-CSRFToken'] && method !== 'GET' && method !== 'HEAD') {
    headers['X-CSRFToken'] = getCsrfToken();
  }

  const response = await fetch(url, {
    ...requestOptions,
    method,
    headers
  });

  let data = null;

  try {
    data = await response.json();
  } catch (_error) {
    data = null;
  }

  if (!response.ok) {
    const message = data && data.error ? data.error : `Request failed: ${response.status}`;
    const error = new Error(message);
    error.response = response;
    error.data = data;
    throw error;
  }

  return data;
}

// Send one JSON GET request.
export function getJson(url, options) {
  return requestJson(url, {
    ...(options || {}),
    method: 'GET'
  });
}

// Send one JSON POST request.
export function postJson(url, payload, options) {
  return requestJson(url, {
    ...(options || {}),
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...((options || {}).headers || {})
    },
    body: JSON.stringify(payload)
  });
}

// Send one JSON PATCH request.
export function patchJson(url, payload, options) {
  return requestJson(url, {
    ...(options || {}),
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      ...((options || {}).headers || {})
    },
    body: JSON.stringify(payload)
  });
}

// Send one JSON DELETE request.
export function deleteJson(url, options) {
  return requestJson(url, {
    ...(options || {}),
    method: 'DELETE'
  });
}
