// Copyright NGGT.LightKeeper. All Rights Reserved.

import { getCsrfToken, getJson, postJson } from '../main/api.js';
import { t } from '../main/i18n.js';
import { escHtml, escapeAttributeValue } from '../main/utils.js';

const CONTROL_ENDPOINT = '/api/deep-research/control/';
const EXPORT_ENDPOINT = '/api/deep-research/export/';
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
const PLAN_MUTATING_EVENT_TYPES = new Set([
  'session_started',
  'planning_started',
  'plan_started',
  'planning_completed',
  'plan_ready',
  'approval_required',
  'approval_requested',
  'awaiting_approval',
  'plan_revision_proposed',
  'plan_approved',
  'approval_granted',
  'research_approved',
  'plan_revised',
  'plan_updated',
  'revision_applied',
  'research_started',
  'execution_started',
  'checklist_updated',
  'plan_checklist_updated',
  'plan_item_updated',
  'checklist_item_updated',
  'task_updated',
  'plan_item_started',
  'checklist_item_started',
  'task_started',
  'plan_item_completed',
  'checklist_item_completed',
  'task_completed',
  'reflection_completed',
  'query_plan_ready'
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

function normalizedInlineText(value) {
  return String(value === null || value === undefined ? '' : value)
    .replace(/\s+/g, ' ')
    .trim();
}

// Keep public reasoning readable without cutting a completed sentence in half.
// If the first sentence is unusually long, allow a modest overflow before
// falling back to a word boundary.
function sentenceAwarePreview(value, limit) {
  const text = normalizedInlineText(value);
  const targetLength = Math.max(96, Number(limit) || 280);
  if (text.length <= targetLength) {
    return { text, truncated: false };
  }

  const hardLength = Math.min(text.length, targetLength + 220);
  const sentencePattern = /[.!?\u2026]+(?:["'\u2019\u201d)\]]+)?(?=\s|$)/g;
  let match;
  let boundaryBeforeTarget = 0;
  let boundaryAfterTarget = 0;
  while ((match = sentencePattern.exec(text)) !== null) {
    const boundary = match.index + match[0].length;
    if (boundary <= targetLength) {
      boundaryBeforeTarget = boundary;
      continue;
    }
    if (boundary <= hardLength) {
      boundaryAfterTarget = boundary;
    }
    break;
  }

  const sentenceBoundary = boundaryBeforeTarget >= Math.min(96, Math.floor(targetLength * 0.4))
    ? boundaryBeforeTarget
    : boundaryAfterTarget;
  if (sentenceBoundary > 0) {
    return {
      text: text.slice(0, sentenceBoundary).trimEnd(),
      truncated: sentenceBoundary < text.length
    };
  }

  const candidate = text.slice(0, targetLength + 1);
  const wordBoundary = candidate.lastIndexOf(' ');
  const end = wordBoundary >= Math.floor(targetLength * 0.65) ? wordBoundary : targetLength;
  return {
    text: `${text.slice(0, end).trimEnd()}\u2026`,
    truncated: true
  };
}

function boundedActivityDetail(value) {
  const text = normalizedInlineText(value);
  if (text.length <= 2400) {
    return text;
  }
  const bounded = sentenceAwarePreview(text, 2180);
  return bounded.truncated && !bounded.text.endsWith('\u2026')
    ? `${bounded.text} \u2026`
    : bounded.text;
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
  const previousCandidates = Array.isArray(previousItems) ? previousItems : [];
  const normalizedTitle = title.replace(/\s+/g, ' ').trim().toLowerCase();
  const titleMatches = previousCandidates.filter(function matchPreviousTitle(candidate) {
    const candidateTitle = String(candidate && candidate.title || '').replace(/\s+/g, ' ').trim().toLowerCase();
    return candidateTitle && candidateTitle === normalizedTitle;
  });
  const idMatch = previousCandidates.find(function matchPreviousId(candidate) {
    return candidate && candidate.id === id;
  });
  const idMatchTitle = String(idMatch && idMatch.title || '').replace(/\s+/g, ' ').trim().toLowerCase();
  // Generated ids such as s1 are positional and are routinely reused after a
  // plan revision. Only inherit completion when the goal itself is unchanged;
  // an ambiguous duplicate title or a renamed replacement must start hollow.
  const previous = idMatch && idMatchTitle === normalizedTitle
    ? idMatch
    : (titleMatches.length === 1 ? titleMatches[0] : null);
  const incomingStatus = normalizedStatus(
    safeItem.status || safeItem.state || (previous && previous.status),
    'pending'
  );
  return {
    id,
    title,
    status: previous && checklistStatus(previous.status) === 'done' ? 'done' : incomingStatus,
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

function readUrlStringsFrom(value) {
  const rawValues = Array.isArray(value) ? value : [value];
  return rawValues.flatMap(function normalizeReadUrl(rawValue) {
    return String(rawValue === null || rawValue === undefined ? '' : rawValue)
      .split(/\s*(?:\u00b7|,|\n)\s*(?=https?:\/\/)/i)
      .map(function trimReadUrl(url) { return url.trim(); })
      .filter(function validReadUrl(url) { return /^https?:\/\//i.test(url); });
  });
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
    const candidate = candidates[index];
    if (candidate === null || candidate === undefined || String(candidate).trim() === '') {
      continue;
    }
    const numeric = Number(candidate);
    if (Number.isFinite(numeric) && numeric >= 0) {
      return Math.floor(numeric);
    }
  }
  const sources = payload.sources || data.sources || structured.sources;
  return Array.isArray(sources) ? sources.length : null;
}

function sourcesFrom(value) {
  const payload = asObject(value);
  const data = asObject(payload.data);
  const structured = asObject(payload.structured_content || payload.structuredContent);
  const candidates = [payload.sources, data.sources, structured.sources];
  const sources = candidates.find(Array.isArray) || [];
  return sources.filter(function keepSource(source) {
    return source && typeof source === 'object';
  }).map(function copySource(source) {
    return { ...source };
  });
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
  if (normalized === 'completed' || normalized === 'done' || normalized === 'skipped') {
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
  if (normalizedType(state.pendingAction) === 'stop') {
    return false;
  }
  return typeof state.canApprove === 'boolean'
    ? state.canApprove
    : statusCanApprove(state.status);
}

function stateCanEdit(state) {
  if (normalizedType(state.pendingAction) === 'stop') {
    return false;
  }
  return typeof state.canEdit === 'boolean'
    ? state.canEdit
    : statusCanEdit(state.status);
}

function stateCanStop(state) {
  if (normalizedType(state.pendingAction) === 'stop' || !statusCanStop(state.status)) {
    return false;
  }
  return typeof state.canStop === 'boolean' ? state.canStop : true;
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
    searches: [],
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
  const icons = asObject(context && context.icons);
  const states = new Map();
  const aliasToKey = new Map();
  const sessionToKey = new Map();
  const pollTimers = new Map();
  const pollsInFlight = new Set();
  let renderCanonicalSearch = null;
  let renderCanonicalReport = null;
  let hydrateCanonicalReport = null;

  function setCanonicalRenderers(renderers) {
    const safeRenderers = asObject(renderers);
    renderCanonicalSearch = typeof safeRenderers.search === 'function' ? safeRenderers.search : null;
    renderCanonicalReport = typeof safeRenderers.report === 'function' ? safeRenderers.report : null;
    hydrateCanonicalReport = typeof safeRenderers.hydrate === 'function' ? safeRenderers.hydrate : null;
    syncOpenInspector();
  }

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
    const version = planVersionFrom(safeSnapshot);
    const planSnapshotIsCurrent = version === null || version >= state.planVersion;
    if (!mergeOptions.skipPlan && planSnapshotIsCurrent) {
      mergePlan(
        state,
        safeSnapshot.plan,
        safeSnapshot.checklist || safeSnapshot.items || asObject(safeSnapshot.plan).items
      );
    }
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
    if (planSnapshotIsCurrent && (safeSnapshot.current_item_id || safeSnapshot.currentItemId)) {
      state.currentItemId = String(safeSnapshot.current_item_id || safeSnapshot.currentItemId);
    }
    if (planSnapshotIsCurrent && (safeSnapshot.latest_action || safeSnapshot.latestAction) && !mergeOptions.skipLatestAction) {
      state.latestAction = compactText(safeSnapshot.latest_action || safeSnapshot.latestAction, 320);
    }
    if (planSnapshotIsCurrent && (typeof safeSnapshot.can_approve === 'boolean' || typeof safeSnapshot.canApprove === 'boolean')) {
      state.canApprove = Boolean(safeSnapshot.can_approve ?? safeSnapshot.canApprove);
    }
    if (planSnapshotIsCurrent && (typeof safeSnapshot.can_edit === 'boolean' || typeof safeSnapshot.canEdit === 'boolean')) {
      state.canEdit = Boolean(safeSnapshot.can_edit ?? safeSnapshot.canEdit);
    }
    if (planSnapshotIsCurrent && (typeof safeSnapshot.can_stop === 'boolean' || typeof safeSnapshot.canStop === 'boolean')) {
      state.canStop = Boolean(safeSnapshot.can_stop ?? safeSnapshot.canStop);
    }
    const snapshotError = safeSnapshot.error || safeSnapshot.public_error || safeSnapshot.publicError;
    if (planSnapshotIsCurrent && snapshotError) {
      state.error = compactText(snapshotError, 520);
    }
    const snapshotReport = safeSnapshot.report || safeSnapshot.model_context || safeSnapshot.modelContext;
    if (planSnapshotIsCurrent && snapshotReport) {
      state.report = String(snapshotReport).trim();
    }
    if (Array.isArray(safeSnapshot.sources)) {
      state.sources = mergeSearchSources(state.sources, safeSnapshot.sources).slice(0, 50);
    }
    if (planSnapshotIsCurrent && safeSnapshot.phase && !mergeOptions.skipPhase) {
      state.phase = normalizedType(safeSnapshot.phase);
    }
    if (planSnapshotIsCurrent && safeSnapshot.status && !mergeOptions.skipStatus) {
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
      detail: boundedActivityDetail(detail),
      status: normalizedType(status) || 'done',
      timestamp
    });
    if (state.activity.length > MAX_ACTIVITY_ITEMS) {
      state.activity.splice(0, state.activity.length - MAX_ACTIVITY_ITEMS);
    }
  }

  function searchIteration(event) {
    const safeEvent = asObject(event);
    const data = asObject(safeEvent.data);
    const numeric = Number(safeEvent.iteration ?? data.iteration);
    return Number.isFinite(numeric) && numeric > 0 ? Math.floor(numeric) : 0;
  }

  function searchQueryKey(queries) {
    return (Array.isArray(queries) ? queries : [])
      .map(function normalizeQuery(query) {
        return String(query || '').replace(/\s+/g, ' ').trim().toLowerCase();
      })
      .filter(Boolean)
      .join('\u241f');
  }

  function mergeSearchSources(existing, incoming) {
    const merged = [];
    const seen = new Set();
    [...(Array.isArray(existing) ? existing : []), ...(Array.isArray(incoming) ? incoming : [])]
      .forEach(function appendSource(source) {
        if (!source || typeof source !== 'object') {
          return;
        }
        const key = String(
          source.url || source.link || source.href || source.source_id || source.id
          || source.domain || source.display_domain || ''
        ).trim().toLowerCase();
        if (!key || seen.has(key)) {
          return;
        }
        seen.add(key);
        merged.push({ ...source });
      });
    return merged;
  }

  function upsertSearch(state, event, queries, status, sources) {
    const safeQueries = (Array.isArray(queries) ? queries : [])
      .map(function cleanQuery(query) { return compactText(query, 360); })
      .filter(Boolean);
    const iteration = searchIteration(event);
    const queryKey = searchQueryKey(safeQueries);
    let search = iteration
      ? state.searches.find(function matchIteration(candidate) {
        return candidate.iteration === iteration;
      })
      : null;
    if (!search && queryKey) {
      search = state.searches.find(function matchQueries(candidate) {
        return candidate.queryKey === queryKey;
      });
    }
    if (!search && normalizedType(status) !== 'running') {
      search = [...state.searches].reverse().find(function latestPending(candidate) {
        return candidate.status === 'running';
      });
    }
    if (!search) {
      const sequence = Number(asObject(event).sequence);
      search = {
        key: iteration
          ? `iteration-${iteration}`
          : (queryKey ? `query-${queryKey}` : `search-${Number.isFinite(sequence) ? sequence : state.searches.length + 1}`),
        iteration,
        queries: [],
        queryKey: '',
        sources: [],
        status: 'running',
        timestamp: String(asObject(event).timestamp || '')
      };
      state.searches.push(search);
    }
    if (safeQueries.length) {
      search.queries = safeQueries;
      search.queryKey = queryKey;
    }
    search.status = normalizedType(status) || search.status;
    search.sources = mergeSearchSources(search.sources, sources);
    if (state.searches.length > 24) {
      state.searches.splice(0, state.searches.length - 24);
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
    if (
      toolId.includes('read_page')
      || toolId.includes('read_url')
      || toolId.includes('reading_started')
      || toolId.includes('source_read_started')
    ) {
      const readUrls = readUrlStringsFrom(
        args.url || args.urls || safeData.url || safeData.urls
      );
      const url = queries[0] || compactText(readUrls.join(' \u00b7 '), 600);
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
    return boundedActivityDetail(
      safeData.public_summary
      || safeData.publicSummary
      || safeData.summary
      || safeData.status_message
      || ''
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
    const stalePlanEvent = version !== null && version < state.planVersion;
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
    if (stalePlanEvent && PLAN_MUTATING_EVENT_TYPES.has(type)) {
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
      const activeIndex = state.items.findIndex(function findActiveIndex(item) {
        const candidate = asObject(data.item);
        const id = String(data.id || data.item_id || candidate.id || candidate.item_id || state.currentItemId || '').trim();
        return id && item.id === id;
      });
      const activeItem = activeIndex >= 0 ? state.items[activeIndex] : null;
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
        upsertSearch(state, safeEvent, actionQueries, 'running', []);
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
      const isReadResult = toolKind.includes('read_page')
        || type === 'source_read_completed'
        || type === 'reading_completed';
      const title = isReadResult
        ? 'Source read'
        : (toolKind.includes('search') || type === 'search_completed' ? 'Search completed' : 'Research action completed');
      if (count !== null) {
        state.sourceCount = Math.max(state.sourceCount, count);
      }
      const isSearchResult = toolKind.includes('search') || type === 'search_completed';
      if (isSearchResult) {
        upsertSearch(state, safeEvent, searchQueries, 'done', sourcesFrom(data));
      }
      state.status = 'reflecting';
      state.phase = 'reflection';
      state.latestAction = t('research.reflecting', null, 'Reviewing evidence and refining the next queries');
      const searchTitle = searchQueries.length
        ? `${title}: \u201c${searchQueries[0]}\u201d`
        : title;
      const searchDetail = [
        searchQueries.slice(1).join(' \u00b7 ')
      ].filter(Boolean).join(' \u2014 ');
      const readUrls = readUrlStringsFrom(data.urls || data.url);
      const previousActivity = state.activity[state.activity.length - 1];
      const readDetail = readUrls.join(' \u00b7 ')
        || (previousActivity && previousActivity.kind === 'read' ? previousActivity.detail : '');
      appendActivity(
        state,
        safeEvent,
        isSearchResult ? 'search' : (isReadResult ? 'read' : 'tool'),
        isSearchResult ? searchTitle : title,
        isSearchResult ? searchDetail : (isReadResult ? readDetail : ''),
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
        '',
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
      appendActivity(state, safeEvent, 'report', 'Report completed', '', 'done');
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
      appendActivity(state, safeEvent, 'done', state.latestAction, '', 'done');
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

  function renderChecklist(items, limit, compact, forceComplete) {
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
    let lastDoneIndex = forceComplete ? safeItems.length - 1 : -1;
    if (!forceComplete) {
      safeItems.forEach(function findLastDone(item, index) {
        if (item && checklistStatus(item.status) === 'done') {
          lastDoneIndex = index;
        }
      });
    }
    const rows = visibleItems.map(function renderItem(item, index) {
      // The plan is ordered visually: if a later goal is complete, earlier
      // circles render filled as well, without mutating the evidence state.
      const status = index <= lastDoneIndex ? 'done' : 'pending';
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

  function renderDownloadMenu(state, compact) {
    if (!state.sessionId || !state.report) {
      return '';
    }
    const key = escapeAttributeValue(state.key);
    const downloadIcon = icons.DOWNLOAD_FILE_ICON || `
      <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3v12m0 0 4-4m-4 4-4-4M5 19h14" stroke-linecap="round" stroke-linejoin="round"></path>
      </svg>`;
    return `
      <details class="deep-research-download-menu${compact ? ' is-compact' : ''}">
        <summary aria-label="${escapeAttributeValue(t('common.download', null, 'Download'))}" title="${escapeAttributeValue(t('common.download', null, 'Download'))}">${downloadIcon}</summary>
        <div class="deep-research-download-popover" role="menu">
          <button type="button" role="menuitem" data-deep-research-action="download" data-research-format="md" data-research-key="${key}">Markdown (.md)</button>
          <button type="button" role="menuitem" data-deep-research-action="download" data-research-format="pdf" data-research-key="${key}">PDF (.pdf)</button>
          <button type="button" role="menuitem" data-deep-research-action="download" data-research-format="docx" data-research-key="${key}">Word (.docx)</button>
        </div>
      </details>
    `;
  }

  function renderReportHtml(state) {
    return state.report && renderCanonicalReport
      ? renderCanonicalReport(state.report, state.sources)
      : '';
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
    const sourceCountLabel = state.sourceCount > 0
      ? `${state.sourceCount} ${state.sourceCount === 1 ? 'source' : 'sources'}`
      : '';
    const activityControl = `
      <button type="button" class="deep-research-card-activity" data-deep-research-action="open" data-research-key="${key}">
        <span class="deep-research-card-activity-label">${escHtml(activityLabel)}</span>
        ${sourceCountLabel ? `<span class="deep-research-card-source-count">${escHtml(sourceCountLabel)}</span>` : ''}
      </button>
    `;
    const ariaLabel = `${t('research.title', null, 'Deep Research')}. ${statusLabel(state.status)}. ${state.topic || state.latestAction}`;
    const reportHtml = renderReportHtml(state);
    if (reportHtml && statusIsTerminal(state.status)) {
      return `
        <section class="msg-deep-research-card deep-research-report-card is-${escapeAttributeValue(stateCssClass(state.status))}" data-research-key="${key}"${sessionAttr}${indexAttr} role="group" tabindex="0" aria-label="${escapeAttributeValue(ariaLabel)}">
          <div class="deep-research-report-card-head">
            <h3 class="deep-research-card-topic">${escHtml(compactText(topic, 220))}</h3>
            ${renderDownloadMenu(state, true)}
          </div>
          <div class="deep-research-report-preview" data-deep-research-action="open-report" data-research-key="${key}" role="button" tabindex="0" aria-label="Open full research report">
            <span class="markdown-body">${reportHtml}</span>
          </div>
        </section>
      `;
    }
    return `
      <section class="msg-deep-research-card is-${escapeAttributeValue(stateCssClass(state.status))}${state.pendingAction ? ' is-busy' : ''}" data-research-key="${key}"${sessionAttr}${indexAttr} role="group" tabindex="0" aria-label="${escapeAttributeValue(ariaLabel)}" aria-busy="${state.pendingAction ? 'true' : 'false'}">
        <div class="deep-research-card-head">
          <h3 class="deep-research-card-topic">${escHtml(compactText(topic, 220))}</h3>
        </div>
        <div class="deep-research-card-plan">${renderChecklist(state.items, MAX_CARD_ITEMS, true, normalizedStatus(state.status) === 'completed')}</div>
        ${!awaitingApproval ? `<div class="deep-research-card-run-row">${activityControl}${active && state.sessionId ? `<button type="button" class="deep-research-stop-button" data-deep-research-action="stop" data-research-key="${key}" aria-label="${escapeAttributeValue(t('research.stop', null, 'Stop research'))}"${state.pendingAction ? ' disabled aria-disabled="true"' : ''}><span aria-hidden="true"></span></button>` : ''}</div>` : ''}
        ${state.error && !statusIsTerminal(state.status) ? `<div class="deep-research-inline-error" role="alert">${escHtml(state.error)}</div>` : ''}
        ${pending || cardActions ? `<div class="deep-research-card-actions">${pending}${cardActions}</div>` : ''}
      </section>
    `;
  }

  function renderCard(segment, toolSegmentIndex) {
    return renderCardFromState(stateForSegment(segment), toolSegmentIndex);
  }

  function syntheticSearchSegment(search) {
    const safeSearch = asObject(search);
    const queries = Array.isArray(safeSearch.queries) ? safeSearch.queries.filter(Boolean) : [];
    const displayQueries = queries.length
      ? queries
      : [t('research.searchingSources', null, 'Searching sources')];
    const done = safeSearch.status !== 'running';
    return {
      type: 'tool',
      alias: `deep_research__web_search__${safeSearch.key || 'search'}`,
      serverId: 'web_search',
      serverName: 'Web Search',
      toolId: 'web_search',
      toolName: 'Web Search',
      arguments: { query: displayQueries },
      result: done ? '{}' : null,
      structuredContent: { sources: Array.isArray(safeSearch.sources) ? safeSearch.sources : [] },
      toolUi: {
        kind: 'search',
        status: safeSearch.status === 'failed' ? 'error' : (done ? 'done' : 'running'),
        search_request: {
          queries: displayQueries.map(function preparedQuery(query) {
            return { compiled_query: query, vertical: 'web' };
          })
        }
      }
    };
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
      return new Intl.DateTimeFormat(undefined, {
        hour: '2-digit',
        minute: '2-digit'
      }).format(date);
    } catch (_error) {
      return '';
    }
  }

  function renderActivityDetail(item) {
    if (!item.detail) {
      return '';
    }
    if (item.kind === 'read') {
      const readUrls = readUrlStringsFrom(item.detail);
      if (readUrls.length) {
        return `
          <div class="deep-research-read-links">
            ${readUrls.map(function renderReadUrl(url) {
              return `
                <div class="deep-research-read-link">
                  <span class="deep-research-read-link-dot" aria-hidden="true"></span>
                  <span class="deep-research-read-link-text">${escHtml(url)}</span>
                </div>
              `;
            }).join('')}
          </div>
        `;
      }
    }
    const preview = sentenceAwarePreview(item.detail, 280);
    const displayText = preview.truncated && !preview.text.endsWith('\u2026')
      ? `${preview.text} \u2026`
      : preview.text;
    return `<div class="msg-reasoning-text deep-research-timeline-detail">${escHtml(displayText)}</div>`;
  }

  function timelineEntries(state) {
    const entries = [];
    const collapsiblePhaseKinds = new Set(['plan', 'approval', 'reflection', 'read', 'report', 'stop']);
    let searchIndex = 0;
    (Array.isArray(state.activity) ? state.activity : []).forEach(function addActivity(item) {
      if (!item) {
        return;
      }
      if (item.kind === 'checkpoint' || (item.kind === 'tool' && !item.detail)) {
        return;
      }
      if (item.kind === 'search') {
        const previous = entries[entries.length - 1];
        if (previous && previous.type === 'search') {
          // search_started/search_completed describe one canonical web call.
          previous.item = item;
          return;
        }
        entries.push({
          type: 'search',
          item,
          search: state.searches[searchIndex] || null,
          searchIndex
        });
        searchIndex += 1;
        return;
      }

      const identity = [item.kind, item.title, item.detail].join('\u241f');
      const previous = entries[entries.length - 1];
      if (
        previous
        && previous.type === 'activity'
        && collapsiblePhaseKinds.has(item.kind)
        && previous.item.kind === item.kind
      ) {
        // CoT shows the latest public summary for one uninterrupted phase,
        // rather than separate "started" and "completed" notifications.
        previous.item = item;
        previous.identity = identity;
        return;
      }
      if (previous && previous.type === 'activity' && previous.identity === identity) {
        // Backend aliases can emit the same public milestone more than once.
        previous.item = item;
        return;
      }
      entries.push({ type: 'activity', item, identity });
    });

    while (searchIndex < state.searches.length) {
      entries.push({
        type: 'search',
        item: null,
        search: state.searches[searchIndex],
        searchIndex
      });
      searchIndex += 1;
    }
    return entries;
  }

  function renderActivityStep(item) {
    const time = activityTimeLabel(item.timestamp);
    let iconHtml = '';
    if (item.kind === 'read') {
      iconHtml = icons.WEB_SEARCH_ICON || icons.TOOL_SEARCH_ICON || icons.GLOBE_ICON || '';
    } else if (item.kind === 'search') {
      iconHtml = icons.TOOL_SEARCH_ICON || icons.WEB_SEARCH_ICON || icons.GLOBE_ICON || '';
    } else if (item.kind === 'analysis') {
      iconHtml = icons.TOOL_CODE_EXEC_ICON || icons.TOOL_BASH_ICON || '';
    }
    const toolClass = iconHtml ? ' msg-reasoning-step--tool' : '';
    return `
      <div class="msg-reasoning-step${toolClass} deep-research-activity-step is-${escapeAttributeValue(item.kind)} is-${escapeAttributeValue(item.status)}" data-research-activity-key="${escapeAttributeValue(item.key)}">
        <span class="msg-reasoning-step-dot" aria-hidden="true">${iconHtml}</span>
        <div class="msg-reasoning-step-body">
          <div class="msg-reasoning-step-title">
            <span>${escHtml(item.title)}</span>
            ${time ? `<time class="msg-reasoning-step-status deep-research-timeline-time">${escHtml(time)}</time>` : ''}
          </div>
          ${renderActivityDetail(item)}
        </div>
      </div>
    `;
  }

  function renderSearchStep(entry) {
    if (!entry.search || !renderCanonicalSearch) {
      return entry.item ? renderActivityStep(entry.item) : '';
    }
    const searchIcon = icons.TOOL_SEARCH_ICON || icons.WEB_SEARCH_ICON || icons.GLOBE_ICON || '';
    return `
      <div class="msg-reasoning-step msg-reasoning-step--tool deep-research-activity-step is-search is-${escapeAttributeValue(entry.search.status || 'done')}">
        <span class="msg-reasoning-step-dot" aria-hidden="true">${searchIcon}</span>
        <div class="msg-reasoning-step-body">
          ${renderCanonicalSearch(syntheticSearchSegment(entry.search), entry.searchIndex, {})}
        </div>
      </div>
    `;
  }

  function renderActivityTimeline(state) {
    const entries = timelineEntries(state);
    if (!entries.length) {
      return `<div class="deep-research-timeline-empty">${escHtml(t('research.activityPending', null, 'Research activity will appear here.'))}</div>`;
    }
    return `<div class="deep-research-timeline">${entries.map(function renderTimelineEntry(entry) {
      return entry.type === 'search'
        ? renderSearchStep(entry)
        : renderActivityStep(entry.item);
    }).join('')}</div>`;
  }

  function activityInspectorBody(state) {
    return `
      <div class="deep-research-inspector-view">
        <div class="deep-research-inspector-current">${escHtml(statusLabel(state.status))}</div>
        ${renderActivityTimeline(state)}
        ${state.error ? `<div class="deep-research-inspector-error" role="alert">${escHtml(state.error)}</div>` : ''}
      </div>
    `;
  }

  function reportInspectorBody(state) {
    const reportHtml = renderReportHtml(state);
    return reportHtml
      ? `<article class="deep-research-full-report markdown-body">${reportHtml}</article>`
      : activityInspectorBody(state);
  }

  function inspectorBody(state, viewMode) {
    return viewMode === 'report' && state.report
      ? reportInspectorBody(state)
      : activityInspectorBody(state);
  }

  function inspectorToolbar(state, viewMode) {
    const controls = [renderDownloadMenu(state, true)];
    if (state.report && viewMode === 'report') {
      const label = t('research.openActivity', null, 'Open research activity');
      controls.push(`
        <button type="button" class="deep-research-activity-toggle" data-deep-research-action="open-activity" data-research-key="${escapeAttributeValue(state.key)}" aria-label="${escapeAttributeValue(label)}" title="${escapeAttributeValue(label)}">
          <span class="deep-research-activity-toggle-icon" aria-hidden="true"><span></span><span></span><span></span></span>
        </button>
      `);
    }
    return controls.join('');
  }

  function inspectorFooter(state) {
    const controls = actionButtons(state, 'inspector');
    return controls
      ? `<div class="deep-research-inspector-actions">${controls}</div>`
      : '';
  }

  function hydrateInspectorReport() {
    if (!hydrateCanonicalReport) {
      return;
    }
    window.requestAnimationFrame(function hydrateResearchInspector() {
      hydrateCanonicalReport(document.querySelector('#toolInspectorModal .tool-inspector-research-body'));
    });
  }

  function openState(state, edit, requestedView) {
    const viewMode = requestedView === 'activity' || requestedView === 'report'
      ? requestedView
      : (state.report && statusIsTerminal(state.status) ? 'report' : 'activity');
    toolInspector.openResearch({
      key: state.key,
      title: compactText(state.topic || t('research.title', null, 'Deep Research'), 90),
      viewMode,
      toolbarHtml: inspectorToolbar(state, viewMode),
      bodyHtml: inspectorBody(state, viewMode),
      footerHtml: inspectorFooter(state)
    });
    hydrateInspectorReport();
    if (edit) {
      beginEdit(state.key);
    }
    ensurePolling(state, 0);
  }

  function openSegment(segment, edit) {
    openState(stateForSegment(segment), edit === true);
  }

  function openByKey(key, edit, requestedView) {
    const state = states.get(String(key || '').trim());
    if (state) {
      openState(state, edit === true, requestedView);
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
    const viewMode = toolInspector.getOpenResearchView ? toolInspector.getOpenResearchView() : 'activity';
    toolInspector.updateResearch({
      key: state.key,
      title: compactText(state.topic || t('research.title', null, 'Deep Research'), 90),
      viewMode,
      toolbarHtml: inspectorToolbar(state, viewMode),
      bodyHtml: inspectorBody(state, viewMode),
      footerHtml: inspectorFooter(state)
    });
    hydrateInspectorReport();
  }

  function refreshRenderedCards(state) {
    const selector = `.msg-deep-research-card[data-research-key="${escapeCssAttributeValue(state.key)}"]`;
    document.querySelectorAll(selector).forEach(function refreshCard(card) {
      const index = parseInt(card.getAttribute('data-tool-segment-index') || '-1', 10);
      const replacement = $(renderCardFromState(state, Number.isInteger(index) && index >= 0 ? index : undefined))[0];
      if (replacement && card.parentNode) {
        // An unchanged polling snapshot must leave the live node alone. Apart
        // from avoiding needless work, this keeps focus and running CSS
        // animations stable instead of restarting them every poll interval.
        if (card.isEqualNode(replacement)) {
          return;
        }
        const focusedAction = card.contains(document.activeElement)
          ? String(document.activeElement.getAttribute('data-deep-research-action') || '').trim()
          : '';
        card.parentNode.replaceChild(replacement, card);
        if (focusedAction) {
          const nextFocus = Array.from(replacement.querySelectorAll('[data-deep-research-action]'))
            .find(function matchFocusedAction(element) {
              return String(element.getAttribute('data-deep-research-action') || '').trim() === focusedAction;
            });
          if (nextFocus && typeof nextFocus.focus === 'function') {
            nextFocus.focus({ preventScroll: true });
          }
        }
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
    const previousControlState = action === 'cancel'
      ? {
        status: state.status,
        phase: state.phase,
        canApprove: state.canApprove,
        canEdit: state.canEdit,
        canStop: state.canStop,
        latestAction: state.latestAction
      }
      : null;
    state.pendingAction = uiAction;
    state.controlHoldUntil = Date.now() + 2500;
    state.error = '';
    if (action === 'cancel') {
      state.status = 'stopping';
      state.phase = 'stopping';
      state.canApprove = false;
      state.canEdit = false;
      state.canStop = false;
      state.latestAction = t('research.stopping', null, 'Stopping research safely');
    }
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
      const hasAuthoritativeSnapshot = Object.keys(snapshot).length > 0;
      if (hasAuthoritativeSnapshot) {
        mergeSnapshot(state, snapshot, { forceStatus: true });
      } else if (previousControlState) {
        state.status = previousControlState.status;
        state.phase = previousControlState.phase;
        state.canApprove = previousControlState.canApprove;
        state.canEdit = previousControlState.canEdit;
        state.canStop = previousControlState.canStop;
        state.latestAction = previousControlState.latestAction;
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

  async function downloadReport(state, format, $button) {
    if (!state || !state.sessionId || !state.report) {
      return;
    }
    const safeFormat = ['md', 'pdf', 'docx'].includes(String(format || '').toLowerCase())
      ? String(format).toLowerCase()
      : 'md';
    if ($button && $button.length) {
      $button.prop('disabled', true).attr('aria-busy', 'true');
    }
    try {
      const response = await fetch(EXPORT_ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({
          session_id: state.sessionId,
          format: safeFormat,
          title: state.topic,
          report: state.report
        })
      });
      if (!response.ok) {
        let message = `Export failed (${response.status})`;
        try {
          const errorPayload = await response.json();
          message = errorPayload.error || message;
        } catch (_error) {}
        throw new Error(message);
      }
      const blob = await response.blob();
      const disposition = String(response.headers.get('Content-Disposition') || '');
      const matchedName = disposition.match(/filename="?([^";]+)"?/i);
      const fallbackName = `research.${safeFormat}`;
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = matchedName ? matchedName[1] : fallbackName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(function revokeResearchDownload() {
        URL.revokeObjectURL(link.href);
      }, 1000);
      if ($button) {
        $button.closest('details').removeAttr('open');
      }
    } finally {
      if ($button && $button.length) {
        $button.prop('disabled', false).removeAttr('aria-busy');
      }
    }
  }

  function handleAction($button) {
    const button = $button && $button.jquery ? $button : $($button);
    const key = String(button.attr('data-research-key') || '').trim();
    const action = String(button.attr('data-deep-research-action') || '').trim();
    if (!key || !action) {
      return Promise.resolve();
    }
    if (action === 'open' || action === 'open-report') {
      openByKey(key, false, action === 'open-report' ? 'report' : undefined);
      return Promise.resolve();
    }
    if (action === 'open-activity') {
      openByKey(key, false, 'activity');
      return Promise.resolve();
    }
    if (action === 'edit') {
      beginEdit(key);
      return Promise.resolve();
    }
    if (action === 'download') {
      const state = states.get(key);
      return downloadReport(state, button.attr('data-research-format'), button);
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
    setCanonicalRenderers,
    syncOpenInspector
  };
}
