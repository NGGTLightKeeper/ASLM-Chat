---
title: "engine-manager"
draft: false
---

## File `engine-manager`

`Apps/UI/static/js/main/engine-manager.js` — ASLM Chat client script.

---

## Overview

Part of `Apps\UI\static\js\main`. See **Related** for package index and callers.

---

## Public functions

#### `function createEngineManager(context, dependencies)`

**Purpose:** Client function `createEngineManager` used by the chat shell.

#### `function readLastModelMap()`

**Purpose:** Client function `readLastModelMap` used by the chat shell.

#### `function rememberLastModel(engine, modelName)`

**Purpose:** Client function `rememberLastModel` used by the chat shell.

#### `function getRememberedLastModel(engine)`

**Purpose:** Client function `getRememberedLastModel` used by the chat shell.

#### `function getActiveEngine()`

**Purpose:** Client function `getActiveEngine` used by the chat shell.

#### `function getSelectedModelName()`

**Purpose:** Client function `getSelectedModelName` used by the chat shell.

#### `function getActivePreset()`

**Purpose:** Client function `getActivePreset` used by the chat shell.

#### `function resetThinkState()`

**Purpose:** Client function `resetThinkState` used by the chat shell.

#### `function resetPresetUi()`

**Purpose:** Client function `resetPresetUi` used by the chat shell.

#### `function applyPresetState(payload)`

**Purpose:** Client function `applyPresetState` used by the chat shell.

#### `function getEngineAddressKey(engine)`

**Purpose:** Client function `getEngineAddressKey` used by the chat shell.

#### `function getEngineAddress(engine)`

**Purpose:** Client function `getEngineAddress` used by the chat shell.

#### `function getEngineApiKeyKey(engine)`

**Purpose:** Client function `getEngineApiKeyKey` used by the chat shell.

#### `function hasStoredEngineApiKey(engine)`

**Purpose:** Client function `hasStoredEngineApiKey` used by the chat shell.

#### `function isLocalLmsAddress()`

**Purpose:** Client function `isLocalLmsAddress` used by the chat shell.

#### `function setEngineAddressStatus(text, status)`

**Purpose:** Client function `setEngineAddressStatus` used by the chat shell.

#### `function setEngineApiKeyStatus(text, status)`

**Purpose:** Client function `setEngineApiKeyStatus` used by the chat shell.

#### `function updateEngineAddressUi()`

**Purpose:** Client function `updateEngineAddressUi` used by the chat shell.

#### `function resetModelUiState(message)`

**Purpose:** Client function `resetModelUiState` used by the chat shell.

#### `function clearModelCache(engine)`

**Purpose:** Client function `clearModelCache` used by the chat shell.

#### `function normalizeModelNames(models)`

**Purpose:** Client function `normalizeModelNames` used by the chat shell.

#### `function areModelListsEqual(left, right)`

**Purpose:** Client function `areModelListsEqual` used by the chat shell.

#### `function getAvailableModelsForEngine(engine)`

**Purpose:** Client function `getAvailableModelsForEngine` used by the chat shell.

#### `function clearModelsRefreshTimer()`

**Purpose:** Client function `clearModelsRefreshTimer` used by the chat shell.

#### `function getLmsSteadyRefreshInterval()`

**Purpose:** Client function `getLmsSteadyRefreshInterval` used by the chat shell.

#### `function getModelsRefreshInterval(engine)`

**Purpose:** Client function `getModelsRefreshInterval` used by the chat shell.

#### `function scheduleModelsRefresh(delayMs)`

**Purpose:** Client function `scheduleModelsRefresh` used by the chat shell.

#### `function syncModelsRefresh()`

**Purpose:** Client function `syncModelsRefresh` used by the chat shell.

#### `function renderModelOptions(models, preferredModel)`

**Purpose:** Client function `renderModelOptions` used by the chat shell.

#### `function fetchModelsForEngine(engine)`

**Purpose:** Client function `fetchModelsForEngine` used by the chat shell.

#### `function runFetch()`

**Purpose:** Client function `runFetch` used by the chat shell.

#### `function ensureModelsLoadedForActiveEngine(options)`

**Purpose:** Client function `ensureModelsLoadedForActiveEngine` used by the chat shell.

#### `function refreshActiveEngineModels(options)`

**Purpose:** Client function `refreshActiveEngineModels` used by the chat shell.

#### `function saveRuntimeSettings(patch)`

**Purpose:** Client function `saveRuntimeSettings` used by the chat shell.

#### `function applyEngineSelection(engine, options)`

**Purpose:** Client function `applyEngineSelection` used by the chat shell.

#### `function refreshActiveEngineModelList()`

**Purpose:** Client function `refreshActiveEngineModelList` used by the chat shell.

#### `function buildActivePresetConfigPayload()`

**Purpose:** Client function `buildActivePresetConfigPayload` used by the chat shell.

#### `function syncActivePreset()`

**Purpose:** Client function `syncActivePreset` used by the chat shell.

#### `function schedulePresetSync()`

**Purpose:** Client function `schedulePresetSync` used by the chat shell.

#### `function loadModelInfo(model)`

**Purpose:** Client function `loadModelInfo` used by the chat shell.

#### `function selectPreset(presetId)`

**Purpose:** Client function `selectPreset` used by the chat shell.

#### `function createPreset()`

**Purpose:** Client function `createPreset` used by the chat shell.

#### `function renamePreset()`

**Purpose:** Client function `renamePreset` used by the chat shell.

#### `function deletePreset()`

**Purpose:** Client function `deletePreset` used by the chat shell.

#### `function persistEngineAddress()`

**Purpose:** Client function `persistEngineAddress` used by the chat shell.

#### `function handleApiKeyToggle()`

**Purpose:** Client function `handleApiKeyToggle` used by the chat shell.

#### `function persistApiKey()`

**Purpose:** Client function `persistApiKey` used by the chat shell.

---

## Related

- [main/_index](../../../../../_index/)
