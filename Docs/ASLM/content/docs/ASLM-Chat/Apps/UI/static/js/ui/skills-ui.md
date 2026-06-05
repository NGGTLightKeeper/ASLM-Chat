---
title: "skills-ui"
draft: false
---

## File `skills-ui`

`Apps/UI/static/js/ui/skills-ui.js` — ASLM Chat client script.

---

## Overview

Part of `Apps\UI\static\js\ui`. See **Related** for package index and callers.

---

## Public functions

#### `function createSkillsUi(context)`

**Purpose:** Client function `createSkillsUi` used by the chat shell.

#### `function folderList()`

**Purpose:** Client function `folderList` used by the chat shell.

#### `function findFolder(name)`

**Purpose:** Client function `findFolder` used by the chat shell.

#### `function walkFiles(nodes, visitor)`

**Purpose:** Client function `walkFiles` used by the chat shell.

#### `function firstFile(folder)`

**Purpose:** Client function `firstFile` used by the chat shell.

#### `function selectFallback()`

**Purpose:** Client function `selectFallback` used by the chat shell.

#### `function loadSkills()`

**Purpose:** Client function `loadSkills` used by the chat shell.

#### `function renderSidebarSummary()`

**Purpose:** Client function `renderSidebarSummary` used by the chat shell.

#### `function ensureOverlay()`

**Purpose:** Client function `ensureOverlay` used by the chat shell.

#### `function openManager()`

**Purpose:** Client function `openManager` used by the chat shell.

#### `function closeManager()`

**Purpose:** Client function `closeManager` used by the chat shell.

#### `function showError(error)`

**Purpose:** Client function `showError` used by the chat shell.

#### `function showMessageDialog(title, message)`

**Purpose:** Client function `showMessageDialog` used by the chat shell.

#### `function showTextDialog(options)`

**Purpose:** Client function `showTextDialog` used by the chat shell.

#### `function close(value)`

**Purpose:** Client function `close` used by the chat shell.

#### `function submit()`

**Purpose:** Client function `submit` used by the chat shell.

#### `function showConfirmDialog(options)`

**Purpose:** Client function `showConfirmDialog` used by the chat shell.

#### `function readFileAsText(file)`

**Purpose:** Client function `readFileAsText` used by the chat shell.

#### `function firstPathSegment(relativePath)`

**Purpose:** Client function `firstPathSegment` used by the chat shell.

#### `function pathWithinSkillRoot(relativePath, rootName)`

**Purpose:** Client function `pathWithinSkillRoot` used by the chat shell.

#### `function isAllowedImportFileName(fileName)`

**Purpose:** Client function `isAllowedImportFileName` used by the chat shell.

#### `function readAllDirectoryEntries(dirReader)`

**Purpose:** Client function `readAllDirectoryEntries` used by the chat shell.

#### `function collectFilesFromEntry(entry, prefix)`

**Purpose:** Client function `collectFilesFromEntry` used by the chat shell.

#### `function collectFilesFromDirectoryEntry(dirEntry)`

**Purpose:** Client function `collectFilesFromDirectoryEntry` used by the chat shell.

#### `function collectFilesFromDirectoryHandle(dirHandle, prefix)`

**Purpose:** Client function `collectFilesFromDirectoryHandle` used by the chat shell.

#### `function collectFilesFromFileList(fileList, rootName, skillName)`

**Purpose:** Client function `collectFilesFromFileList` used by the chat shell.

#### `function groupFileListBySkillRoot(fileList, explicitName)`

**Purpose:** Client function `groupFileListBySkillRoot` used by the chat shell.

#### `function resolveImportPayloads(source, explicitName)`

**Purpose:** Client function `resolveImportPayloads` used by the chat shell.

#### `function importSkillFromSource(source, explicitName)`

**Purpose:** Client function `importSkillFromSource` used by the chat shell.

#### `function showAddSkillsDialog()`

**Purpose:** Client function `showAddSkillsDialog` used by the chat shell.

#### `function doCreate()`

**Purpose:** Client function `doCreate` used by the chat shell.

#### `function doImport(source)`

**Purpose:** Client function `doImport` used by the chat shell.

#### `function createSkill()`

**Purpose:** Client function `createSkill` used by the chat shell.

#### `function renameSkill(folderName)`

**Purpose:** Client function `renameSkill` used by the chat shell.

#### `function deleteSkill(folderName)`

**Purpose:** Client function `deleteSkill` used by the chat shell.

#### `function createFile(folderName)`

**Purpose:** Client function `createFile` used by the chat shell.

#### `function deleteFile(folderName, filePath, options)`

**Purpose:** Client function `deleteFile` used by the chat shell.

#### `function expandDirAncestors(folderName, dirPath)`

**Purpose:** Client function `expandDirAncestors` used by the chat shell.

