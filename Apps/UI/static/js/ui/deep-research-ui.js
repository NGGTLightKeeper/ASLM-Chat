// Copyright NGGT.LightKeeper. All Rights Reserved.

import { getJson, postJson } from '../main/api.js';
import { t } from '../main/i18n.js';
import { escHtml, escapeAttributeValue } from '../main/utils.js';

const CONTROL_ENDPOINT = '/api/deep-research/control/';
const MAX_ACTIVITY_ITEMS = 160;
const MAX_CARD_ITEMS = 6;
const ACTIVE_POLL_INTERVAL_MS = 1600;
const APPROVAL_POLL_INTERVAL_MS = 2600;
const TERMINAL_STATUSES = new Set(['completed', 'partial', 'cancelled', 'failed', 'expired']);
const PRIVATE_EVENT_TYPES = new Set([
  'model_output_delta',
  'model_turn_completed',
  'usage',
  'reasoning_delta',
  'thinking_delta'
]);

function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function compactText(value, limit) {
  const maxLength = Math.max(32, Number(limit) || 240);
  const text = String(value === null || value === undefined ? '' : value)
    .replace(/\s+/g, ' ')
    .trim();
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, Math.max(1, maxLength - 1)).trimEnd()}\u2026`;
}

function normalizedType(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_');
}

function normalizedStatus(value, fallback) {
  const status = normalizedType(value);
  const aliases = {
    approved: 'running',
    awaiting_plan_approval: 'awaiting_approval',
    canceled: 'cancelled',
    done: 'completed',
    error: 'failed',
    revising_plan: 'revising',
    stopped: 'cancelled',
    waiting_approval: 'awaiting_approval'
  };
  return aliases[status] || status || fallback || 'planning';
}

function canonicalAlias(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/__\d+$/, '');
}

function statusIsTerminal(value) {
  return TERMINAL_STATUSES.has(normalizedStatus(value));
}

function deepResearchUiPayload(segment) {
  const safeSegment = asObject(segment);
  const structured = asObject(safeSegment.structuredContent);
  const structuredUi = asObject(structured.ui);
  const directUi = asObject(safeSegment.toolUi);
  return {
    ...structuredUi,
    ...directUi
  };
}

export function isDeepResearchToolSegment(segment) {
  const safeSegment = asObject(segment);
  if (safeSegment.type && safeSegment.type !== 'tool') {
    return false;
  }
  const ui = deepResearchUiPayload(safeSegment);
  const identity = [
    safeSegment.serverId,
    safeSegment.serverName,
    safeSegment.toolId,
    safeSegment.toolName,
    safeSegment.alias,
    ui.kind
  ].map(function normalizePart(value) {
    return String(value || '').trim().toLowerCase();
  }).join(' ');
  return identity.includes('deep_research') || identity.includes('deep research');
}

function activityBelongsToDeepResearch(payload) {
  const safePayload = asObject(payload);
  const identity = [
    safePayload.server_id,
    safePayload.serverId,
    safePayload.tool_id,
    safePayload.toolId,
    safePayload.alias,
    safePayload.session_id
  ].map(function normalizePart(value) {
    return String(value || '').trim().toLowerCase();
  }).join(' ');
  return identity.includes('deep_research') || identity.includes('deep-research');
}

function sessionIdFrom(value) {
  const payload = asObject(value);
  const data = asObject(payload.data);
  const state = asObject(payload.state);
  const snapshot = asObject(payload.snapshot);
  return String(
    payload.session_id
    || payload.sessionId
    || data.session_id
    || data.sessionId
    || state.session_id
    || snapshot.session_id
    || ''
  ).trim();
}

function planVersionFrom(value) {
  const payload = asObject(value);
  const data = asObject(payload.data);
  const state = asObject(payload.state);
  const numeric = Number(
    payload.plan_version
    ?? payload.planVersion
    ?? data.plan_version
    ?? data.planVersion
    ?? state.plan_version
    ?? state.planVersion
  );
  return Number.isFinite(numeric) && numeric >= 0 ? Math.floor(numeric) : null;
}

function planTextFromObject(plan) {
  const safePlan = asObject(plan);
  const direct = safePlan.text || safePlan.markdown || safePlan.description || safePlan.summary || '';
  if (direct) {
    return String(direct).trim();
  }
  const rawItems = safePlan.items || safePlan.steps || safePlan.checklist;
  if (!Array.isArray(rawItems)) {
    return '';
  }
  return rawItems.map(function planItemLine(item, index) {
    const safeItem = asObject(item);
    const title = typeof item === 'string'
      ? item
      : (safeItem.title || safeItem.text || safeItem.label || safeItem.description || `Step ${index + 1}`);
    return `- ${String(title || '').trim()}`;
  }).filter(Boolean).join('\n');
}

function parsePlanTextItems(rawPlan) {
  const text = String(rawPlan || '').trim();
  if (!text) {
    return [];
  }
  const lines = text.split(/\r?\n/);
  const items = [];
  lines.forEach(function parseLine(rawLine) {
    const line = String(rawLine || '').trim();
    if (!line) {
      return;
    }
    const match = line.match(/^(?:[-*+]\s+|\d+[.)]\s+)(?:\[([ xX])\]\s*)?(.+)$/);
    if (!match) {
      return;
    }
    items.push({
      title: match[2].trim(),
      status: match[1] && match[1].toLowerCase() === 'x' ? 'done' : 'pending'
    });
  });
  if (items.length > 0) {
    return items;
  }
  const paragraphs = text
    .split(/\n\s*\n/)
    .map(function cleanParagraph(value) { return compactText(value, 320); })
    .filter(Boolean);
  return paragraphs.length > 1
    ? paragraphs.map(function paragraphItem(title) { return { title, status: 'pending' }; })
    : [{ title: compactText(text, 420), status: 'pending' }];
}

function normalizeChecklistItem(item, index, previousItems) {
  const safeItem = asObject(item);
  const title = compactText(
    typeof item === 'string'
      ? item
      : (safeItem.title || safeItem.text || safeItem.label || safeItem.description || safeItem.task),
    420
  ) || `Step ${index + 1}`;
  const id = String(safeItem.id || safeItem.item_id || safeItem.key || `step-${index + 1}`).trim();
  const previous = (Array.isArray(previousItems) ? previousItems : []).find(function matchPrevious(candidate) {
    return candidate && (candidate.id === id || candidate.title === title);
  });
  return {
    id,
    title,
    status: normalizedStatus(safeItem.status || safeItem.state || (previous && previous.status), 'pending'),
    note: compactText(safeItem.note || safeItem.detail || safeItem.summary || (previous && previous.note), 260)
  };
}

function normalizePlan(plan, checklist, previousItems) {
  const planObject = asObject(plan);
  const rawPlan = typeof plan === 'string'
    ? String(plan).trim()
    : planTextFromObject(planObject);
  let rawItems = Array.isArray(checklist) ? checklist : null;
  if (!rawItems) {
    const candidate = planObject.items || planObject.steps || planObject.checklist;
    rawItems = Array.isArray(candidate) ? candidate : null;
  }
  if (!rawItems) {
    rawItems = parsePlanTextItems(rawPlan);
  }
  const items = rawItems.map(function normalizeItem(item, index) {
    return normalizeChecklistItem(item, index, previousItems);
  });
  return {
    rawPlan: rawPlan || items.map(function itemLine(item) { return `- ${item.title}`; }).join('\n'),
    items
  };
}

function queryStringsFrom(value) {
  const payload = asObject(value);
  const queries = [];
  const visited = new Set();

  function append(candidate, depth) {
    if (candidate === null || candidate === undefined) {
      return;
    }
    if (Array.isArray(candidate)) {
      candidate.forEach(function appendArrayItem(item) { append(item, (depth || 0) + 1); });
      return;
    }
    if (typeof candidate === 'object') {
      if (visited.has(candidate) || (depth || 0) > 5) {
        return;
      }
      visited.add(candidate);
      append(
        candidate.compiled_query
        || candidate.compiledQuery
        || candidate.search_query
        || candidate.searchQuery
        || candidate.query
        || candidate.q
        || candidate.text,
        (depth || 0) + 1
      );
      [
        'queries',
        'selected_queries',
        'selectedQueries',
        'next_queries',
        'nextQueries',
        'search_queries',
        'searchQueries',
        'arguments',
        'args',
        'parameters',
        'params',
        'input',
        'request',
        'data'
      ].forEach(function appendNested(key) {
        if (candidate[key] !== undefined) {
          append(candidate[key], (depth || 0) + 1);
        }
      });
      return;
    }
    const text = compactText(candidate, 360);
    if (text && !queries.includes(text)) {
      queries.push(text);
    }
  }
  append(payload, 0);
  if (!queries.length) {
    append(payload.url || payload.urls, 0);
  }
  return queries.slice(0, 4);
}

function sourceCountFrom(value) {
  const payload = asObject(value);
  const data = asObject(payload.data);
  const structured = asObject(payload.structured_content || payload.structuredContent);
  const candidates = [
    payload.source_count,
    payload.sourceCount,
    payload.result_count,
    data.source_count,
    data.sourceCount,
    data.result_count
  ];
  for (let index = 0; index < candidates.length; index += 1) {
    const numeric = Number(candidates[index]);
    if (Number.isFinite(numeric) && numeric >= 0) {
      return Math.floor(numeric);
    }
  }
  const sources = payload.sources || data.sources || structured.sources;
  return Array.isArray(sources) ? sources.length : null;
}

function flattenActivityPayload(payload, inherited) {
  const safePayload = asObject(payload);
  const inheritedMeta = asObject(inherited);
  const ownMeta = {
    alias: safePayload.alias || inheritedMeta.alias || '',
    server_id: safePayload.server_id || safePayload.serverId || inheritedMeta.server_id || '',
    tool_id: safePayload.tool_id || safePayload.toolId || inheritedMeta.tool_id || '',
    session_id: safePayload.session_id || inheritedMeta.session_id || ''
  };
  const nestedEvent = asObject(safePayload.event);
  if (normalizedType(nestedEvent.type) === 'event_batch' && Array.isArray(nestedEvent.events)) {
    return nestedEvent.events.flatMap(function flattenNested(event) {
      return flattenActivityPayload(event, ownMeta);
    });
  }
  if (normalizedType(safePayload.type) === 'event_batch' && Array.isArray(safePayload.events)) {
    return safePayload.events.flatMap(function flattenBatch(event) {
      return flattenActivityPayload(event, ownMeta);
    });
  }
  if (!Object.keys(safePayload).length) {
    return [];
  }
  return [{ event: safePayload, meta: ownMeta }];
}

function stateCssClass(status) {
  return normalizedStatus(status).replace(/[^a-z0-9_-]+/g, '-');
}

function statusLabel(status) {
  const normalized = normalizedStatus(status);
  const labels = {
    planning: t('research.statusPlanning', null, 'Planning'),
    awaiting_approval: t('research.statusAwaitingApproval', null, 'Awaiting approval'),
    awaiting_revision_approval: t('research.statusAwaitingApproval', null, 'Awaiting approval'),
    revising: t('research.statusRevising', null, 'Updating plan'),
    starting: t('research.statusStarting', null, 'Starting'),
    running: t('research.statusRunning', null, 'Researching'),
    reflecting: t('research.statusReflecting', null, 'Reflecting'),
    synthesizing: t('research.statusSynthesizing', null, 'Writing report'),
    stopping: t('research.statusStopping', null, 'Stopping'),
    cancelled: t('research.statusStopped', null, 'Stopped'),
    completed: t('research.statusCompleted', null, 'Completed'),
    partial: t('research.statusPartial', null, 'Partial'),
    failed: t('research.statusFailed', null, 'Failed'),
    expired: t('research.statusExpired', null, 'Expired')
  };
  return labels[normalized] || normalized.replace(/_/g, ' ');
}

function checklistStatus(value) {
  const normalized = normalizedStatus(value, 'pending');
  if (normalized === 'completed' || normalized === 'done') {
    return 'done';
  }
  return 'pending';
}

function statusCanApprove(status) {
  const normalized = normalizedStatus(status);
  return normalized === 'awaiting_approval' || normalized === 'awaiting_revision_approval';
}

function statusCanEdit(status) {
  const normalized = normalizedStatus(status);
  return [
    'awaiting_approval',
    'awaiting_revision_approval',
    'running',
    'reflecting'
  ].includes(normalized);
}

function statusCanStop(status) {
  const normalized = normalizedStatus(status);
  return !statusIsTerminal(normalized) && normalized !== 'stopping';
}

function stateCanApprove(state) {
  return typeof state.canApprove === 'boolean'
    ? state.canApprove
    : statusCanApprove(state.status);
}

function stateCanEdit(state) {
  return typeof state.canEdit === 'boolean'
    ? state.canEdit
    : statusCanEdit(state.status);
}

function stateCanStop(state) {
  return typeof state.canStop === 'boolean'
    ? state.canStop
    : statusCanStop(state.status);
}

function pendingActionLabel(action) {
  const labels = {
    approve: t('research.sendingApproval', null, 'Sending approval'),
    edit: t('research.savingPlan', null, 'Saving plan'),
    stop: t('research.sendingStop', null, 'Sending stop request')
  };
  return labels[normalizedType(action)] || t('research.updating', null, 'Updating');
}

function escapeCssAttributeValue(value) {
  const raw = String(value || '');
  if (window.CSS && typeof window.CSS.escape === 'function') {
    return window.CSS.escape(raw);
  }
  return raw.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function createEmptyState(key) {
  return {
    key,
    sessionId: '',
    alias: '',
    topic: '',
    status: 'planning',
    phase: 'planning',
    planVersion: 0,
    rawPlan: '',
    items: [],
    currentItemId: '',
    latestAction: t('research.preparingPlan', null, 'Preparing the research plan'),
    sourceCount: 0,
    queryBudget: 0,
    queriesUsed: 0,
    activeQueries: [],
    iteration: 0,
    report: '',
    sources: [],
    lastSequence: 0,
    activity: [],
    seenEvents: new Set(),
    pendingAction: '',
    pendingPlanText: '',
    editingPlanVersion: null,
    controlHoldUntil: 0,
    pollFailures: 0,
    canApprove: null,
    canEdit: null,
    canStop: null,
    error: '',
    segment: null
  };
}

// Deep Research UI.
// Reduce the tool's nested activity stream into one stable public progress card.
export function createDeepResearchUi(context, dependencies) {
  const { toolInspector } = dependencies;
  const states = new Map();
  const aliasToKey = new Map();
  const sessionToKey = new Map();
  const pollTimers = new Map();
  const pollsInFlight = new Set();

  function ensureState(key) {
    const normalizedKey = String(key || '').trim() || `research-local-${states.size + 1}`;
    if (!states.has(normalizedKey)) {
      states.set(normalizedKey, createEmptyState(normalizedKey));
    }
    return states.get(normalizedKey);
  }

  function bindIdentity(state, sessionId, alias) {
    const normalizedSessionId = String(sessionId || '').trim();
    const normalizedAlias = canonicalAlias(alias);
    if (normalizedSessionId) {
      state.sessionId = normalizedSessionId;
      sessionToKey.set(normalizedSessionId, state.key);
    }
    if (normalizedAlias) {
      state.alias = normalizedAlias;
      aliasToKey.set(normalizedAlias, state.key);
    }
  }

  function stateForIdentity(sessionId, alias, create) {
    const normalizedSessionId = String(sessionId || '').trim();
    const normalizedAlias = canonicalAlias(alias);
    let existingKey = normalizedSessionId
      ? sessionToKey.get(normalizedSessionId)
      : (normalizedAlias && aliasToKey.get(normalizedAlias));
    if (!existingKey && normalizedSessionId && normalizedAlias) {
      const provisionalKey = aliasToKey.get(normalizedAlias);
      const provisionalState = provisionalKey ? states.get(provisionalKey) : null;
      // Adopt an alias-only placeholder once. Never merge a new research
      // session into an older session merely because both tool calls use the
      // same MCP alias.
      if (provisionalState && !provisionalState.sessionId) {
        existingKey = provisionalKey;
      }
    }
    if (existingKey) {
      const state = ensureState(existingKey);
      bindIdentity(state, normalizedSessionId, normalizedAlias);
      return state;
    }
    if (create === false) {
      return null;
    }
    const state = ensureState(normalizedSessionId || normalizedAlias || 'deep-research');
    bindIdentity(state, normalizedSessionId, normalizedAlias);
    return state;
  }

  function stateForSegment(segment) {
    const safeSegment = asObject(segment);
    const ui = deepResearchUiPayload(safeSegment);
    const structured = asObject(safeSegment.structuredContent);
    const sessionId = String(ui.session_id || structured.session_id || '').trim();
    const state = stateForIdentity(sessionId, safeSegment.alias, true);
    ingestSegment(state, safeSegment);
    return state;
  }

  function mergePlan(state, plan, checklist) {
    if (plan === undefined && checklist === undefined) {
      return;
    }
    const normalized = normalizePlan(
      plan === undefined ? state.rawPlan : plan,
      checklist,
      state.items
    );
    if (normalized.rawPlan) {
      state.rawPlan = normalized.rawPlan;
    }
    if (normalized.items.length) {
      state.items = normalized.items.map(function withChecklistStatus(item) {
        return { ...item, status: checklistStatus(item.status) };
      });
    }
  }

  function mergeSnapshot(state, snapshot, options) {
    const safeSnapshot = asObject(snapshot);
    const mergeOptions = options || {};
    bindIdentity(
      state,
      safeSnapshot.session_id || safeSnapshot.sessionId,
      safeSnapshot.alias || state.alias
    );
    if (!mergeOptions.skipEvents) {
      const publicEvents = safeSnapshot.events
        || safeSnapshot.event_tail
        || safeSnapshot.events_tail
        || safeSnapshot.public_events;
      if (Array.isArray(publicEvents)) {
        publicEvents.forEach(function mergeSnapshotEvent(event) {
          applyEvent(state, event, {
            alias: safeSnapshot.alias || state.alias,
            session_id: safeSnapshot.session_id || safeSnapshot.sessionId || state.sessionId
          });
        });
      }
    }
    const topic = safeSnapshot.topic || safeSnapshot.request || safeSnapshot.question;
    if (topic) {
      state.topic = String(topic).trim();
    }
    if (!mergeOptions.skipPlan) {
      mergePlan(
        state,
        safeSnapshot.plan,
        safeSnapshot.checklist || safeSnapshot.items || asObject(safeSnapshot.plan).items
      );
    }
    const version = planVersionFrom(safeSnapshot);
    if (version !== null) {
      state.planVersion = Math.max(state.planVersion, version);
    }
    const sourceCount = sourceCountFrom(safeSnapshot);
    if (sourceCount !== null) {
      state.sourceCount = Math.max(state.sourceCount, sourceCount);
    }
    const queryBudget = Number(safeSnapshot.query_budget ?? safeSnapshot.queryBudget);
    if (Number.isFinite(queryBudget) && queryBudget >= 0) {
      state.queryBudget = Math.floor(queryBudget);
    }
    const queriesUsed = Number(safeSnapshot.queries_used ?? safeSnapshot.queriesUsed);
    if (Number.isFinite(queriesUsed) && queriesUsed >= 0) {
      state.queriesUsed = Math.max(state.queriesUsed, Math.floor(queriesUsed));
    }
    const iteration = Number(safeSnapshot.iteration);
    if (Number.isFinite(iteration) && iteration >= 0) {
      state.iteration = Math.max(state.iteration, Math.floor(iteration));
    }
    if (safeSnapshot.current_item_id || safeSnapshot.currentItemId) {
      state.currentItemId = String(safeSnapshot.current_item_id || safeSnapshot.currentItemId);
    }
    if ((safeSnapshot.latest_action || safeSnapshot.latestAction) && !mergeOptions.skipLatestAction) {
      state.latestAction = compactText(safeSnapshot.latest_action || safeSnapshot.latestAction, 320);
    }
    if (typeof safeSnapshot.can_approve === 'boolean' || typeof safeSnapshot.canApprove === 'boolean') {
      state.canApprove = Boolean(safeSnapshot.can_approve ?? safeSnapshot.canApprove);
    }
    if (typeof safeSnapshot.can_edit === 'boolean' || typeof safeSnapshot.canEdit === 'boolean') {
      state.canEdit = Boolean(safeSnapshot.can_edit ?? safeSnapshot.canEdit);
    }
    if (typeof safeSnapshot.can_stop === 'boolean' || typeof safeSnapshot.canStop === 'boolean') {
      state.canStop = Boolean(safeSnapshot.can_stop ?? safeSnapshot.canStop);
    }
    const snapshotError = safeSnapshot.error || safeSnapshot.public_error || safeSnapshot.publicError;
    if (snapshotError) {
      state.error = compactText(snapshotError, 520);
    }
    const snapshotReport = safeSnapshot.report || safeSnapshot.model_context || safeSnapshot.modelContext;
    if (snapshotReport) {
      state.report = String(snapshotReport).trim();
    }
    if (Array.isArray(safeSnapshot.sources)) {
      state.sources = safeSnapshot.sources.filter(function validSource(source) {
        return source && typeof source === 'object';
      }).slice(0, 50);
    }
    if (safeSnapshot.phase && !mergeOptions.skipPhase) {
      state.phase = normalizedType(safeSnapshot.phase);
    }
    if (safeSnapshot.status && !mergeOptions.skipStatus) {
      const snapshotPhase = normalizedType(safeSnapshot.phase);
      const baseStatus = normalizedStatus(safeSnapshot.status, state.status);
      const nextStatus = baseStatus === 'running' && snapshotPhase === 'reflection'
        ? 'reflecting'
        : baseStatus;
      const mayApply = mergeOptions.forceStatus
        || statusIsTerminal(nextStatus)
        || !statusIsTerminal(state.status);
      if (mayApply) {
        state.status = nextStatus;
      }
    }
    const lastSequence = Number(safeSnapshot.last_sequence ?? safeSnapshot.lastSequence);
    if (Number.isFinite(lastSequence) && lastSequence >= 0) {
      state.lastSequence = Math.max(state.lastSequence, Math.floor(lastSequence));
    }
  }

  function ingestSegment(state, segment) {
    const ui = deepResearchUiPayload(segment);
    const structured = asObject(segment.structuredContent);
    const argumentsPayload = asObject(segment.arguments);
    state.segment = segment;
    bindIdentity(state, ui.session_id || structured.session_id, segment.alias);
    if (!state.topic) {
      state.topic = String(ui.topic || structured.topic || argumentsPayload.topic || '').trim();
    }
    const hasResult = segment.result !== null && segment.result !== undefined;
    const resultStatus = normalizedStatus(ui.status || structured.status || (hasResult ? 'completed' : 'planning'));
    const terminalResult = hasResult && statusIsTerminal(resultStatus);
    const segmentVersion = planVersionFrom({ ...structured, ...ui });
    const staleSegmentPlan = !terminalResult && (
      !!state.pendingPlanText
      || (segmentVersion !== null && segmentVersion < state.planVersion)
    );
    if (!staleSegmentPlan) {
      mergePlan(
        state,
        ui.plan !== undefined ? ui.plan : structured.plan,
        ui.checklist || structured.checklist || asObject(ui.plan).items || asObject(structured.plan).items
      );
    }
    const pristineState = state.lastSequence === 0
      && state.activity.length === 0
      && !state.pendingAction;
    mergeSnapshot(state, { ...structured, ...ui }, {
      skipPlan: staleSegmentPlan,
      skipPhase: !pristineState && !terminalResult,
      skipStatus: !pristineState && !terminalResult
    });
    if (hasResult) {
      if (statusIsTerminal(resultStatus)) {
        state.status = resultStatus;
      }
    }
  }

  function appendActivity(state, event, kind, title, detail, status) {
    const safeEvent = asObject(event);
    const sequence = Number(safeEvent.sequence);
    const timestamp = String(safeEvent.timestamp || safeEvent.created_at || '');
    const key = Number.isFinite(sequence)
      ? `seq-${sequence}`
      : `${normalizedType(safeEvent.type)}:${timestamp}:${title}:${detail}`;
    if (state.activity.some(function duplicate(item) { return item.key === key; })) {
      return;
    }
    state.activity.push({
      key,
      kind: normalizedType(kind) || 'progress',
      title: compactText(title, 240),
      detail: compactText(detail, 520),
      status: normalizedType(status) || 'done',
      timestamp
    });
    if (state.activity.length > MAX_ACTIVITY_ITEMS) {
      state.activity.splice(0, state.activity.length - MAX_ACTIVITY_ITEMS);
    }
  }

  function updateChecklistItem(state, value, fallbackStatus) {
    const payload = asObject(value);
    const itemPayload = asObject(payload.item);
    const candidate = Object.keys(itemPayload).length ? itemPayload : payload;
    const id = String(candidate.id || candidate.item_id || candidate.key || '').trim();
    const numericIndex = Number(candidate.index ?? candidate.item_index);
    let itemIndex = id
      ? state.items.findIndex(function findById(item) { return item && item.id === id; })
      : -1;
    if (itemIndex < 0 && Number.isInteger(numericIndex)) {
      itemIndex = numericIndex >= 1 && numericIndex <= state.items.length ? numericIndex - 1 : numericIndex;
    }
    if (itemIndex < 0) {
      const title = candidate.title || candidate.text || candidate.label || candidate.task;
      if (!title) {
        return;
      }
      state.items.push(normalizeChecklistItem({
        ...candidate,
        status: candidate.status || fallbackStatus
      }, state.items.length, state.items));
      itemIndex = state.items.length - 1;
    } else {
      const previous = state.items[itemIndex];
      state.items[itemIndex] = normalizeChecklistItem({
        ...previous,
        ...candidate,
        status: candidate.status || candidate.state || fallbackStatus || previous.status
      }, itemIndex, state.items);
    }
    state.items[itemIndex].status = checklistStatus(state.items[itemIndex].status);
  }

  function toolActionFromEvent(event, data) {
    const safeData = asObject(data);
    const toolId = normalizedType(safeData.tool_id || safeData.toolId || safeData.name || safeData.alias);
    const args = asObject(safeData.arguments || safeData.args);
    const queries = queryStringsFrom(Object.keys(args).length ? args : safeData);
    if (toolId.includes('search')) {
      return {
        kind: 'search',
        title: queries.length
          ? t('research.searchingFor', { query: queries[0] }, `Searching for \u201c${queries[0]}\u201d`)
          : t('research.searchingSources', null, 'Searching sources'),
        detail: queries.slice(1).join(' \u00b7 '),
        latest: queries.length ? `Searching: ${queries.join(' \u00b7 ')}` : 'Searching sources'
      };
    }
    if (toolId.includes('read_page') || toolId.includes('read_url')) {
      const url = queries[0] || compactText(args.url || args.urls, 300);
      return {
        kind: 'read',
        title: t('research.readingSource', null, 'Reading a source'),
        detail: url,
        latest: url ? `Reading: ${url}` : 'Reading a source'
      };
    }
    if (toolId.includes('bash') || toolId.includes('python') || toolId.includes('sandbox')) {
      return {
        kind: 'analysis',
        title: t('research.runningAnalysis', null, 'Running evidence analysis'),
        detail: '',
        latest: 'Analyzing evidence'
      };
    }
    return {
      kind: 'tool',
      title: compactText(safeData.tool_name || safeData.toolName || safeData.name || 'Using research tool', 180),
      detail: '',
      latest: 'Working with research evidence'
    };
  }

  function publicSummary(data) {
    const safeData = asObject(data);
    return compactText(
      safeData.public_summary
      || safeData.publicSummary
      || safeData.summary
      || safeData.status_message
      || '',
      520
    );
  }

  function applyEvent(state, event, meta) {
    const safeEvent = asObject(event);
    const type = normalizedType(safeEvent.type || safeEvent.event_type);
    if (!type) {
      return;
    }
    const sequence = Number(safeEvent.sequence);
    const eventKey = Number.isFinite(sequence)
      ? `${sessionIdFrom(safeEvent) || state.sessionId || state.key}:${sequence}`
      : `${type}:${String(safeEvent.timestamp || '')}:${JSON.stringify(asObject(safeEvent.data)).slice(0, 300)}`;
    if (state.seenEvents.has(eventKey)) {
      return;
    }
    state.seenEvents.add(eventKey);
    if (Number.isFinite(sequence) && sequence >= 0) {
      state.lastSequence = Math.max(state.lastSequence, Math.floor(sequence));
    }
    bindIdentity(state, sessionIdFrom(safeEvent) || meta.session_id, meta.alias);
    const data = asObject(safeEvent.data);
    const nestedState = asObject(data.state || data.snapshot || safeEvent.state || safeEvent.snapshot);
    if (Object.keys(nestedState).length) {
      mergeSnapshot(state, nestedState, { skipEvents: true });
    }
    const version = planVersionFrom(safeEvent);
    if (version !== null) {
      state.planVersion = Math.max(state.planVersion, version);
    }
    const sourceCount = sourceCountFrom(safeEvent);
    if (sourceCount !== null) {
      state.sourceCount = Math.max(state.sourceCount, sourceCount);
    }
    if (safeEvent.iteration !== undefined || data.iteration !== undefined) {
      const iteration = Number(safeEvent.iteration ?? data.iteration);
      if (Number.isFinite(iteration)) {
        state.iteration = Math.max(state.iteration, Math.floor(iteration));
      }
    }

    if (PRIVATE_EVENT_TYPES.has(type)) {
      return;
    }

    if (type === 'session_started') {
      state.status = 'planning';
      state.phase = 'planning';
      state.canApprove = false;
      state.canEdit = false;
      state.canStop = true;
      state.topic = String(data.topic || state.topic || '').trim();
      mergeSnapshot(state, data);
      state.latestAction = t('research.preparingPlan', null, 'Preparing the research plan');
      appendActivity(state, safeEvent, 'plan', 'Research session started', state.topic, 'running');
      return;
    }

    if (type === 'search_backend_unavailable') {
      state.latestAction = t(
        'research.searchBackendUnavailable',
        null,
        'Search is temporarily unavailable; the result may be partial'
      );
      appendActivity(
        state,
        safeEvent,
        'warning',
        'Search backend unavailable',
        'Planning can continue, but live source collection may be limited.',
        'warning'
      );
      return;
    }

    if (type === 'command_rejected') {
      state.pendingPlanText = '';
      state.controlHoldUntil = 0;
      state.status = 'awaiting_approval';
      state.phase = 'approval';
      state.canApprove = true;
      state.canEdit = true;
      state.canStop = true;
      state.error = data.reason === 'stale_plan_version'
        ? t('research.planChanged', null, 'The plan changed before that action was applied. Review the latest version.')
        : t('research.commandRejected', null, 'The research action could not be applied.');
      state.latestAction = state.error;
      appendActivity(state, safeEvent, 'warning', 'Research action not applied', state.error, 'warning');
      return;
    }

    if (type === 'planning_started' || type === 'plan_started') {
      state.status = 'planning';
      state.phase = 'planning';
      state.latestAction = t('research.preparingPlan', null, 'Preparing the research plan');
      appendActivity(state, safeEvent, 'plan', 'Building the research plan', '', 'running');
      return;
    }

    if ([
      'planning_completed',
      'plan_ready',
      'approval_required',
      'approval_requested',
      'awaiting_approval',
      'plan_revision_proposed'
    ].includes(type)) {
      mergePlan(state, data.plan, data.checklist || data.items || asObject(data.plan).items);
      state.status = type === 'plan_revision_proposed' ? 'awaiting_revision_approval' : 'awaiting_approval';
      state.phase = 'approval';
      state.canApprove = true;
      state.canEdit = true;
      state.canStop = true;
      state.latestAction = type === 'plan_revision_proposed'
        ? t('research.reviewUpdatedPlan', null, 'Review the updated plan')
        : t('research.reviewPlan', null, 'Review the plan before research starts');
      appendActivity(
        state,
        safeEvent,
        'approval',
        type === 'plan_revision_proposed' ? 'Updated plan needs approval' : 'Plan ready for approval',
        `${state.items.length} ${state.items.length === 1 ? 'step' : 'steps'}`,
        'waiting'
      );
      return;
    }

    if (['plan_approved', 'approval_granted', 'research_approved'].includes(type)) {
      state.error = '';
      state.status = 'starting';
      state.phase = 'research';
      state.canApprove = false;
      state.canEdit = true;
      state.canStop = true;
      state.latestAction = t('research.starting', null, 'Starting the approved research plan');
      appendActivity(state, safeEvent, 'approval', 'Plan approved', '', 'done');
      return;
    }

    if (['plan_revised', 'plan_updated', 'revision_applied'].includes(type)) {
      mergePlan(state, data.plan, data.checklist || data.items || asObject(data.plan).items);
      state.pendingPlanText = '';
      const activeRevision = normalizedType(safeEvent.phase) === 'research'
        || Number(safeEvent.iteration || 0) > 0;
      state.status = normalizedStatus(data.status, activeRevision ? 'running' : 'awaiting_approval');
      state.phase = activeRevision ? 'research' : 'approval';
      state.canApprove = !activeRevision;
      state.canEdit = true;
      state.canStop = true;
      state.latestAction = activeRevision
        ? t('research.planUpdated', null, 'Research plan updated')
        : t('research.reviewUpdatedPlan', null, 'Review the updated plan');
      appendActivity(
        state,
        safeEvent,
        'plan',
        'Research plan updated',
        activeRevision ? 'The active research will use the revised checklist.' : 'Review and approve the updated plan.',
        'done'
      );
      return;
    }

    if (type === 'research_started' || type === 'execution_started') {
      state.error = '';
      mergePlan(state, data.plan, data.checklist || data.items || asObject(data.plan).items);
      state.status = 'running';
      state.phase = 'research';
      state.canApprove = false;
      state.canEdit = true;
      state.canStop = true;
      state.latestAction = t('research.collectingEvidence', null, 'Collecting evidence');
      if (state.items.length && !state.items.some(function hasActive(item) { return checklistStatus(item.status) === 'active'; })) {
        state.items[0].status = state.items[0].status === 'done' ? 'done' : 'active';
        state.currentItemId = state.items[0].id;
      }
      appendActivity(state, safeEvent, 'research', 'Research started', '', 'running');
      return;
    }

    if (['checklist_updated', 'plan_checklist_updated'].includes(type)) {
      mergePlan(state, data.plan === undefined ? state.rawPlan : data.plan, data.checklist || data.items);
      if (data.current_item_id || data.currentItemId) {
        state.currentItemId = String(data.current_item_id || data.currentItemId);
      }
      state.latestAction = publicSummary(data) || state.latestAction;
      return;
    }

    if (['plan_item_updated', 'checklist_item_updated', 'task_updated'].includes(type)) {
      updateChecklistItem(state, data);
      state.latestAction = publicSummary(data) || state.latestAction;
      return;
    }

    if (['plan_item_started', 'checklist_item_started', 'task_started'].includes(type)) {
      updateChecklistItem(state, data, 'active');
      const activeItem = state.items.find(function findActive(item) { return item.id === state.currentItemId; });
      state.latestAction = activeItem ? activeItem.title : (publicSummary(data) || 'Working on the next plan step');
      appendActivity(state, safeEvent, 'step', 'Started plan step', activeItem ? activeItem.title : '', 'running');
      return;
    }

    if (['plan_item_completed', 'checklist_item_completed', 'task_completed'].includes(type)) {
      updateChecklistItem(state, data, 'done');
      appendActivity(state, safeEvent, 'step', 'Completed plan step', publicSummary(data), 'done');
      return;
    }

    if (type === 'iteration_started' || type === 'reflection_started') {
      state.status = 'reflecting';
      state.phase = 'reflection';
      state.latestAction = t('research.reflecting', null, 'Reviewing evidence and refining the next queries');
      appendActivity(state, safeEvent, 'reflection', 'Reflecting on the evidence', '', 'running');
      return;
    }

    if (['reflection_completed', 'query_plan_ready'].includes(type)) {
      mergePlan(
        state,
        data.plan === undefined ? state.rawPlan : data.plan,
        data.checklist || data.items
      );
      const summary = publicSummary(data);
      const queries = queryStringsFrom(data);
      state.status = 'running';
      state.phase = 'research';
      state.latestAction = queries.length
        ? `Next queries: ${queries.join(' \u00b7 ')}`
        : (summary || t('research.collectingEvidence', null, 'Collecting evidence'));
      appendActivity(state, safeEvent, 'reflection', 'Evidence review completed', [summary, queries.join(' \u00b7 ')].filter(Boolean).join(' \u2014 '), 'done');
      return;
    }

    if (['queries_selected', 'next_queries_selected'].includes(type)) {
      const queries = queryStringsFrom(data);
      if (queries.length) {
        state.activeQueries = queries;
      }
      state.status = 'running';
      state.phase = 'query_selection';
      state.latestAction = queries.length
        ? `Selected next queries: ${queries.join(' \u00b7 ')}`
        : t('research.collectingEvidence', null, 'Collecting evidence');
      appendActivity(
        state,
        safeEvent,
        'query',
        queries.length === 1 ? 'Next query selected' : 'Next queries selected',
        queries.join(' \u00b7 '),
        'done'
      );
      return;
    }

    if (
      type === 'tool_call'
      || type === 'search_started'
      || type === 'source_read_started'
      || type === 'reading_started'
    ) {
      const toolData = type === 'tool_call' ? data : { ...data, tool_id: data.tool_id || type };
      const action = toolActionFromEvent(safeEvent, toolData);
      const actionQueries = action.kind === 'search' ? queryStringsFrom(toolData) : [];
      if (actionQueries.length) {
        state.activeQueries = actionQueries;
      }
      state.status = 'running';
      state.phase = action.kind === 'read' ? 'reading' : 'research';
      state.latestAction = action.latest;
      if (action.kind === 'search') {
        const selectedQueryCount = queryStringsFrom(data).length;
        state.queriesUsed += Math.max(1, selectedQueryCount);
      }
      appendActivity(state, safeEvent, action.kind, action.title, action.detail, 'running');
      return;
    }

    if (
      type === 'tool_result'
      || type === 'search_completed'
      || type === 'source_read_completed'
      || type === 'reading_completed'
    ) {
      const toolUi = asObject(data.tool_ui || data.toolUi);
      const toolKind = normalizedType(toolUi.kind || data.tool_id || data.toolId);
      const count = sourceCountFrom(data);
      const completedQueries = queryStringsFrom(data);
      const searchQueries = completedQueries.length ? completedQueries : state.activeQueries;
      const title = toolKind.includes('read_page')
        || type === 'source_read_completed'
        || type === 'reading_completed'
        ? 'Source read'
        : (toolKind.includes('search') || type === 'search_completed' ? 'Search completed' : 'Research action completed');
      if (count !== null) {
        state.sourceCount = Math.max(state.sourceCount, count);
      }
      state.status = 'reflecting';
      state.phase = 'reflection';
      state.latestAction = t('research.reflecting', null, 'Reviewing evidence and refining the next queries');
      const searchTitle = searchQueries.length
        ? `${title}: \u201c${searchQueries[0]}\u201d`
        : title;
      const searchDetail = [
        searchQueries.slice(1).join(' \u00b7 '),
        count !== null ? `${count} sources available` : ''
      ].filter(Boolean).join(' \u2014 ');
      appendActivity(
        state,
        safeEvent,
        toolKind.includes('search') || type === 'search_completed' ? 'search' : 'tool',
        toolKind.includes('search') || type === 'search_completed' ? searchTitle : title,
        toolKind.includes('search') || type === 'search_completed' ? searchDetail : (count !== null ? `${count} sources available` : ''),
        'done'
      );
      return;
    }

    if (type === 'checkpoint_saved') {
      mergeSnapshot(state, data, { skipStatus: true, skipPhase: true });
      state.status = 'running';
      state.phase = 'checkpoint';
      state.latestAction = safeEvent.iteration
        ? `Checkpoint ${safeEvent.iteration} saved`
        : 'Research checkpoint saved';
      appendActivity(
        state,
        safeEvent,
        'checkpoint',
        state.latestAction,
        state.sourceCount ? `${state.sourceCount} sources collected` : '',
        'done'
      );
      return;
    }

    if (type === 'tool_activity') {
      // Inner tools can be extremely verbose. Keep one bounded public status only.
      const publicText = publicSummary(data);
      if (publicText) {
        state.latestAction = publicText;
      }
      return;
    }

    if (['synthesis_started', 'report_started', 'writing_report'].includes(type)) {
      state.status = 'synthesizing';
      state.phase = 'synthesis';
      state.latestAction = t('research.writingReport', null, 'Synthesizing the final report');
      appendActivity(state, safeEvent, 'report', 'Writing the research report', '', 'running');
      return;
    }

    if (type === 'report_completed') {
      state.status = 'synthesizing';
      state.phase = 'synthesis';
      state.latestAction = t('research.finalizingReport', null, 'Finalizing the report');
      appendActivity(state, safeEvent, 'report', 'Report completed', state.sourceCount ? `${state.sourceCount} sources` : '', 'done');
      return;
    }

    if (['stop_requested', 'cancellation_requested', 'session_stopping'].includes(type)) {
      state.status = 'stopping';
      state.phase = 'stopping';
      state.canApprove = false;
      state.canEdit = false;
      state.canStop = false;
      state.latestAction = t('research.stopping', null, 'Stopping research safely');
      appendActivity(state, safeEvent, 'stop', 'Stop requested', '', 'running');
      return;
    }

    if (['session_cancelled', 'session_canceled', 'session_stopped'].includes(type)) {
      state.error = '';
      state.status = 'cancelled';
      state.phase = 'done';
      state.canApprove = false;
      state.canEdit = false;
      state.canStop = false;
      state.latestAction = t('research.stopped', null, 'Research stopped');
      appendActivity(state, safeEvent, 'stop', 'Research stopped', publicSummary(data), 'done');
      return;
    }

    if (type === 'session_failed') {
      state.status = 'failed';
      state.phase = 'done';
      state.canApprove = false;
      state.canEdit = false;
      state.canStop = false;
      state.error = compactText(data.public_message || data.message || 'Research failed', 480);
      state.latestAction = state.error;
      appendActivity(state, safeEvent, 'error', 'Research failed', state.error, 'failed');
      return;
    }

    if (type === 'session_expired') {
      state.status = 'expired';
      state.phase = 'done';
      state.canApprove = false;
      state.canEdit = false;
      state.canStop = false;
      state.error = compactText(data.public_message || data.message || 'Plan approval expired', 480);
      state.latestAction = state.error;
      appendActivity(state, safeEvent, 'error', 'Approval window expired', state.error, 'failed');
      return;
    }

    if (type === 'session_completed') {
      state.error = '';
      state.status = normalizedStatus(data.status, 'completed');
      state.phase = 'done';
      state.canApprove = false;
      state.canEdit = false;
      state.canStop = false;
      state.latestAction = state.status === 'partial'
        ? t('research.completedPartial', null, 'Research completed with limitations')
        : t('research.completed', null, 'Research completed');
      appendActivity(state, safeEvent, 'done', state.latestAction, state.sourceCount ? `${state.sourceCount} sources` : '', 'done');
      return;
    }

    if (['state_updated', 'progress_updated', 'research_progress'].includes(type)) {
      mergeSnapshot(state, Object.keys(nestedState).length ? nestedState : data, { skipEvents: true });
      const summary = publicSummary(data);
      if (summary) {
        state.latestAction = summary;
      }
    }
  }

  function ingestTimeline(segments) {
    const safeSegments = Array.isArray(segments) ? segments : [];
    const deepSegments = safeSegments.filter(isDeepResearchToolSegment);
    deepSegments.forEach(function ingestBaseSegment(segment) {
      stateForSegment(segment);
    });

    safeSegments.forEach(function ingestActivitySegment(segment) {
      if (!segment || segment.type !== 'tool_activity') {
        return;
      }
      const outer = asObject(segment.event);
      if (!activityBelongsToDeepResearch(outer)) {
        return;
      }
      flattenActivityPayload(outer).forEach(function ingestOne(entry) {
        const sessionId = sessionIdFrom(entry.event) || entry.meta.session_id;
        let state = stateForIdentity(sessionId, entry.meta.alias, false);
        if (!state && deepSegments.length === 1) {
          state = stateForSegment(deepSegments[0]);
          bindIdentity(state, sessionId, entry.meta.alias);
        }
        if (!state) {
          state = stateForIdentity(sessionId, entry.meta.alias, true);
        }
        applyEvent(state, entry.event, entry.meta);
      });
    });

    // A terminal tool result is authoritative and must win over replayed progress.
    deepSegments.forEach(function ingestTerminalSegment(segment) {
      const state = stateForSegment(segment);
      const ui = deepResearchUiPayload(segment);
      if (segment.result !== null && segment.result !== undefined && statusIsTerminal(ui.status)) {
        state.status = normalizedStatus(ui.status);
      }
      ensurePolling(state);
    });

    syncOpenInspector();
  }

  function renderChecklist(items, limit, compact) {
    const safeItems = Array.isArray(items) ? items : [];
    const visibleItems = Number.isFinite(Number(limit)) ? safeItems.slice(0, Number(limit)) : safeItems;
    if (!visibleItems.length) {
      return `
        <div class="deep-research-plan-empty">
          <span class="deep-research-spinner" aria-hidden="true"></span>
          <span>${escHtml(t('research.preparingPlan', null, 'Preparing the research plan'))}</span>
        </div>
      `;
    }
    const rows = visibleItems.map(function renderItem(item) {
      const status = checklistStatus(item.status);
      return `
        <li class="deep-research-check-item is-${escapeAttributeValue(status)}" data-plan-item-id="${escapeAttributeValue(item.id)}">
          <span class="deep-research-check-mark" aria-hidden="true"></span>
          <span class="deep-research-check-copy">
            <span class="deep-research-check-title">${escHtml(item.title)}</span>
            ${!compact && item.note ? `<span class="deep-research-check-note">${escHtml(item.note)}</span>` : ''}
          </span>
        </li>
      `;
    }).join('');
    const remaining = Math.max(0, safeItems.length - visibleItems.length);
    return `<ol class="deep-research-checklist${compact ? ' is-compact' : ''}">${rows}${remaining ? `<li class="deep-research-check-more">+${remaining} more</li>` : ''}</ol>`;
  }

  function actionButtons(state, location) {
    const key = escapeAttributeValue(state.key);
    const disabled = state.pendingAction ? ' disabled aria-disabled="true"' : '';
    const buttons = [];
    if (stateCanEdit(state) && state.sessionId) {
      const editLabel = stateCanApprove(state)
        ? t('research.editPlan', null, 'Edit plan')
        : t('research.updatePlan', null, 'Update plan');
      buttons.push(`<button type="button" class="deep-research-btn deep-research-btn--secondary is-edit-action" data-deep-research-action="edit" data-research-key="${key}"${disabled}>${escHtml(editLabel)}</button>`);
    }
    if (stateCanStop(state) && state.sessionId) {
      const stopLabel = stateCanApprove(state)
        ? t('research.cancel', null, 'Cancel')
        : t('research.stop', null, 'Stop');
      buttons.push(`<button type="button" class="deep-research-btn deep-research-btn--danger${location === 'card' ? ' is-compact' : ''}" data-deep-research-action="stop" data-research-key="${key}"${disabled}>${escHtml(stopLabel)}</button>`);
    }
    if (stateCanApprove(state)) {
      buttons.push(`<button type="button" class="deep-research-btn deep-research-btn--primary" data-deep-research-action="approve" data-research-key="${key}"${disabled}>${escHtml(t('research.approve', null, 'Approve & start'))}</button>`);
    }
    return buttons.join('');
  }

  function renderCardFromState(state, toolSegmentIndex) {
    const key = escapeAttributeValue(state.key);
    const sessionAttr = state.sessionId ? ` data-research-session-id="${escapeAttributeValue(state.sessionId)}"` : '';
    const indexAttr = Number.isInteger(toolSegmentIndex) ? ` data-tool-segment-index="${toolSegmentIndex}"` : '';
    const pending = state.pendingAction
      ? `<span class="deep-research-card-pending"><span class="deep-research-spinner" aria-hidden="true"></span>${escHtml(pendingActionLabel(state.pendingAction))}</span>`
      : '';
    const awaitingApproval = stateCanApprove(state);
    const active = stateCanStop(state) && !awaitingApproval;
    const topic = state.topic || t('research.title', null, 'Deep Research');
    const cardActions = awaitingApproval ? actionButtons(state, 'card') : '';
    const activityLabel = active
      ? statusLabel(state.status)
      : (state.latestAction || statusLabel(state.status));
    const activityControl = `
      <button type="button" class="deep-research-card-activity" data-deep-research-action="open" data-research-key="${key}">
        <span class="deep-research-card-activity-label">${escHtml(activityLabel)}</span>
      </button>
    `;
    const ariaLabel = `${t('research.title', null, 'Deep Research')}. ${statusLabel(state.status)}. ${state.topic || state.latestAction}`;
    return `
      <section class="msg-deep-research-card is-${escapeAttributeValue(stateCssClass(state.status))}${state.pendingAction ? ' is-busy' : ''}" data-research-key="${key}"${sessionAttr}${indexAttr} role="group" tabindex="0" aria-label="${escapeAttributeValue(ariaLabel)}" aria-busy="${state.pendingAction ? 'true' : 'false'}">
        <div class="deep-research-card-head">
          <h3 class="deep-research-card-topic">${escHtml(compactText(topic, 220))}</h3>
        </div>
        <div class="deep-research-card-plan">${renderChecklist(state.items, MAX_CARD_ITEMS, true)}</div>
        ${!awaitingApproval ? `<div class="deep-research-card-run-row">${activityControl}${active && state.sessionId ? `<button type="button" class="deep-research-stop-button" data-deep-research-action="stop" data-research-key="${key}" aria-label="${escapeAttributeValue(t('research.stop', null, 'Stop research'))}"${state.pendingAction ? ' disabled aria-disabled="true"' : ''}><span aria-hidden="true"></span></button>` : ''}</div>` : ''}
        ${state.error && !statusIsTerminal(state.status) ? `<div class="deep-research-inline-error" role="alert">${escHtml(state.error)}</div>` : ''}
        ${pending || cardActions ? `<div class="deep-research-card-actions">${pending}${cardActions}</div>` : ''}
      </section>
    `;
  }

  function renderCard(segment, toolSegmentIndex) {
    return renderCardFromState(stateForSegment(segment), toolSegmentIndex);
  }

  function activityTimeLabel(value) {
    if (!value) {
      return '';
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return '';
    }
    try {
      return new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(date);
    } catch (_error) {
      return '';
    }
  }

  function renderActivityLog(state) {
    if (!state.activity.length) {
      return `<div class="deep-research-activity-empty">${escHtml(t('research.activityPending', null, 'Public research actions will appear here.'))}</div>`;
    }
    return `<ol class="deep-research-activity-list">${state.activity.map(function renderActivity(item) {
      const time = activityTimeLabel(item.timestamp);
      return `
        <li class="deep-research-activity-item is-${escapeAttributeValue(item.kind)} is-${escapeAttributeValue(item.status)}">
          <span class="deep-research-activity-marker" aria-hidden="true"></span>
          <span class="deep-research-activity-copy">
            <span class="deep-research-activity-title">${escHtml(item.title)}</span>
            ${item.detail ? `<span class="deep-research-activity-detail">${escHtml(item.detail)}</span>` : ''}
          </span>
          ${time ? `<time class="deep-research-activity-time">${escHtml(time)}</time>` : ''}
        </li>
      `;
    }).join('')}</ol>`;
  }

  function inspectorBody(state) {
    return `
      <div class="deep-research-inspector-view">
        <section class="deep-research-inspector-section" aria-labelledby="deepResearchActivityHeading">
          <div class="deep-research-section-head">
            <h3 id="deepResearchActivityHeading">${escHtml(t('research.activity', null, 'Public activity'))}</h3>
          </div>
          ${renderActivityLog(state)}
        </section>
        ${state.report ? `<section class="deep-research-inspector-section" aria-labelledby="deepResearchReportHeading"><div class="deep-research-section-head"><h3 id="deepResearchReportHeading">${escHtml(t('research.report', null, 'Research report'))}</h3></div><div class="deep-research-recovered-report">${escHtml(state.report)}</div></section>` : ''}
        ${state.error ? `<div class="deep-research-inspector-error" role="alert">${escHtml(state.error)}</div>` : ''}
      </div>
    `;
  }

  function inspectorFooter(state) {
    const controls = actionButtons(state, 'inspector');
    return controls
      ? `<div class="deep-research-inspector-actions">${controls}</div>`
      : '';
  }

  function openState(state, edit) {
    toolInspector.openResearch({
      key: state.key,
      title: compactText(state.topic || t('research.title', null, 'Deep Research'), 90),
      bodyHtml: inspectorBody(state),
      footerHtml: inspectorFooter(state)
    });
    if (edit) {
      beginEdit(state.key);
    }
    ensurePolling(state, 0);
  }

  function openSegment(segment, edit) {
    openState(stateForSegment(segment), edit === true);
  }

  function openByKey(key, edit) {
    const state = states.get(String(key || '').trim());
    if (state) {
      openState(state, edit === true);
    }
  }

  function syncOpenInspector() {
    const key = toolInspector.getOpenResearchKey();
    if (!key || toolInspector.isResearchEditing()) {
      return;
    }
    const state = states.get(key);
    if (!state) {
      return;
    }
    toolInspector.updateResearch({
      key: state.key,
      title: compactText(state.topic || t('research.title', null, 'Deep Research'), 90),
      bodyHtml: inspectorBody(state),
      footerHtml: inspectorFooter(state)
    });
  }

  function refreshRenderedCards(state) {
    const selector = `.msg-deep-research-card[data-research-key="${escapeCssAttributeValue(state.key)}"]`;
    document.querySelectorAll(selector).forEach(function refreshCard(card) {
      const index = parseInt(card.getAttribute('data-tool-segment-index') || '-1', 10);
      const replacement = $(renderCardFromState(state, Number.isInteger(index) && index >= 0 ? index : undefined))[0];
      if (replacement && card.parentNode) {
        card.parentNode.replaceChild(replacement, card);
      }
    });
    syncOpenInspector();
  }

  function beginEdit(key) {
    const state = states.get(String(key || '').trim());
    if (!state || !state.sessionId) {
      return;
    }
    if (toolInspector.getOpenResearchKey() !== state.key) {
      openState(state, false);
    }
    state.editingPlanVersion = state.planVersion;
    toolInspector.setResearchEditing(true, state.rawPlan || state.items.map(function planLine(item) {
      return `- ${item.title}`;
    }).join('\n'));
  }

  function cancelEdit() {
    const state = states.get(toolInspector.getOpenResearchKey());
    if (state) {
      state.editingPlanVersion = null;
    }
    toolInspector.setResearchEditing(false);
    syncOpenInspector();
  }

  function responseSnapshot(response) {
    const safeResponse = asObject(response);
    return asObject(safeResponse.state || safeResponse.snapshot || safeResponse.research || safeResponse.session);
  }

  function stopPolling(state) {
    if (!state) {
      return;
    }
    if (pollTimers.has(state.key)) {
      const timer = pollTimers.get(state.key);
      window.clearTimeout(timer);
      pollTimers.delete(state.key);
    }
  }

  function pollingDelay(state) {
    return stateCanApprove(state)
      ? APPROVAL_POLL_INTERVAL_MS
      : ACTIVE_POLL_INTERVAL_MS;
  }

  function snapshotSequence(snapshot) {
    const numeric = Number(asObject(snapshot).last_sequence ?? asObject(snapshot).lastSequence);
    return Number.isFinite(numeric) && numeric >= 0 ? Math.floor(numeric) : 0;
  }

  async function pollState(state) {
    if (!state || !state.sessionId || statusIsTerminal(state.status) || pollsInFlight.has(state.key)) {
      stopPolling(state);
      return;
    }
    pollsInFlight.add(state.key);
    try {
      const response = await getJson(`${CONTROL_ENDPOINT}?session_id=${encodeURIComponent(state.sessionId)}`);
      const snapshot = responseSnapshot(response);
      if (Object.keys(snapshot).length) {
        const snapshotIsNewer = snapshotSequence(snapshot) > state.lastSequence;
        const snapshotHasNewerPlan = (planVersionFrom(snapshot) ?? 0) > state.planVersion;
        const preserveOptimisticControl = Date.now() < state.controlHoldUntil && !snapshotIsNewer;
        mergeSnapshot(state, snapshot, {
          forceStatus: !preserveOptimisticControl,
          skipLatestAction: preserveOptimisticControl,
          skipPlan: !!state.pendingPlanText && !snapshotHasNewerPlan,
          skipPhase: preserveOptimisticControl,
          skipStatus: preserveOptimisticControl
        });
        if (snapshotHasNewerPlan || statusIsTerminal(state.status)) {
          state.pendingPlanText = '';
        }
        if (snapshotIsNewer || statusIsTerminal(state.status)) {
          state.controlHoldUntil = 0;
        }
        state.pollFailures = 0;
        refreshRenderedCards(state);
      }
    } catch (_error) {
      // Streaming events remain primary. A transient snapshot read must not fail the card.
      state.pollFailures += 1;
    } finally {
      pollsInFlight.delete(state.key);
      if (statusIsTerminal(state.status)) {
        stopPolling(state);
        return;
      }
      const selector = `.msg-deep-research-card[data-research-key="${escapeCssAttributeValue(state.key)}"]`;
      const isVisible = !!document.querySelector(selector)
        || toolInspector.getOpenResearchKey() === state.key;
      if (isVisible && state.pollFailures < 12) {
        ensurePolling(state, pollingDelay(state));
      }
    }
  }

  function ensurePolling(state, delay) {
    if (!state || !state.sessionId || statusIsTerminal(state.status)) {
      stopPolling(state);
      return;
    }
    if (pollTimers.has(state.key) || pollsInFlight.has(state.key)) {
      return;
    }
    const waitMs = Number.isFinite(Number(delay)) ? Math.max(0, Number(delay)) : pollingDelay(state);
    const timer = window.setTimeout(function runResearchPoll() {
      pollTimers.delete(state.key);
      pollState(state);
    }, waitMs);
    pollTimers.set(state.key, timer);
  }

  async function submitControl(key, uiAction, plan) {
    const state = states.get(String(key || '').trim());
    if (!state || !state.sessionId || state.pendingAction) {
      return;
    }
    const actionMap = {
      approve: 'approve',
      edit: 'revise',
      stop: 'cancel'
    };
    const action = actionMap[uiAction] || uiAction;
    state.pendingAction = uiAction;
    state.controlHoldUntil = Date.now() + 2500;
    state.error = '';
    refreshRenderedCards(state);

    const payload = {
      session_id: state.sessionId,
      action,
      expected_plan_version: action === 'revise' && state.editingPlanVersion !== null
        ? state.editingPlanVersion
        : state.planVersion
    };
    if (action === 'revise') {
      payload.plan = String(plan || '').trim();
      if (!payload.plan) {
        state.pendingAction = '';
        state.controlHoldUntil = 0;
        state.error = t('research.planRequired', null, 'The research plan cannot be empty.');
        refreshRenderedCards(state);
        toolInspector.showResearchError(state.error);
        return;
      }
    }

    try {
      const response = await postJson(CONTROL_ENDPOINT, payload);
      const snapshot = responseSnapshot(response);
      if (Object.keys(snapshot).length) {
        mergeSnapshot(state, snapshot);
      }
      toolInspector.showResearchError('');
      if (action === 'approve') {
        state.status = 'starting';
        state.phase = 'research';
        state.latestAction = t('research.starting', null, 'Starting the approved research plan');
        appendActivity(state, { type: 'ui_command', timestamp: new Date().toISOString() }, 'approval', 'Approval sent', '', 'done');
      } else if (action === 'revise') {
        state.rawPlan = payload.plan;
        state.pendingPlanText = payload.plan;
        state.editingPlanVersion = null;
        mergePlan(state, payload.plan);
        state.status = 'revising';
        state.phase = 'approval';
        state.latestAction = t('research.applyingChanges', null, 'Applying plan changes');
        appendActivity(state, { type: 'ui_command', timestamp: new Date().toISOString() }, 'plan', 'Plan changes submitted', '', 'running');
        toolInspector.setResearchEditing(false);
      } else if (action === 'cancel') {
        state.status = 'stopping';
        state.phase = 'stopping';
        state.latestAction = t('research.stopping', null, 'Stopping research safely');
        appendActivity(state, { type: 'ui_command', timestamp: new Date().toISOString() }, 'stop', 'Stop requested', '', 'running');
      }
      stopPolling(state);
      ensurePolling(state, 180);
    } catch (error) {
      const data = asObject(error && error.data);
      const snapshot = responseSnapshot(data);
      if (Object.keys(snapshot).length) {
        mergeSnapshot(state, snapshot, { forceStatus: true });
      }
      state.error = compactText(
        data.error || (error && error.message) || t('errors.generic', null, 'Something went wrong'),
        520
      );
      state.controlHoldUntil = 0;
      state.pendingPlanText = '';
      toolInspector.showResearchError(state.error);
    } finally {
      state.pendingAction = '';
      refreshRenderedCards(state);
    }
  }

  function handleAction($button) {
    const button = $button && $button.jquery ? $button : $($button);
    const key = String(button.attr('data-research-key') || '').trim();
    const action = String(button.attr('data-deep-research-action') || '').trim();
    if (!key || !action) {
      return Promise.resolve();
    }
    if (action === 'open') {
      openByKey(key, false);
      return Promise.resolve();
    }
    if (action === 'edit') {
      beginEdit(key);
      return Promise.resolve();
    }
    return submitControl(key, action);
  }

  function saveEdit() {
    const key = toolInspector.getOpenResearchKey();
    const plan = toolInspector.getResearchEditorValue();
    return submitControl(key, 'edit', plan);
  }

  return {
    cancelEdit,
    handleAction,
    ingestTimeline,
    isDeepResearchSegment: isDeepResearchToolSegment,
    openByKey,
    openSegment,
    renderCard,
    saveEdit,
    syncOpenInspector
  };
}
