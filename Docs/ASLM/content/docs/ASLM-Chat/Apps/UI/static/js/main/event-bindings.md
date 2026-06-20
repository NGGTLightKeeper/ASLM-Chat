---
title: "event-bindings"
draft: false
---

## File `event-bindings`

`Apps/UI/static/js/main/event-bindings.js` — ASLM Chat client script.

---

## Overview

Part of `Apps\UI\static\js\main`. See **Related** for package index and callers.

---


## Private functions

#### `function readSectionCollapseMap()`

**Purpose:** Read the persisted {sectionId: collapsed} map.

#### `function persistSectionCollapsed(sectionId, collapsed)`

**Purpose:** Persist one section's collapsed state, keyed by its element id.

#### `function restoreSectionCollapseState()`

**Purpose:** Re-apply the saved collapse state to every settings section on load.

#### `function setHistoryCollapsed(collapsed, persist)`

**Purpose:** Collapse or expand the recent-chats list and optionally persist the state.

#### `function positionSettingHelpPopover(helpEl)`

**Purpose:** Position a setting's help popover next to its (?) icon.

---

## Public functions

#### `function bindEventHandlers(context, dependencies)`

**Purpose:** Client function `bindEventHandlers` used by the chat shell.

#### `function setRightSidebarCollapsed(collapsed, persist)`

**Purpose:** Client function `setRightSidebarCollapsed` used by the chat shell.

#### `function closeComposerMenus()`

**Purpose:** Client function `closeComposerMenus` used by the chat shell.

#### `function closeThinkLevelMenus()`

**Purpose:** Client function `closeThinkLevelMenus` used by the chat shell.

#### `function toggleComposerMenu($button, $popover)`

**Purpose:** Client function `toggleComposerMenu` used by the chat shell.

#### `function showDropOverlay()`

**Purpose:** Client function `showDropOverlay` used by the chat shell.

#### `function hideDropOverlay()`

**Purpose:** Client function `hideDropOverlay` used by the chat shell.

#### `function getDragDataTransfer(event)`

**Purpose:** Client function `getDragDataTransfer` used by the chat shell.

#### `function eventHasDraggedFiles(event)`

**Purpose:** Client function `eventHasDraggedFiles` used by the chat shell.

#### `function isSkillsManagerOpen()`

**Purpose:** Client function `isSkillsManagerOpen` used by the chat shell.

#### `function isOverSkillsImportSurface(event)`

**Purpose:** Client function `isOverSkillsImportSurface` used by the chat shell.

#### `function handleFileDrag(event)`

**Purpose:** Client function `handleFileDrag` used by the chat shell.

#### `function handleFileDragEnd(event)`

**Purpose:** Client function `handleFileDragEnd` used by the chat shell.

#### `function handleFileDrop(event)`

**Purpose:** Client function `handleFileDrop` used by the chat shell.

#### `function onOptionalNumberChange()`

**Purpose:** Client function `onOptionalNumberChange` used by the chat shell.

---

## Related

- [main/_index](../../../../../_index/)
