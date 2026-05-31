// Copyright NGGT.LightKeeper. All Rights Reserved.

import { escHtml, escapeAttributeValue } from '../main/utils.js';
import { getJson, postJson } from '../main/api.js';

// Portal poll cache.
// If hydrate runs twice on the same portal node, clear any prior poll interval.
const portalFramePollIntervalByEl = typeof WeakMap === 'undefined' ? null : new WeakMap();
const portalWaitTimerByEl = typeof WeakMap === 'undefined' ? null : new WeakMap();

// Browser portal UI.
// Collapse browser-agent tool calls into one compact visual session block.
export function createBrowserPortalUi(context) {
  const { icons, state } = context;

  // Segment classification helpers.
  // Normalize one tool segment into a canonical tool id suffix.
  function normalizeToolId(segment) {
    const rawToolId = String(segment && (segment.toolId || segment.alias || segment.toolName) || '').trim();
    if (!rawToolId) {
      return '';
    }
    const aliasParts = rawToolId.split('__');
    return aliasParts[aliasParts.length - 1].toLowerCase();
  }

  // Report whether one activity segment belongs to the browser agent.
  function isBrowserToolSegment(segment) {
    if (!segment || segment.type !== 'tool') {
      return false;
    }
    const serverId = String(segment.serverId || '').toLowerCase();
    const alias = String(segment.alias || '').toLowerCase();
    const toolId = normalizeToolId(segment);
    return serverId === 'browser_agent'
      || serverId === 'browser'
      || alias.startsWith('browser_agent__')
      || toolId.startsWith('browser_');
  }

  // Report whether raw browser tool rows should be shown for debugging.
  function browserDebugEnabled(options) {
    const renderOptions = options || {};
    if (renderOptions.browserDebug === true || renderOptions.showRawBrowserTools === true) {
      return true;
    }
    const settings = state && state.runtimeSettings && typeof state.runtimeSettings === 'object'
      ? state.runtimeSettings
      : {};
    return settings.browser_portal_debug === true || settings.browserPortalDebug === true;
  }

  // Derive the portal status badge from the latest browser segment.
  function statusForSegments(segments, options) {
    const renderOptions = options || {};
    const latest = segments[segments.length - 1] || {};
    const latestToolId = normalizeToolId(latest);
    const toolUi = latest.toolUi && typeof latest.toolUi === 'object' ? latest.toolUi : {};
    const uiStatus = String(toolUi.status || '').trim().toLowerCase();
    const resultText = String(latest.result || '').trim().toLowerCase();

    if (uiStatus === 'failed' || uiStatus === 'error' || resultText.startsWith('error:')) {
      return 'failed';
    }
    if (latestToolId === 'browser_wait_for_user' && (latest.result === null || latest.result === undefined)) {
      return 'waiting';
    }
    if (renderOptions.streaming === true || latest.result === null || latest.result === undefined) {
      return 'live';
    }
    if (uiStatus === 'waiting' || uiStatus === 'paused') {
      return 'waiting';
    }
    return 'done';
  }

  // Map one portal status code to a short human label.
  function statusLabel(status) {
    if (status === 'failed') {
      return 'Failed';
    }
    if (status === 'waiting') {
      return 'Waiting';
    }
    if (status === 'done') {
      return 'Finished';
    }
    return 'Live';
  }


  // Portal rendering helpers.
  // Build icon, title, and detail text for one browser tool segment.
  function actionForSegment(segment) {
    const toolId = normalizeToolId(segment);
    const args = segment && segment.arguments && typeof segment.arguments === 'object'
      ? segment.arguments
      : {};

    if (toolId === 'browser_navigate') {
      return {
        icon: icons.BROWSER_NAVIGATE_ICON || icons.GLOBE_ICON || '',
        title: 'browser navigate',
        detail: args.url ? String(args.url) : ''
      };
    }
    if (toolId === 'browser_click') {
      return {
        icon: icons.BROWSER_CURSOR_ICON || '',
        title: 'browser click',
        detail: args.ref ? `ref ${args.ref}` : ''
      };
    }
    if (toolId === 'browser_key') {
      return {
        icon: icons.BROWSER_KEYBOARD_ICON || '',
        title: 'browser key',
        detail: args.key ? String(args.key) : ''
      };
    }
    if (toolId === 'browser_scroll') {
      return {
        icon: icons.BROWSER_SCROLL_ICON || '',
        title: 'browser scroll',
        detail: args.direction ? String(args.direction) : ''
      };
    }
    if (toolId === 'browser_text') {
      return {
        icon: icons.BROWSER_TYPE_ICON || '',
        title: 'browser text',
        detail: args.ref ? `ref ${args.ref}` : ''
      };
    }
    if (toolId === 'browser_screenshot') {
      return {
        icon: icons.TOOL_IMAGE_VIEW_ICON || icons.GLOBE_ICON || '',
        title: 'browser screenshot',
        detail: args.full_page ? 'full page' : 'viewport'
      };
    }
    if (toolId === 'browser_snapshot') {
      return {
        icon: icons.GLOBE_ICON || '',
        title: 'browser snapshot',
        detail: args.full ? 'full' : 'controls'
      };
    }
    if (toolId === 'browser_wait_for_user') {
      return {
        icon: icons.GLOBE_ICON || '',
        title: 'browser wait_for_user',
        detail: args.timeout_seconds ? `${args.timeout_seconds}s` : ''
      };
    }

    return {
      icon: icons.GLOBE_ICON || '',
      title: segment.toolName || toolId || 'browser',
      detail: ''
    };
  }

  // Build a data URL from one browser screenshot payload.
  function dataUrlFromImage(image) {
    if (!image || typeof image !== 'object') {
      return '';
    }
    if (image.src) {
      return String(image.src);
    }
    const preview = image.preview && typeof image.preview === 'object' ? image.preview : {};
    const dataBase64 = preview.data_base64 || image.data_base64;
    if (!dataBase64) {
      return '';
    }
    const mime = preview.mime_type || image.mime || image.mime_type || 'image/png';
    return `data:${mime};base64,${dataBase64}`;
  }

  // Pick the latest screenshot frame from a browser segment list.
  function extractFrame(segments) {
    for (let index = segments.length - 1; index >= 0; index -= 1) {
      const segment = segments[index];
      const toolUi = segment && segment.toolUi && typeof segment.toolUi === 'object' ? segment.toolUi : {};
      const structured = segment && segment.structuredContent && typeof segment.structuredContent === 'object'
        ? segment.structuredContent
        : {};
      const candidates = [
        toolUi.frame,
        toolUi.image,
        toolUi.kind === 'browser_screenshot' ? toolUi.image : null,
        structured.frame,
        structured.image,
        structured.result
      ];
      for (let candidateIndex = 0; candidateIndex < candidates.length; candidateIndex += 1) {
        const candidate = candidates[candidateIndex];
        const src = dataUrlFromImage(candidate);
        if (src) {
          return {
            src,
            width: candidate.width || 0,
            height: candidate.height || 0,
            url: candidate.url || structured.url || ''
          };
        }
      }
    }
    return null;
  }

  // Resolve the active page URL from frame metadata or navigate args.
  function extractUrl(segments, frame) {
    if (frame && frame.url) {
      return String(frame.url);
    }
    for (let index = segments.length - 1; index >= 0; index -= 1) {
      const segment = segments[index];
      const args = segment && segment.arguments && typeof segment.arguments === 'object'
        ? segment.arguments
        : {};
      if (args.url) {
        return String(args.url);
      }
    }
    return '';
  }

  // Render the live viewport image or an empty-state placeholder.
  function renderFrame(frame, status) {
    const keyCapture = status === 'waiting'
      ? '<textarea class="browser-portal-key-capture" aria-hidden="true" tabindex="-1" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false"></textarea>'
      : '';
    if (frame && frame.src) {
      const fetchPriority = status === 'waiting' ? 'high' : 'low';
      return `
        <img class="browser-portal-image" src="${escapeAttributeValue(frame.src)}" alt="Browser viewport" decoding="async" fetchpriority="${fetchPriority}">
        <span class="browser-portal-click-layer" aria-hidden="true"></span>
        ${keyCapture}
        ${status === 'done' ? '<div class="browser-portal-ended">Browsing finished</div>' : ''}
      `;
    }

    const isEnded = status === 'done' || status === 'failed';
    const placeholderIcon = isEnded
      ? (icons.BROWSER_DISCONNECTED_ICON || icons.GLOBE_ICON || '')
      : (icons.GLOBE_ICON || '');
    const placeholderText = status === 'failed'
      ? 'Broadcast failed'
      : (isEnded ? 'Broadcast ended' : 'Waiting for browser frame');
    return `
      <div class="browser-portal-empty">
        <span class="browser-portal-empty-icon">${placeholderIcon}</span>
        <span>${escHtml(placeholderText)}</span>
      </div>
      ${keyCapture}
    `;
  }

  // Render one consolidated browser portal block for related tool segments.
  function renderPortalSegment(browserSegments, options) {
    const status = statusForSegments(browserSegments, options);
    const latest = browserSegments[browserSegments.length - 1] || {};
    const latestToolId = normalizeToolId(latest);
    const latestArgs = latest.arguments && typeof latest.arguments === 'object' ? latest.arguments : {};
    const isWaitUser = latestToolId === 'browser_wait_for_user' && status !== 'done' && status !== 'failed';
    const action = actionForSegment(latest);
    const frame = extractFrame(browserSegments);
    const detail = action.detail ? `<span class="browser-portal-detail">${escHtml(action.detail)}</span>` : '';
    const timeoutSeconds = Math.max(1, parseInt(latestArgs.timeout_seconds || 45, 10) || 45);

    if (isWaitUser) {
      // Wait state: show a plain card without a live frame or interactive DOM controls.
      const waitMessage = String(latestArgs.message || 'Complete the step in the browser window, then the model will continue.').trim();
      return `
        <div class="browser-portal browser-portal--wait-user" data-browser-status="waiting" data-browser-wait-timeout="${escapeAttributeValue(timeoutSeconds)}">
          <div class="browser-portal-strip">
            <div class="browser-portal-action">
              <span class="browser-portal-action-icon">${action.icon || icons.GLOBE_ICON || ''}</span>
              <span class="browser-portal-action-title">${escHtml(action.title)}</span>
              ${detail}
            </div>
            <div class="browser-portal-status browser-portal-status--waiting">
              <span class="browser-portal-status-dot" aria-hidden="true"></span>
              <span>Waiting</span>
            </div>
          </div>
          <div class="browser-portal-wait-card">
            <div class="browser-portal-wait-card-message">${escHtml(waitMessage)}</div>
            <div class="browser-portal-wait-card-footer">
              <div class="browser-portal-timer" data-browser-portal-timer>${escHtml(`${timeoutSeconds}s`)}</div>
              <button class="browser-portal-finish" type="button" data-browser-portal-finish>Done</button>
            </div>
          </div>
        </div>
      `;
    }

    const frameWidth = frame && frame.width ? Number(frame.width) : 0;
    const frameHeight = frame && frame.height ? Number(frame.height) : 0;
    return `
      <div class="browser-portal" data-browser-status="${escapeAttributeValue(status)}" data-browser-frame-width="${escapeAttributeValue(frameWidth)}" data-browser-frame-height="${escapeAttributeValue(frameHeight)}">
        <div class="browser-portal-strip">
          <div class="browser-portal-action">
            <span class="browser-portal-action-icon">${action.icon || icons.GLOBE_ICON || ''}</span>
            <span class="browser-portal-action-title">${escHtml(action.title)}</span>
            ${detail}
          </div>
          <div class="browser-portal-status browser-portal-status--${escapeAttributeValue(status)}">
            <span class="browser-portal-status-dot" aria-hidden="true"></span>
            <span>${escHtml(statusLabel(status))}</span>
          </div>
        </div>
        <div class="browser-portal-frame">
          ${renderFrame(frame, status)}
        </div>
      </div>
    `;
  }


  // Portal lifecycle.
  // Attach interactive handlers to browser portal nodes under one root.
  function hydrate(root) {
    const rootEl = root && root.jquery ? root[0] : root;
    if (!rootEl) {
      return;
    }

    // Wire manual control, polling, and timers for each wait-user portal node.
    rootEl.querySelectorAll('.browser-portal').forEach(function hydratePortal(portal) {
      if (!portal.classList.contains('browser-portal--wait-user')) {
        return;
      }

      if (portalLiveUiShowsSessionEnded()) {
        portal.classList.remove('browser-portal--wait-user');
        return;
      }

      const frame = portal.querySelector('.browser-portal-frame');
      let image = frame ? portal.querySelector('.browser-portal-image') : null;
      let keyCapture = frame ? portal.querySelector('.browser-portal-key-capture') : null;
      const status = portal.querySelector('.browser-portal-status');
      const statusText = status ? status.querySelector('span:last-child') : null;
      const actionTitle = portal.querySelector('.browser-portal-action-title');
      const actionDetail = portal.querySelector('.browser-portal-detail');
      const finishButton = portal.querySelector('[data-browser-portal-finish]');
      let framePollTimer = 0;
      let framePollInFlight = false;
      let eventInFlight = false;
      let latestVersion = 0;
      let latestSessionId = String(portal.dataset.browserSessionId || '');
      let consecutiveFrameNoSession = 0;
      let hadSuccessfulPortalFramePoll = false;
      let lastPortalFrameSrc = '';

      const FRAME_POLL_MS_FOREGROUND = 100;
      const FRAME_POLL_MS_BACKGROUND = 1000;

      // Wait-session timing helpers.
      // Coerce one payload field into a positive finite number.
      function numericPayloadValue(value) {
        const number = Number(value);
        return Number.isFinite(number) && number > 0 ? number : 0;
      }

      // Convert one epoch-seconds value from the server into milliseconds.
      function epochSecondsToMs(value) {
        const number = numericPayloadValue(value);
        return number > 0 ? number * 1000 : 0;
      }

      // Resolve the wait-session deadline timestamp in milliseconds.
      function waitDeadlineAtMs() {
        const deadline = Number(portal.dataset.browserWaitDeadlineAt || 0) || 0;
        if (deadline > 0) {
          return deadline;
        }
        const timeoutSeconds = Math.max(1, parseInt(portal.dataset.browserWaitTimeout || '45', 10) || 45);
        const startedAt = Number(portal.dataset.browserWaitStartedAt || 0) || 0;
        return (startedAt || Date.now()) + (timeoutSeconds * 1000);
      }


      // Frame polling.
      // Start or restart the frame poll interval for the active tab visibility.
      function armFramePollInterval() {
        if (framePollTimer) {
          window.clearInterval(framePollTimer);
          framePollTimer = 0;
        }
        const ms = document.hidden ? FRAME_POLL_MS_BACKGROUND : FRAME_POLL_MS_FOREGROUND;
        framePollTimer = window.setInterval(function () {
          void pollFrameOnce();
        }, ms);
        if (portalFramePollIntervalByEl) {
          portalFramePollIntervalByEl.set(portal, framePollTimer);
        }
      }

      // Re-arm polling when the document visibility state changes.
      function onFramePollVisibility() {
        if (!portal.isConnected || !portal.classList.contains('browser-portal--wait-user')) {
          document.removeEventListener('visibilitychange', onFramePollVisibility);
          return;
        }
        armFramePollInterval();
      }

      // Stop listening for visibility changes on this portal node.
      function detachFramePollVisibility() {
        document.removeEventListener('visibilitychange', onFramePollVisibility);
      }

      // Report whether the portal chip already shows a terminal session state.
      function portalLiveUiShowsSessionEnded() {
        const chip = portal.querySelector('.browser-portal-status');
        if (chip) {
          if (chip.classList.contains('browser-portal-status--done')
            || chip.classList.contains('browser-portal-status--failed')) {
            return true;
          }
        }
        const attr = String(portal.getAttribute('data-browser-status') || portal.dataset.browserStatus || '').trim().toLowerCase();
        return attr === 'done' || attr === 'failed';
      }

      // Read the frame object from one browser portal API payload.
      function frameFromPayload(payload) {
        if (!payload || typeof payload !== 'object') {
          return null;
        }
        return payload.frame && typeof payload.frame === 'object' ? payload.frame : null;
      }


      // Manual control input.
      // Ensure the hidden textarea used for keyboard capture exists.
      function ensureKeyCapture() {
        if (!frame) {
          return null;
        }
        keyCapture = frame.querySelector('.browser-portal-key-capture');
        if (!keyCapture) {
          keyCapture = document.createElement('textarea');
          keyCapture.className = 'browser-portal-key-capture';
          keyCapture.setAttribute('aria-hidden', 'true');
          keyCapture.tabIndex = -1;
          keyCapture.autocomplete = 'off';
          keyCapture.setAttribute('autocorrect', 'off');
          keyCapture.setAttribute('autocapitalize', 'off');
          keyCapture.spellcheck = false;
          frame.appendChild(keyCapture);
        }
        return keyCapture;
      }

      // Move focus into the keyboard capture surface for remote typing.
      function focusKeyCapture() {
        const capture = ensureKeyCapture();
        if (capture) {
          try {
            capture.focus({ preventScroll: true });
          } catch (_error) {
            capture.focus();
          }
          return;
        }
        if (frame) {
          frame.focus();
        }
      }


      // Portal status helpers.
      // Merge one server payload into local portal session state.
      function applyFramePayload(payload) {
        if (payload && Number.isFinite(Number(payload.version))) {
          latestVersion = Math.max(latestVersion, Number(payload.version));
        }
        if (payload && payload.session_id) {
          latestSessionId = String(payload.session_id);
          portal.dataset.browserSessionId = latestSessionId;
        }
        if (payload && typeof payload === 'object') {
          const nextTimeout = numericPayloadValue(payload.timeout_seconds);
          const nextStartedAt = epochSecondsToMs(payload.started_at);
          const nextDeadlineAt = epochSecondsToMs(payload.deadline_at);
          if (nextTimeout > 0) {
            portal.dataset.browserWaitTimeout = String(Math.max(1, Math.ceil(nextTimeout)));
          }
          if (nextStartedAt > 0) {
            portal.dataset.browserWaitStartedAt = String(nextStartedAt);
          }
          if (nextDeadlineAt > 0) {
            portal.dataset.browserWaitDeadlineAt = String(nextDeadlineAt);
          }
          const st = String(payload.status || '').trim().toLowerCase();
          if (st === 'done' || st === 'failed') {
            stopBrowserPortalManualLoop(st === 'failed' ? 'Broadcast failed' : 'Session ended');
          }
        }
      }

      // Update the manual status label text in the portal strip.
      function setManualStatus(text) {
        if (statusText) {
          statusText.textContent = text;
        }
      }

      // Apply one portal status class and label to the strip chip.
      function setPortalStatus(statusName, text) {
        const normalized = String(statusName || '').trim().toLowerCase() || 'waiting';
        portal.dataset.browserStatus = normalized;
        portal.setAttribute('data-browser-status', normalized);
        if (status) {
          ['live', 'waiting', 'done', 'failed'].forEach(function removeStatusClass(name) {
            status.classList.remove(`browser-portal-status--${name}`);
          });
          status.classList.add(`browser-portal-status--${normalized}`);
        }
        setManualStatus(text || statusLabel(normalized));
      }

      // Cancel the countdown animation frame for this portal node.
      function cancelWaitTimer() {
        if (!portalWaitTimerByEl) {
          return;
        }
        const frameId = portalWaitTimerByEl.get(portal);
        if (frameId) {
          window.cancelAnimationFrame(frameId);
          portalWaitTimerByEl.delete(portal);
        }
      }

      // Tear down polling, timers, and manual control for one portal node.
      function stopBrowserPortalManualLoop(reason) {
        detachFramePollVisibility();
        if (framePollTimer) {
          window.clearInterval(framePollTimer);
          framePollTimer = 0;
        }
        if (portalFramePollIntervalByEl) {
          portalFramePollIntervalByEl.delete(portal);
        }
        cancelWaitTimer();
        if (portal.isConnected) {
          portal.classList.remove('browser-portal--wait-user');
        }
        setPortalStatus(reason === 'Broadcast failed' ? 'failed' : 'done', reason || 'Session ended');
      }

      // Draw a short-lived click ring at the pointer position in the frame.
      function addClickRing(event) {
        if (!frame) {
          return;
        }
        const rect = frame.getBoundingClientRect();
        const ring = document.createElement('span');
        ring.className = 'browser-portal-click-ring';
        ring.style.left = `${event.clientX - rect.left}px`;
        ring.style.top = `${event.clientY - rect.top}px`;
        frame.appendChild(ring);
        ring.addEventListener('animationend', function removeRing() {
          ring.remove();
        }, { once: true });
      }

      // Map pointer coordinates into the visible browser image viewport.
      function browserImageGeometry() {
        if (!frame) {
          return null;
        }
        const rect = frame.getBoundingClientRect();
        const browserWidth = Math.max(1, Number(portal.dataset.browserFrameWidth || 0) || Math.round(rect.width));
        const browserHeight = Math.max(1, Number(portal.dataset.browserFrameHeight || 0) || Math.round(rect.height));
        const browserAspect = browserWidth / browserHeight;
        const frameAspect = rect.width / Math.max(1, rect.height);
        let visibleWidth = rect.width;
        let visibleHeight = rect.height;
        let left = rect.left;
        let top = rect.top;
        if (frameAspect > browserAspect) {
          visibleHeight = rect.height;
          visibleWidth = visibleHeight * browserAspect;
          left = rect.left + ((rect.width - visibleWidth) / 2);
        } else {
          visibleWidth = rect.width;
          visibleHeight = visibleWidth / browserAspect;
          top = rect.top + ((rect.height - visibleHeight) / 2);
        }
        return {
          browserWidth,
          browserHeight,
          left,
          top,
          width: Math.max(1, visibleWidth),
          height: Math.max(1, visibleHeight)
        };
      }

      // Poll the backend once for the latest browser portal frame state.
      async function pollFrameOnce() {
        if (!portal.isConnected || !portal.classList.contains('browser-portal--wait-user')) {
          return;
        }
        if (portalLiveUiShowsSessionEnded()) {
          stopBrowserPortalManualLoop('Session ended');
          return;
        }
        if (!framePollInFlight) {
          framePollInFlight = true;
          try {
            applyFramePayload(await getJson('/api/browser_portal/frame/'));
            setManualStatus('Ready');
            hadSuccessfulPortalFramePoll = true;
            consecutiveFrameNoSession = 0;
          } catch (error) {
            let httpStatus = error && error.response ? error.response.status : 0;
            const errMsg = String((error && error.message) || '');
            const errDataErr = error && error.data && error.data.error ? String(error.data.error) : '';
            const looksLikeNoSession = /no active browser_wait_for_user|no active browser session/i.test(errMsg)
              || /no active browser_wait_for_user|no active browser session/i.test(errDataErr);
            if (!httpStatus && errMsg.indexOf('404') !== -1) {
              httpStatus = 404;
            }
            if (httpStatus === 404 || looksLikeNoSession) {
              consecutiveFrameNoSession += 1;
              if (!hadSuccessfulPortalFramePoll) {
                setManualStatus('Starting browser');
              } else {
                setManualStatus('Ready');
              }
              if (Date.now() > waitDeadlineAtMs() + 1500) {
                stopBrowserPortalManualLoop('No active browser session');
              }
            } else {
              setManualStatus('Frame unavailable');
              consecutiveFrameNoSession = 0;
            }
          } finally {
            framePollInFlight = false;
          }
        }
      }


      // Portal event transport.
      // Send one manual browser portal event to the backend.
      async function sendPortalEvent(type, payload) {
        if (!portal.isConnected || !portal.classList.contains('browser-portal--wait-user')) {
          return false;
        }
        if (portalLiveUiShowsSessionEnded()) {
          portal.classList.remove('browser-portal--wait-user');
          return false;
        }
        eventInFlight = true;
        const active = document.activeElement;
        const capture = ensureKeyCapture();
        const clientMeta = {
          sent_at: Date.now(),
          portal_status: portal.dataset.browserStatus || '',
          latest_version: latestVersion,
          latest_session_id: latestSessionId,
          active_tag: active && active.tagName ? active.tagName.toLowerCase() : '',
          active_id: active && active.id ? active.id : '',
          active_class: active && active.className ? String(active.className).slice(0, 240) : '',
          frame_focused: document.activeElement === frame,
          capture_exists: !!capture,
          capture_focused: !!capture && document.activeElement === capture,
          browser_frame_width: Number(portal.dataset.browserFrameWidth || 0) || 0,
          browser_frame_height: Number(portal.dataset.browserFrameHeight || 0) || 0
        };
        if (actionTitle) {
          actionTitle.textContent = `portal ${type}`;
        }
        setPortalStatus('waiting', 'Sending event');
        try {
          applyFramePayload(await postJson('/api/browser_portal/event/', {
            type,
            version: latestVersion,
            session_id: latestSessionId,
            client_meta: clientMeta,
            ...(payload || {})
          }));
          if (type !== 'finish') {
            setPortalStatus('waiting', 'Ready');
          }
          return true;
        } catch (error) {
          setPortalStatus('failed', 'Event failed');
          let httpStatus = error && error.response ? error.response.status : 0;
          if (!httpStatus && error && error.message && String(error.message).indexOf('404') !== -1) {
            httpStatus = 404;
          }
          if (!httpStatus && error && error.message && String(error.message).indexOf('409') !== -1) {
            httpStatus = 409;
          }
          if (httpStatus === 409 || httpStatus === 404) {
            stopBrowserPortalManualLoop(
              httpStatus === 404 ? 'No active browser session' : 'Browser session ended'
            );
          }
          return false;
        } finally {
          eventInFlight = false;
        }
      }

      // Send one typed text chunk as a portal type event.
      function sendTypedText(text) {
        const value = String(text || '');
        if (value) {
          sendPortalEvent('type', { text: value });
        }
      }

      // Route keyboard input from the portal frame to backend events.
      function handlePortalKeyDown(event) {
        if (event.ctrlKey || event.metaKey || event.altKey || event.isComposing) {
          return;
        }

        const key = event.key || '';
        const fromCapture = keyCapture && event.target === keyCapture;

        if (key === 'Enter' || key === 'Tab' || key === 'Backspace' || key === 'Delete'
          || key === 'Escape' || key.startsWith('Arrow') || key === 'Home' || key === 'End'
          || key === 'PageUp' || key === 'PageDown') {
          event.preventDefault();
          sendPortalEvent('key', { key });
          return;
        }

        if (fromCapture) {
          return;
        }

        event.preventDefault();
        if (key.length === 1) {
          sendTypedText(key);
        } else if (key) {
          sendPortalEvent('key', { key });
        }
      }

      // Forward pasted plain text into the remote browser session.
      function handlePortalPaste(event) {
        event.preventDefault();
        const text = event.clipboardData ? event.clipboardData.getData('text/plain') : '';
        sendTypedText(text);
        if (keyCapture) {
          keyCapture.value = '';
        }
      }

      // Forward buffered characters from the hidden capture textarea.
      function handleCaptureInput(event) {
        const capture = event.target && event.target.classList && event.target.classList.contains('browser-portal-key-capture')
          ? event.target
          : null;
        if (!capture) {
          return;
        }
        const text = capture.value;
        capture.value = '';
        sendTypedText(text);
      }


      // One-time portal event wiring.
      if (portal.dataset.browserPortalHydrated !== '1') {
        portal.dataset.browserPortalHydrated = '1';
        if (frame) {
          frame.tabIndex = 0;
          ensureKeyCapture();
          frame.addEventListener('pointerdown', function onPointerDown(event) {
            focusKeyCapture();
            const geometry = browserImageGeometry();
            if (!geometry) {
              return;
            }
            const x = event.clientX - geometry.left;
            const y = event.clientY - geometry.top;
            if (x < 0 || y < 0 || x > geometry.width || y > geometry.height) {
              return;
            }
            addClickRing(event);
            sendPortalEvent('click', {
              x: Math.round(x),
              y: Math.round(y),
              viewport_width: Math.round(geometry.width),
              viewport_height: Math.round(geometry.height)
            });
          });
          frame.addEventListener('wheel', function onWheel(event) {
            event.preventDefault();
            sendPortalEvent('scroll', {
              delta_x: Math.round(event.deltaX),
              delta_y: Math.round(event.deltaY)
            });
          }, { passive: false });
          frame.addEventListener('keydown', handlePortalKeyDown);
          frame.addEventListener('paste', handlePortalPaste);
          frame.addEventListener('input', handleCaptureInput);
        }
        if (finishButton) {
          finishButton.addEventListener('click', function onFinishClick() {
            if (eventInFlight) {
              return;
            }
            finishButton.disabled = true;
            setPortalStatus('waiting', 'Finishing');
            sendPortalEvent('finish', {}).then(function stopManualControl(sent) {
              if (sent) {
                stopBrowserPortalManualLoop('Done');
              } else if (finishButton.isConnected) {
                finishButton.disabled = false;
              }
            });
          });
        }
      }

      if (portalWaitTimerByEl && portalWaitTimerByEl.get(portal)) {
        return;
      }
      portal.dataset.browserPortalTimerStarted = '1';
      const timer = portal.querySelector('[data-browser-portal-timer]');
      const fallbackTimeoutSeconds = Math.max(1, parseInt(portal.dataset.browserWaitTimeout || '45', 10) || 45);
      if (!portal.dataset.browserWaitStartedAt) {
        portal.dataset.browserWaitStartedAt = String(Date.now());
      }
      if (!portal.dataset.browserWaitDeadlineAt) {
        portal.dataset.browserWaitDeadlineAt = String(Date.now() + (fallbackTimeoutSeconds * 1000));
      }

      // Update the wait countdown label on each animation frame.
      function tick() {
        if (!portal.isConnected || !portal.classList.contains('browser-portal--wait-user')) {
          if (portalWaitTimerByEl) {
            portalWaitTimerByEl.delete(portal);
          }
          return;
        }
        const timeoutSeconds = Math.max(1, parseInt(portal.dataset.browserWaitTimeout || '45', 10) || 45);
        const durationMs = timeoutSeconds * 1000;
        const startedAtMs = Math.max(0, Number(portal.dataset.browserWaitStartedAt || 0) || 0);
        const deadlineAtMs = Math.max(0, Number(portal.dataset.browserWaitDeadlineAt || 0) || 0);
        const remaining = Math.max(0, (deadlineAtMs || (startedAtMs + durationMs)) - Date.now());
        const elapsed = Math.max(0, durationMs - remaining);
        if (timer) {
          timer.textContent = `${Math.ceil(remaining / 1000)}s`;
        }
        if (elapsed > 0) {
          portal.dataset.browserWaitElapsed = String(Math.round(elapsed));
        }
        if (remaining > 0) {
          const nextFrame = window.requestAnimationFrame(tick);
          if (portalWaitTimerByEl) {
            portalWaitTimerByEl.set(portal, nextFrame);
          }
        } else if (framePollTimer) {
          detachFramePollVisibility();
          window.clearInterval(framePollTimer);
          framePollTimer = 0;
          if (portalFramePollIntervalByEl) {
            portalFramePollIntervalByEl.delete(portal);
          }
          if (portalWaitTimerByEl) {
            portalWaitTimerByEl.delete(portal);
          }
        }
      }

      const firstFrame = window.requestAnimationFrame(tick);
      if (portalWaitTimerByEl) {
        portalWaitTimerByEl.set(portal, firstFrame);
      }
      if (portalFramePollIntervalByEl) {
        const prevPoll = portalFramePollIntervalByEl.get(portal);
        if (prevPoll) {
          window.clearInterval(prevPoll);
          portalFramePollIntervalByEl.delete(portal);
        }
      }
      document.addEventListener('visibilitychange', onFramePollVisibility);
      armFramePollInterval();
    });
  }

  // Replace browser tool rows with one portal segment when debug mode is off.
  function enhanceSegments(segments, options) {
    const sourceSegments = Array.isArray(segments) ? segments : [];
    if (browserDebugEnabled(options)) {
      return sourceSegments.slice();
    }

    const browserSegments = sourceSegments.filter(isBrowserToolSegment);
    if (!browserSegments.length) {
      return sourceSegments.slice();
    }

    const status = statusForSegments(browserSegments, options);
    const latest = browserSegments[browserSegments.length - 1] || {};
    const latestToolId = normalizeToolId(latest);
    const firstBrowserIndex = sourceSegments.findIndex(isBrowserToolSegment);
    const keySeed = browserSegments[0].alias || browserSegments[0].toolId || firstBrowserIndex;
    const portalSegment = {
      type: 'browser_portal',
      key: `browser-${keySeed}`,
      html: renderPortalSegment(browserSegments, options),
      browserSegments
    };

    const result = [];
    sourceSegments.forEach(function appendSegment(segment, index) {
      if (index === firstBrowserIndex) {
        result.push(portalSegment);
      }
      if (!isBrowserToolSegment(segment)) {
        result.push(segment);
      }
    });
    return result;
  }

  return {
    enhanceSegments,
    hydrate,
    isBrowserToolSegment
  };
}