#### `function remapExpandedDirs(folderName, oldPath, newPath)`

**Purpose:** Client function `remapExpandedDirs` used by the chat shell.

#### `function focusComposerInput()`

**Purpose:** Client function `focusComposerInput` used by the chat shell.

#### `function enterEditModeAt(folderName, parentPath, createKind)`

**Purpose:** Client function `enterEditModeAt` used by the chat shell.

#### `function renameTreeDirectory(folderName, dirPath)`

**Purpose:** Client function `renameTreeDirectory` used by the chat shell.

#### `function renameTreeFile(folderName, filePath)`

**Purpose:** Client function `renameTreeFile` used by the chat shell.

#### `function renderDirTools(folderName, dirPath)`

**Purpose:** Client function `renderDirTools` used by the chat shell.

#### `function renderFileTools(folderName, filePath)`

**Purpose:** Client function `renderFileTools` used by the chat shell.

#### `function syncComposerSkillCheckbox(folderName)`

**Purpose:** Client function `syncComposerSkillCheckbox` used by the chat shell.

#### `function setEnabled(folderName, enabled)`

**Purpose:** Client function `setEnabled` used by the chat shell.

#### `function renderComposerSkillsMenu()`

**Purpose:** Client function `renderComposerSkillsMenu` used by the chat shell.

#### `function loadCurrentFile()`

**Purpose:** Client function `loadCurrentFile` used by the chat shell.

#### `function renderOverlay()`

**Purpose:** Client function `renderOverlay` used by the chat shell.

#### `function renderTreeList()`

**Purpose:** Client function `renderTreeList` used by the chat shell.

#### `function renderTreePane()`

**Purpose:** Client function `renderTreePane` used by the chat shell.

#### `function renderSkillFolder(folder)`

**Purpose:** Client function `renderSkillFolder` used by the chat shell.

#### `function appendTreeToCascade($cascade, folderName, nodes, depth)`

**Purpose:** Client function `appendTreeToCascade` used by the chat shell.

#### `function renderDirRow(folderName, node, depth)`

**Purpose:** Client function `renderDirRow` used by the chat shell.

#### `function toggleExpanded(ev)`

**Purpose:** Client function `toggleExpanded` used by the chat shell.

#### `function renderFileRow(folderName, node, depth)`

**Purpose:** Client function `renderFileRow` used by the chat shell.

#### `function renderEditComposer(folderName, parentPath, depth)`

**Purpose:** Client function `renderEditComposer` used by the chat shell.

#### `function formatDetailFilePath(folderName, filePath)`

**Purpose:** Client function `formatDetailFilePath` used by the chat shell.

#### `function renderDetailPane()`

**Purpose:** Client function `renderDetailPane` used by the chat shell.

#### `function metaBlock(label, value)`

**Purpose:** Client function `metaBlock` used by the chat shell.

#### `function formatCreatedAt(timestamp)`

**Purpose:** Client function `formatCreatedAt` used by the chat shell.

#### `function enterEditMode(folderName)`

**Purpose:** Client function `enterEditMode` used by the chat shell.

#### `function exitEditMode()`

**Purpose:** Client function `exitEditMode` used by the chat shell.

#### `function deriveEditParentPath(folderName)`

**Purpose:** Client function `deriveEditParentPath` used by the chat shell.

#### `function submitComposerFolder(folderName, parentPath, name)`

**Purpose:** Client function `submitComposerFolder` used by the chat shell.

#### `function submitComposerFile(folderName, parentPath, rawName)`

**Purpose:** Client function `submitComposerFile` used by the chat shell.

#### `function openSkillActions(folder, $anchor)`

**Purpose:** Client function `openSkillActions` used by the chat shell.

#### `function renderPreview($panel)`

**Purpose:** Client function `renderPreview` used by the chat shell.

#### `function stripFrontMatter(content)`

**Purpose:** Client function `stripFrontMatter` used by the chat shell.

#### `function renderSourceEditor($panel)`

**Purpose:** Client function `renderSourceEditor` used by the chat shell.

#### `function buildGutterLines(lineCount)`

**Purpose:** Client function `buildGutterLines` used by the chat shell.

#### `function syncEditor()`

**Purpose:** Client function `syncEditor` used by the chat shell.

#### `function syncScroll()`

**Purpose:** Client function `syncScroll` used by the chat shell.

#### `function highlightCode(source, filePath)`

**Purpose:** Client function `highlightCode` used by the chat shell.

#### `function languageForPath(filePath)`

**Purpose:** Client function `languageForPath` used by the chat shell.

#### `function escapeHtml(value)`

**Purpose:** Client function `escapeHtml` used by the chat shell.

#### `function init()`

**Purpose:** Client function `init` used by the chat shell.

---

## Related

- [ui/_index](../../../../../_index/)
