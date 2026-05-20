// Copyright NGGT.LightKeeper. All Rights Reserved.

import { getJson, patchJson, postJson, requestJson } from '../main/api.js';

// Skills manager UI.
// Create the settings-sidebar entry and the modal customize surface.
export function createSkillsUi(context) {
  const { dom, icons } = context;
  const state = {
    payload: { folders: [] },
    selectedFolder: '',
    selectedFile: '',
    currentFile: null,
    mode: 'preview',
    query: '',
    expandedSkills: new Set(),
    expandedDirs: new Set(),
    editMode: null
  };

  let $overlay = null;
  let $middle = null;
  let $detail = null;

  function folderList() {
    return Array.isArray(state.payload.folders) ? state.payload.folders : [];
  }

  function findFolder(name) {
    return folderList().find((folder) => String(folder.name || '') === String(name || '')) || null;
  }

  function walkFiles(nodes, visitor) {
    (Array.isArray(nodes) ? nodes : []).forEach(function visit(node) {
      if (!node || typeof node !== 'object') {
        return;
      }
      visitor(node);
      if (node.type === 'directory') {
        walkFiles(node.children || [], visitor);
      }
    });
  }

  function firstFile(folder) {
    if (!folder) {
      return '';
    }
    if (folder.primary_file) {
      return String(folder.primary_file);
    }
    let found = '';
    walkFiles(folder.tree || [], function find(node) {
      if (!found && node.type === 'file') {
        found = String(node.path || '');
      }
    });
    return found;
  }

  function selectFallback() {
    if (findFolder(state.selectedFolder)) {
      if (!state.selectedFile) {
        state.selectedFile = firstFile(findFolder(state.selectedFolder));
      }
      return;
    }
    const first = folderList()[0];
    state.selectedFolder = first ? String(first.name || '') : '';
    state.selectedFile = firstFile(first);
    if (state.selectedFolder) {
      state.expandedSkills.add(state.selectedFolder);
    }
  }

  async function loadSkills() {
    state.payload = await getJson('/api/skills/');
    selectFallback();
    renderSidebarSummary();
    renderOverlay();
  }

  function renderSidebarSummary() {
    if (!dom.$skillsSettingsContent || !dom.$skillsSettingsContent.length) {
      return;
    }
    const count = folderList().length;
    dom.$skillsSettingsContent.empty();
    const $btn = $('<button type="button" class="preset-action-btn skills-open-btn">').text('Manage skills');
    const $summary = $('<div class="skills-settings-summary">').text(
      count === 1 ? '1 personal skill' : `${count} personal skills`
    );
    $btn.on('click', openManager);
    dom.$skillsSettingsContent.append($btn).append($summary);
  }

  function ensureOverlay() {
    if ($overlay && $overlay.length) {
      return;
    }
    $overlay = $('<div class="skills-manager-backdrop" role="dialog" aria-modal="true" aria-label="Customize skills">');
    const $shell = $('<div class="skills-manager-shell">');

    $middle = $('<aside class="skills-tree-pane">');
    $detail = $('<main class="skills-detail-pane">');
    $shell.append($middle).append($detail);
    $overlay.append($shell);
    $('body').append($overlay);
    $overlay.on('click', function onBackdrop(ev) {
      if (ev.target === $overlay[0]) {
        closeManager();
      }
    });
  }

  function openManager() {
    ensureOverlay();
    $('body').addClass('skills-manager-open');
    $overlay.addClass('is-open');
    loadSkills().catch(showError);
  }

  function closeManager() {
    $('body').removeClass('skills-manager-open');
    if ($overlay) {
      $overlay.removeClass('is-open');
    }
  }

  function showError(error) {
    const message = error && error.message ? error.message : String(error);
    if ($detail && $detail.length) {
      $detail.find('.skills-detail-error').remove();
      $detail.prepend($('<div class="skills-detail-error" role="alert">').text(message));
    } else {
      showMessageDialog('Skills error', message);
    }
  }

  function showMessageDialog(title, message) {
    return showConfirmDialog({
      title,
      message,
      confirmText: 'OK',
      cancelText: '',
      danger: false
    });
  }

  function showTextDialog(options) {
    ensureOverlay();
    return new Promise(function textDialogPromise(resolve) {
      const dialogOptions = options || {};
      const $backdrop = $('<div class="skills-inline-dialog-backdrop" role="dialog" aria-modal="true">');
      const $dialog = $('<div class="skills-inline-dialog">');
      const $title = $('<div class="skills-inline-dialog-title">').text(dialogOptions.title || 'Input');
      const $label = $('<label class="skills-inline-dialog-label">').text(dialogOptions.label || '');
      const $input = $('<input class="skills-inline-dialog-input" type="text">')
        .val(dialogOptions.value || '')
        .attr('placeholder', dialogOptions.placeholder || '');
      const $error = $('<div class="skills-inline-dialog-error" role="alert">').hide();
      const $actions = $('<div class="skills-inline-dialog-actions">');
      const $cancel = $('<button type="button" class="preset-action-btn">').text('Cancel');
      const $confirm = $('<button type="button" class="preset-action-btn preset-action-btn-primary">').text(dialogOptions.confirmText || 'OK');

      function close(value) {
        $backdrop.remove();
        resolve(value);
      }

      function submit() {
        const value = String($input.val() || '').trim();
        if (!value) {
          $error.text('Value is required.').show();
          return;
        }
        close(value);
      }

      $cancel.on('click', function onCancel() {
        close('');
      });
      $confirm.on('click', submit);
      $input.on('keydown', function onKeyDown(ev) {
        if (ev.key === 'Enter') {
          ev.preventDefault();
          submit();
        } else if (ev.key === 'Escape') {
          ev.preventDefault();
          close('');
        }
      });

      $actions.append($cancel).append($confirm);
      $dialog.append($title).append($label.append($input)).append($error).append($actions);
      $backdrop.append($dialog);
      ($overlay || $('body')).append($backdrop);
      requestAnimationFrame(function focusInput() {
        $input.trigger('focus');
        const input = $input.get(0);
        if (input && input.select) {
          input.select();
        }
      });
    });
  }

  function showConfirmDialog(options) {
    ensureOverlay();
    return new Promise(function confirmDialogPromise(resolve) {
      const dialogOptions = options || {};
      const $backdrop = $('<div class="skills-inline-dialog-backdrop" role="dialog" aria-modal="true">');
      const $dialog = $('<div class="skills-inline-dialog">');
      const $title = $('<div class="skills-inline-dialog-title">').text(dialogOptions.title || 'Confirm');
      const $message = $('<div class="skills-inline-dialog-message">').text(dialogOptions.message || '');
      const $actions = $('<div class="skills-inline-dialog-actions">');
      const cancelText = dialogOptions.cancelText === undefined ? 'Cancel' : String(dialogOptions.cancelText || '');
      const $confirm = $('<button type="button" class="preset-action-btn preset-action-btn-primary">')
        .toggleClass('preset-action-btn-danger', Boolean(dialogOptions.danger))
        .text(dialogOptions.confirmText || 'OK');

      function close(value) {
        $backdrop.remove();
        resolve(value);
      }

      if (cancelText) {
        const $cancel = $('<button type="button" class="preset-action-btn">').text(cancelText);
        $cancel.on('click', function onCancel() {
          close(false);
        });
        $actions.append($cancel);
      }

      $confirm.on('click', function onConfirm() {
        close(true);
      });
      $backdrop.on('click', function onBackdropClick(ev) {
        if (ev.target === $backdrop[0]) {
          close(false);
        }
      });

      $actions.append($confirm);
      $dialog.append($title).append($message).append($actions);
      $backdrop.append($dialog);
      ($overlay || $('body')).append($backdrop);
    });
  }

  const ALLOWED_IMPORT_EXTENSIONS = new Set([
    '.bat', '.css', '.html', '.js', '.json', '.md', '.ps1',
    '.py', '.sh', '.toml', '.ts', '.txt', '.yaml', '.yml'
  ]);

  function readFileAsText(file) {
    return new Promise(function readPromise(resolve, reject) {
      const reader = new FileReader();
      reader.onload = function onLoad(ev) { resolve(ev.target.result || ''); };
      reader.onerror = function onErr() { reject(new Error(`Failed to read ${file.name}`)); };
      reader.readAsText(file);
    });
  }

  function firstPathSegment(relativePath) {
    const norm = String(relativePath || '').replace(/\\/g, '/').replace(/^\/+/, '');
    const slash = norm.indexOf('/');
    return slash === -1 ? norm : norm.slice(0, slash);
  }

  function pathWithinSkillRoot(relativePath, rootName) {
    const norm = String(relativePath || '').replace(/\\/g, '/').replace(/^\/+/, '');
    if (!rootName) {
      return norm;
    }
    const prefix = `${rootName}/`;
    if (norm.startsWith(prefix)) {
      return norm.slice(prefix.length);
    }
    const slash = norm.indexOf('/');
    return slash === -1 ? '' : norm.slice(slash + 1);
  }

  function isAllowedImportFileName(fileName) {
    const ext = ('.' + String(fileName || '').split('.').pop()).toLowerCase();
    return ALLOWED_IMPORT_EXTENSIONS.has(ext);
  }

  async function readAllDirectoryEntries(dirReader) {
    const all = [];
    let batch = [];
    do {
      batch = await new Promise(function (res, rej) { dirReader.readEntries(res, rej); });
      all.push(...batch);
    } while (batch.length > 0);
    return all;
  }

  async function collectFilesFromEntry(entry, prefix) {
    const results = [];
    if (entry.isFile) {
      if (!isAllowedImportFileName(entry.name)) {
        return results;
      }
      const file = await new Promise(function (res, rej) { entry.file(res, rej); });
      const content = await readFileAsText(file);
      results.push({ path: prefix ? `${prefix}/${entry.name}` : entry.name, content });
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      const children = await readAllDirectoryEntries(reader);
      const childPrefix = prefix ? `${prefix}/${entry.name}` : entry.name;
      for (const child of children) {
        const sub = await collectFilesFromEntry(child, childPrefix);
        results.push(...sub);
      }
    }
    return results;
  }

  async function collectFilesFromDirectoryEntry(dirEntry) {
    const reader = dirEntry.createReader();
    const children = await readAllDirectoryEntries(reader);
    const files = [];
    for (const child of children) {
      const sub = await collectFilesFromEntry(child, '');
      files.push(...sub);
    }
    return files;
  }

  async function collectFilesFromDirectoryHandle(dirHandle, prefix) {
    const results = [];
    for await (const childHandle of dirHandle.values()) {
      const rel = prefix ? `${prefix}/${childHandle.name}` : childHandle.name;
      if (childHandle.kind === 'file') {
        if (!isAllowedImportFileName(childHandle.name)) {
          continue;
        }
        const file = await childHandle.getFile();
        const content = await readFileAsText(file);
        results.push({ path: rel, content });
      } else if (childHandle.kind === 'directory') {
        const sub = await collectFilesFromDirectoryHandle(childHandle, rel);
        results.push(...sub);
      }
    }
    return results;
  }

  async function collectFilesFromFileList(fileList, rootName, skillName) {
    const arr = Array.from(fileList instanceof FileList ? fileList : (fileList.files || []));
    const files = [];
    const pathRoot = rootName || skillName || '';
    for (const file of arr) {
      if (!isAllowedImportFileName(file.name)) {
        continue;
      }
      const rel = file.webkitRelativePath || file.name;
      let relWithinSkill = pathWithinSkillRoot(rel, pathRoot);
      if (!relWithinSkill && pathRoot && !rel.includes('/')) {
        relWithinSkill = file.name;
      }
      if (!relWithinSkill && !pathRoot) {
        relWithinSkill = file.name;
      }
      if (!relWithinSkill) {
        continue;
      }
      const content = await readFileAsText(file);
      files.push({ path: relWithinSkill, content });
    }
    return files;
  }

  async function groupFileListBySkillRoot(fileList, explicitName) {
    const arr = Array.from(fileList instanceof FileList ? fileList : (fileList.files || []));
    const groups = new Map();
    for (const file of arr) {
      const rel = file.webkitRelativePath || '';
      const root = firstPathSegment(rel);
      if (!root) {
        continue;
      }
      if (!groups.has(root)) {
        groups.set(root, []);
      }
      groups.get(root).push(file);
    }
    if (groups.size > 0) {
      const payloads = [];
      for (const [root, files] of groups.entries()) {
        const collected = await collectFilesFromFileList(files, root, root);
        if (collected.length) {
          payloads.push({ skillName: root, files: collected });
        }
      }
      return payloads;
    }
    const target = String(explicitName || state.selectedFolder || '').trim();
    if (!target) {
      return [];
    }
    const collected = await collectFilesFromFileList(arr, '', target);
    if (!collected.length) {
      return [];
    }
    return [{ skillName: target, files: collected }];
  }

  async function resolveImportPayloads(source, explicitName) {
    const nameHint = String(explicitName || state.selectedFolder || '').trim();

    if (source && source.skillName && Array.isArray(source.files)) {
      return [{ skillName: source.skillName, files: source.files }];
    }

    const dataTransfer = source instanceof DataTransfer ? source : null;
    const fileList = source instanceof FileList ? source : null;
    let entries = dataTransfer
      ? Array.from(dataTransfer.items || [])
        .map(function (item) { return item.webkitGetAsEntry ? item.webkitGetAsEntry() : null; })
        .filter(Boolean)
      : [];

    if (entries.length === 0 && dataTransfer && dataTransfer.files && dataTransfer.files.length > 0) {
      return groupFileListBySkillRoot(dataTransfer.files, nameHint);
    }

    if (entries.length > 0) {
      const topDirs = entries.filter(function (e) { return e.isDirectory; });
      const topFiles = entries.filter(function (e) { return e.isFile; });

      if (topDirs.length === 1 && topFiles.length === 0) {
        const skillName = topDirs[0].name;
        const files = await collectFilesFromDirectoryEntry(topDirs[0]);
        return [{ skillName, files }];
      }

      if (topDirs.length > 1 && !nameHint) {
        const payloads = [];
        for (const dir of topDirs) {
          const files = await collectFilesFromDirectoryEntry(dir);
          if (files.length) {
            payloads.push({ skillName: dir.name, files });
          }
        }
        if (payloads.length) {
          return payloads;
        }
      }

      const skillName = nameHint;
      if (!skillName) {
        throw new Error('Enter a skill name in the field above, or drop one skill folder at a time.');
      }
      const files = [];
      for (const entry of entries) {
        if (entry.isFile) {
          if (!isAllowedImportFileName(entry.name)) {
            continue;
          }
          const file = await new Promise(function (res, rej) { entry.file(res, rej); });
          const content = await readFileAsText(file);
          files.push({ path: entry.name, content });
        } else if (entry.isDirectory) {
          const sub = await collectFilesFromDirectoryEntry(entry);
          const prefix = entry.name;
          for (const item of sub) {
            files.push({ path: `${prefix}/${item.path}`, content: item.content });
          }
        }
      }
      return [{ skillName, files }];
    }

    if (fileList && fileList.length > 0) {
      const grouped = await groupFileListBySkillRoot(fileList, nameHint);
      if (grouped.length) {
        return grouped;
      }
      throw new Error('Enter a skill name above, select a skill in the tree, or pick a single skill folder.');
    }

    throw new Error('No files found.');
  }

  async function importSkillFromSource(source, explicitName) {
    const payloads = await resolveImportPayloads(source, explicitName);
    if (!payloads.length) {
      throw new Error('No supported text files found (.md, .txt, .py, …).');
    }

    for (const payload of payloads) {
      const skillName = String(payload.skillName || '').trim();
      if (!skillName) {
        throw new Error('Skill name is required.');
      }
      if (!payload.files || !payload.files.length) {
        throw new Error(`No supported text files found for "${skillName}".`);
      }
      await postJson('/api/skills/import/', {
        name: skillName,
        files: payload.files
      });
    }

    state.query = '';
    const lastName = payloads[payloads.length - 1].skillName;
    await loadSkills();
    state.selectedFolder = lastName;
    state.selectedFile = firstFile(findFolder(lastName));
    state.expandedSkills.add(lastName);
    return lastName;
  }

  function showAddSkillsDialog() {
    ensureOverlay();
    return new Promise(function addDialogPromise(resolve) {
      const $backdrop = $('<div class="skills-inline-dialog-backdrop" role="dialog" aria-modal="true">');
      const $dialog = $('<div class="skills-inline-dialog skills-add-dialog">');

      // --- Create section ---
      const $createSection = $('<div class="skills-add-section">');
      const $createLabel = $('<div class="skills-add-section-title">').text('Create skill');
      const $createRow = $('<div class="skills-add-create-row">');
      const $nameInput = $('<input class="skills-inline-dialog-input" type="text" autocomplete="off" spellcheck="false">')
        .attr('placeholder', 'skill-name');
      const $createBtn = $('<button type="button" class="preset-action-btn preset-action-btn-primary">').text('Create');
      const $createError = $('<div class="skills-inline-dialog-error" role="alert">').hide();
      $createRow.append($nameInput).append($createBtn);
      $createSection.append($createLabel).append($createRow).append($createError);

      // --- Divider ---
      const $divider = $('<div class="skills-add-divider">');

      // --- Import section ---
      const $importSection = $('<div class="skills-add-section">');
      const $importLabel = $('<div class="skills-add-section-title">').text('Import skill folder');
      const $dropzone = $('<div class="skills-import-dropzone" role="button" tabindex="0" aria-label="Drop a skill folder here">');
      const $dropzoneText = $('<div class="skills-import-dropzone-text">').text('Drop the skill folder here (parent directory)');
      const $dropzoneHint = $('<div class="skills-import-dropzone-hint">').text('or');
      const $browseBtn = $('<button type="button" class="preset-action-btn">').text('Browse folder…');
      const $fileInput = $('<input type="file" style="display:none">').attr('webkitdirectory', '').attr('multiple', '');
      const $importStatus = $('<div class="skills-inline-dialog-error" role="status">').hide();
      $dropzone.append($dropzoneText).append($dropzoneHint).append($browseBtn);
      $importSection.append($importLabel).append($dropzone).append($importStatus);

      $dialog.append($createSection).append($divider).append($importSection);
      $backdrop.append($dialog).append($fileInput);
      ($overlay || $('body')).append($backdrop);

      function close(value) {
        $(document).off('dragend.skillsAddDialog');
        $backdrop.remove();
        resolve(value);
      }

      async function doCreate() {
        const name = String($nameInput.val() || '').trim();
        if (!name) {
          $createError.text('Skill name is required.').show();
          return;
        }
        $createError.hide();
        try {
          state.payload = await postJson('/api/skills/', { name });
          state.selectedFolder = name;
          state.selectedFile = firstFile(findFolder(name));
          state.expandedSkills.add(name);
          close(name);
          renderOverlay();
        } catch (err) {
          $createError.text(err && err.message ? err.message : String(err)).show();
        }
      }

      async function doImport(source) {
        $importStatus.text('Importing…').removeClass('is-error').show();
        try {
          const explicitName = String($nameInput.val() || '').trim();
          const name = await importSkillFromSource(source, explicitName);
          close(name);
          renderOverlay();
        } catch (err) {
          $importStatus.text(err && err.message ? err.message : String(err)).addClass('is-error').show();
        }
      }

      $createBtn.on('click', doCreate);
      $nameInput.on('keydown', function onKey(ev) {
        if (ev.key === 'Enter') {
          ev.preventDefault();
          doCreate();
        } else if (ev.key === 'Escape') {
          ev.preventDefault();
          close('');
        }
      });

      $browseBtn.on('click', function onBrowse(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        $fileInput.val('');
        $fileInput.trigger('click');
      });

      $fileInput.on('change', function onFileChange() {
        if (this.files && this.files.length > 0) {
          doImport(this.files);
        }
      });

      $dropzone.on('dragenter dragover', function onDragOver(ev) {
        ev.preventDefault();
        const dt = ev.originalEvent && ev.originalEvent.dataTransfer;
        if (dt) {
          dt.dropEffect = 'copy';
        }
        $dropzone.addClass('is-dragover');
      });

      $dropzone.on('dragleave', function onDragLeave(ev) {
        if (!$dropzone[0].contains(ev.relatedTarget)) {
          $dropzone.removeClass('is-dragover');
        }
      });

      $dropzone.on('drop', function onDrop(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        $dropzone.removeClass('is-dragover');
        const dt = ev.originalEvent && ev.originalEvent.dataTransfer;
        if (dt && dt.items && dt.items.length > 0) {
          doImport(dt);
        }
      });

      $(document).on('dragend.skillsAddDialog', function onDragEnd() {
        $dropzone.removeClass('is-dragover');
      });

      $backdrop.on('click', function onBackdrop(ev) {
        if (ev.target === $backdrop[0]) {
          close('');
        }
      });

      requestAnimationFrame(function focusInput() {
        $nameInput.trigger('focus');
      });
    });
  }

  async function createSkill() {
    const name = await showTextDialog({
      title: 'New skill',
      label: 'Skill folder name',
      placeholder: 'skill-creator',
      confirmText: 'Create'
    });
    if (!name) {
      return;
    }
    state.payload = await postJson('/api/skills/', { name });
    state.selectedFolder = name.trim();
    state.selectedFile = firstFile(findFolder(state.selectedFolder));
    state.expandedSkills.add(state.selectedFolder);
    renderOverlay();
  }

  async function renameSkill(folderName) {
    const nextName = await showTextDialog({
      title: 'Rename skill',
      label: 'New skill folder name',
      value: folderName,
      confirmText: 'Rename'
    });
    if (!nextName || nextName === folderName) {
      return;
    }
    state.payload = await patchJson('/api/skills/folder/', { old_name: folderName, new_name: nextName });
    state.selectedFolder = nextName.trim();
    state.expandedSkills.add(state.selectedFolder);
    renderOverlay();
  }

  async function deleteSkill(folderName) {
    const confirmed = await showConfirmDialog({
      title: 'Delete skill',
      message: `Delete skill "${folderName}"?`,
      confirmText: 'Delete',
      danger: true
    });
    if (!confirmed) {
      return;
    }
    state.payload = await requestJson('/api/skills/folder/', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: folderName })
    });
    state.selectedFolder = '';
    state.selectedFile = '';
    state.currentFile = null;
    selectFallback();
    renderOverlay();
  }

  async function createFile(folderName) {
    const filePath = await showTextDialog({
      title: 'New skill file',
      label: 'File path inside the skill',
      value: 'SKILL.md',
      placeholder: 'agents/grader.md',
      confirmText: 'Create'
    });
    if (!filePath) {
      return;
    }
    const title = filePath.split('/').pop() || filePath;
    state.payload = await requestJson('/api/skills/file/', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder: folderName, file: filePath, content: `# ${title}\n\n` })
    });
    state.selectedFolder = folderName;
    state.selectedFile = filePath.replace(/\\/g, '/').replace(/^\/+/, '');
    state.expandedSkills.add(folderName);
    await loadCurrentFile();
    renderOverlay();
  }

  async function deleteFile(folderName, filePath, options) {
    if (!filePath) {
      return;
    }
    const opts = options || {};
    if (!opts.skipConfirm) {
      const confirmed = await showConfirmDialog({
        title: 'Delete file',
        message: 'Are you sure?',
        confirmText: 'Delete',
        danger: true
      });
      if (!confirmed) {
        return;
      }
    }
    state.payload = await requestJson('/api/skills/file/', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder: folderName, file: filePath })
    });
    if (state.selectedFile === filePath) {
      state.selectedFile = firstFile(findFolder(folderName));
      state.currentFile = null;
    }
    renderOverlay();
  }

  function expandDirAncestors(folderName, dirPath) {
    if (!dirPath) {
      return;
    }
    const parts = dirPath.split('/').filter(Boolean);
    for (let index = 1; index <= parts.length; index += 1) {
      state.expandedDirs.add(`${folderName}/${parts.slice(0, index).join('/')}`);
    }
  }

  function remapExpandedDirs(folderName, oldPath, newPath) {
    const prefix = `${folderName}/${oldPath}`;
    const nextPrefix = `${folderName}/${newPath}`;
    const next = new Set();
    state.expandedDirs.forEach(function remap(key) {
      if (key === prefix || key.startsWith(`${prefix}/`)) {
        next.add(nextPrefix + key.slice(prefix.length));
      } else {
        next.add(key);
      }
    });
    state.expandedDirs = next;
  }

  function focusComposerInput() {
    requestAnimationFrame(function focusComposer() {
      const $input = $middle && $middle.find('.skills-edit-input').first();
      if ($input && $input.length) {
        $input.trigger('focus');
      }
    });
  }

  function enterEditModeAt(folderName, parentPath, createKind) {
    state.editMode = {
      skillName: folderName,
      parentPath: parentPath || '',
      createKind: createKind || 'folder'
    };
    state.expandedSkills.add(folderName);
    expandDirAncestors(folderName, parentPath);
    renderTreePane();
    focusComposerInput();
  }

  async function renameTreeDirectory(folderName, dirPath) {
    const baseName = dirPath.split('/').pop() || dirPath;
    const newName = await showTextDialog({
      title: 'Rename folder',
      label: 'Folder name',
      value: baseName,
      confirmText: 'Rename'
    });
    if (!newName || newName === baseName) {
      return;
    }
    const parent = dirPath.includes('/') ? dirPath.replace(/\/[^/]+$/, '') : '';
    const newPath = parent ? `${parent}/${newName}` : newName;
    state.payload = await patchJson('/api/skills/path/', {
      folder: folderName,
      old_path: dirPath,
      new_path: newPath,
      kind: 'directory'
    });
    remapExpandedDirs(folderName, dirPath, newPath);
    if (state.editMode && state.editMode.skillName === folderName && state.editMode.parentPath === dirPath) {
      state.editMode.parentPath = newPath;
    } else if (state.editMode && state.editMode.skillName === folderName && state.editMode.parentPath.startsWith(`${dirPath}/`)) {
      state.editMode.parentPath = newPath + state.editMode.parentPath.slice(dirPath.length);
    }
    renderOverlay();
  }

  async function renameTreeFile(folderName, filePath) {
    const baseName = filePath.split('/').pop() || filePath;
    const newName = await showTextDialog({
      title: 'Rename file',
      label: 'File name',
      value: baseName,
      confirmText: 'Rename'
    });
    if (!newName || newName === baseName) {
      return;
    }
    const parent = filePath.includes('/') ? filePath.replace(/\/[^/]+$/, '') : '';
    const newPath = parent ? `${parent}/${newName}` : newName;
    state.payload = await patchJson('/api/skills/path/', {
      folder: folderName,
      old_path: filePath,
      new_path: newPath,
      kind: 'file'
    });
    if (state.selectedFolder === folderName && state.selectedFile === filePath) {
      state.selectedFile = newPath;
    }
    renderOverlay();
  }

  function renderDirTools(folderName, dirPath) {
    const $tools = $('<div class="skills-tree-node-tools">');
    const $newFile = $('<button type="button" class="skills-tree-tool-btn" title="New file" aria-label="New file in folder">')
      .html(icons.SKILLS_FILE_ICON || '+');
    const $rename = $('<button type="button" class="skills-tree-tool-btn" title="Rename folder" aria-label="Rename folder">')
      .text('Aa');
    $newFile.on('click', function onNewFile(ev) {
      ev.stopPropagation();
      enterEditModeAt(folderName, dirPath, 'file');
    });
    $rename.on('click', function onRename(ev) {
      ev.stopPropagation();
      renameTreeDirectory(folderName, dirPath).catch(showError);
    });
    return $tools.append($newFile).append($rename);
  }

  function renderFileTools(folderName, filePath) {
    const $tools = $('<div class="skills-tree-node-tools">');
    const $rename = $('<button type="button" class="skills-tree-tool-btn" title="Rename file" aria-label="Rename file">')
      .text('Aa');
    $rename.on('click', function onRename(ev) {
      ev.stopPropagation();
      renameTreeFile(folderName, filePath).catch(showError);
    });
    return $tools.append($rename);
  }

  async function setEnabled(folderName, enabled) {
    state.payload = await patchJson('/api/skills/enabled/', { folder: folderName, enabled });
    renderOverlay();
  }

  async function loadCurrentFile() {
    if (!state.selectedFolder || !state.selectedFile) {
      state.currentFile = null;
      return;
    }
    state.currentFile = await getJson(
      `/api/skills/file/?folder=${encodeURIComponent(state.selectedFolder)}&file=${encodeURIComponent(state.selectedFile)}`
    );
  }

  function renderOverlay() {
    if (!$overlay || !$overlay.length || !$overlay.hasClass('is-open')) {
      return;
    }
    selectFallback();
    renderTreePane();
    renderDetailPane();
  }

  function renderTreeList() {
    if (!$middle || !$middle.length) {
      return;
    }
    let $group = $middle.find('.skills-personal-group');
    if (!$group.length) {
      renderTreePane();
      return;
    }
    $group.empty();
    const query = state.query;
    folderList()
      .filter((folder) => {
        if (!query) {
          return true;
        }
        return `${folder.name || ''} ${folder.title || ''} ${folder.description || ''}`.toLowerCase().includes(query);
      })
      .forEach((folder) => $group.append(renderSkillFolder(folder)));
  }

  function renderTreePane() {
    if (!$middle || !$middle.length) {
      return;
    }
    $middle.empty();
    const $head = $('<div class="skills-tree-head">');
    const $closeBtn = $('<button type="button" class="skills-manager-close skills-tree-close" aria-label="Close skills manager">')
      .html(icons.CLOSE_ICON || '<span aria-hidden="true">×</span>');
    const $title = $('<div class="skills-tree-title">').text('Skills');
    const $actions = $('<div class="skills-tree-actions">');
    const $addBtn = $('<button type="button" class="skills-icon-btn" title="Add skill" aria-label="Add skill">').html(icons.ADD_ICON || '+');
    $actions.append($addBtn);
    $head.append($closeBtn).append($title).append($actions);

    $closeBtn.on('click', closeManager);

    const $search = $('<input class="skills-search-input" type="search" placeholder="Search skills">').val(state.query);
    $search.on('input', function onSearch() {
      state.query = String(this.value || '').toLowerCase();
      renderTreeList();
    });
    $addBtn.on('click', function onAdd() {
      showAddSkillsDialog().catch(showError);
    });

    $middle.append($head).append($search).append($('<div class="skills-personal-group">'));
    renderTreeList();
  }

  function renderSkillFolder(folder) {
    const folderName = String(folder.name || '');
    const isExpanded = state.expandedSkills.has(folderName);
    const $wrap = $('<div class="skills-folder-wrap">');
    const $cascade = $('<div class="skills-tree-cascade">');
    const $row = $('<div class="skills-folder-row skills-tree-dir-row">');
    const $button = $('<button type="button" class="skills-folder-main">');
    const folderIcon = isExpanded ? (icons.SKILLS_FOLDER_OPEN_ICON || '') : (icons.SKILLS_FOLDER_ICON || '');
    const $icon = $('<span class="skills-tree-icon" aria-hidden="true">').html(folderIcon);
    const $name = $('<span class="skills-folder-name">').text(folder.title || folderName);
    const $actions = $('<button type="button" class="skills-folder-actions" aria-label="Skill actions">').text('...');
    const $toggle = $('<button type="button" class="skills-tree-caret" aria-label="Toggle skill files">')
      .toggleClass('is-expanded', isExpanded);
    $button.append($icon).append($name);
    $row.append($button).append($actions).append($toggle);
    $button.on('click', function onSelect() {
      if (state.editMode && state.editMode.skillName !== folderName) {
        state.editMode = null;
      }
      state.selectedFolder = folderName;
      state.selectedFile = firstFile(folder);
      state.expandedSkills.add(folderName);
      loadCurrentFile().catch(showError).finally(renderOverlay);
    });
    $toggle.on('click', function onToggle(ev) {
      ev.stopPropagation();
      if (isExpanded) {
        state.expandedSkills.delete(folderName);
      } else {
        state.expandedSkills.add(folderName);
      }
      renderTreeList();
    });
    $actions.on('click', function onFolderActions(ev) {
      ev.stopPropagation();
      state.selectedFolder = folderName;
      if (!state.selectedFile) {
        state.selectedFile = firstFile(folder);
      }
      openSkillActions(folder, $actions);
      renderDetailPane();
    });
    $cascade.append($row);
    if (isExpanded) {
      appendTreeToCascade($cascade, folderName, folder.tree || []);
      const editMode = state.editMode;
      if (editMode && editMode.skillName === folderName && editMode.parentPath === '') {
        $cascade.append(renderEditComposer(folderName, ''));
      }
    }
    return $wrap.append($cascade);
  }

  function appendTreeToCascade($cascade, folderName, nodes) {
    (Array.isArray(nodes) ? nodes : []).forEach(function visit(node) {
      if (!node || typeof node !== 'object') {
        return;
      }
      const path = String(node.path || '');
      if (node.type === 'directory') {
        $cascade.append(renderDirRow(folderName, node));
        const key = `${folderName}/${path}`;
        if (state.expandedDirs.has(key)) {
          appendTreeToCascade($cascade, folderName, node.children || []);
          const editMode = state.editMode;
          if (editMode && editMode.skillName === folderName && editMode.parentPath === path) {
            $cascade.append(renderEditComposer(folderName, path));
          }
        }
        return;
      }
      $cascade.append(renderFileRow(folderName, node));
    });
  }

  function renderDirRow(folderName, node) {
    const path = String(node.path || '');
    const key = `${folderName}/${path}`;
    const expanded = state.expandedDirs.has(key);
    const dirIcon = expanded ? (icons.SKILLS_FOLDER_OPEN_ICON || '') : (icons.SKILLS_FOLDER_ICON || '');
    const $rowWrap = $('<div class="skills-tree-node-row skills-tree-dir-row">');
    const $row = $('<button type="button" class="skills-tree-node is-dir">');
    const $toggle = $('<button type="button" class="skills-tree-caret" aria-label="Toggle folder">')
      .toggleClass('is-expanded', expanded);
    function toggleExpanded(ev) {
      if (ev) {
        ev.stopPropagation();
      }
      if (expanded) {
        state.expandedDirs.delete(key);
      } else {
        state.expandedDirs.add(key);
      }
      renderTreeList();
    }
    $row.append(
      $('<span class="skills-tree-icon" aria-hidden="true">').html(dirIcon),
      $('<span class="skills-tree-label">').text(node.name || path)
    );
    $row.on('click', toggleExpanded);
    $toggle.on('click', toggleExpanded);
    return $rowWrap.append($row).append(renderDirTools(folderName, path)).append($toggle);
  }

  function renderFileRow(folderName, node) {
    const path = String(node.path || '');
    const selected = folderName === state.selectedFolder && path === state.selectedFile;
    const $rowWrap = $('<div class="skills-tree-node-row skills-tree-file-row">')
      .toggleClass('is-active', selected);
    const $file = $('<button type="button" class="skills-tree-node is-file">');
    const $delete = $('<button type="button" class="skills-tree-delete-btn" title="Delete file" aria-label="Delete file">')
      .html(icons.CLOSE_ICON || '×');
    $delete.on('click', function onDelete(ev) {
      ev.stopPropagation();
      deleteFile(folderName, path).catch(showError);
    });
    $file.append(
      $('<span class="skills-tree-icon" aria-hidden="true">').html(icons.SKILLS_FILE_ICON || ''),
      $('<span class="skills-tree-label">').text(node.name || path)
    );
    $file.on('click', function onFileSelect() {
      state.selectedFolder = folderName;
      state.selectedFile = path;
      loadCurrentFile().catch(showError).finally(renderOverlay);
    });
    return $rowWrap.append($file).append(renderFileTools(folderName, path)).append($delete);
  }

  function renderEditComposer(folderName, parentPath) {
    const editMode = state.editMode;
    if (!editMode) {
      return $();
    }
    const isFile = editMode.createKind === 'file';
    const $row = $('<div class="skills-edit-composer">');
    const kindIcon = isFile ? (icons.SKILLS_FILE_ICON || '') : (icons.SKILLS_FOLDER_ICON || '');
    const $kindBtn = $('<button type="button" class="skills-edit-kind-toggle" aria-label="Toggle folder or file">')
      .html(kindIcon);
    const $input = $('<input class="skills-edit-input" type="text" autocomplete="off" spellcheck="false">')
      .attr('placeholder', isFile ? 'New file name (e.g. grader.md)' : 'New folder name');
    const $error = $('<div class="skills-edit-error" role="alert">').hide();

    $kindBtn.on('click', function onKindToggle(ev) {
      ev.stopPropagation();
      editMode.createKind = isFile ? 'folder' : 'file';
      renderTreeList();
      focusComposerInput();
    });

    $input.on('keydown', function onKey(ev) {
      if (ev.key === 'Escape') {
        ev.preventDefault();
        exitEditMode();
        return;
      }
      if (ev.key !== 'Enter') {
        return;
      }
      ev.preventDefault();
      const name = String($input.val() || '').trim();
      if (!name) {
        return;
      }
      const promise = isFile
        ? submitComposerFile(folderName, parentPath, name)
        : submitComposerFolder(folderName, parentPath, name);
      promise.catch(function onComposerError(err) {
        $error.text(err && err.message ? err.message : String(err)).show();
      });
    });

    $input.on('input', function onInput() {
      $error.hide();
    });

    $row.append($kindBtn).append($input).append($error);
    return $row;
  }

  function renderDetailPane() {
    if (!$detail || !$detail.length) {
      return;
    }
    const folder = findFolder(state.selectedFolder);
    $detail.empty();
    if (!folder) {
      $detail.append($('<div class="skills-empty-state">').text('Create a skill to get started.'));
      return;
    }

    const $top = $('<div class="skills-detail-topbar">');
    const $title = $('<div class="skills-detail-title">').text(folder.title || folder.name);
    const $controls = $('<div class="skills-detail-controls">');
    const $toggle = $('<label class="skills-enabled-toggle" title="Enable skill">')
      .append($('<input type="checkbox">').prop('checked', folder.enabled !== false))
      .append($('<span>'));
    $toggle.find('input').on('change', function onEnabledChange() {
      setEnabled(folder.name, this.checked).catch(showError);
    });
    $controls.append($toggle);
    $top.append($title).append($controls);

    const $meta = $('<div class="skills-meta-grid skills-meta-grid--created">').append(
      metaBlock('Created', formatCreatedAt(folder.created_at))
    );

    const $panel = $('<div class="skills-content-panel">');
    const $panelTools = $('<div class="skills-panel-tools">');
    const $previewBtn = $('<button type="button" class="skills-panel-toggle">').toggleClass('is-active', state.mode === 'preview').html(icons.EYE_ICON || 'Preview');
    const $sourceBtn = $('<button type="button" class="skills-panel-toggle">').toggleClass('is-active', state.mode === 'source').text('</>');
    $previewBtn.on('click', function onPreview() {
      state.mode = 'preview';
      renderDetailPane();
    });
    $sourceBtn.on('click', function onSource() {
      state.mode = 'source';
      loadCurrentFile().catch(showError).finally(renderDetailPane);
    });
    $panelTools.append($previewBtn).append($sourceBtn);
    $panel.append($panelTools);

    if (state.mode === 'source') {
      renderSourceEditor($panel);
    } else {
      renderPreview($panel);
    }

    $detail.append($top).append($meta).append($panel);
    if (state.mode === 'preview' && (!state.currentFile || state.currentFile.file !== state.selectedFile)) {
      loadCurrentFile().then(renderDetailPane).catch(showError);
    }
  }

  function metaBlock(label, value) {
    return $('<div class="skills-meta-block">')
      .append($('<div class="skills-meta-label">').text(label))
      .append($('<div class="skills-meta-value">').text(value));
  }

  function formatCreatedAt(timestamp) {
    const value = Number(timestamp);
    if (!Number.isFinite(value) || value <= 0) {
      return 'Unknown';
    }
    const date = new Date(value * 1000);
    if (Number.isNaN(date.getTime())) {
      return 'Unknown';
    }
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  function enterEditMode(folderName) {
    enterEditModeAt(folderName, deriveEditParentPath(folderName), 'folder');
  }

  function exitEditMode() {
    state.editMode = null;
    renderTreePane();
  }

  function deriveEditParentPath(folderName) {
    const file = state.selectedFile;
    if (!file || state.selectedFolder !== folderName) {
      return '';
    }
    const parts = file.replace(/\\/g, '/').split('/');
    if (parts.length <= 1) {
      return '';
    }
    return parts.slice(0, -1).join('/');
  }

  async function submitComposerFolder(folderName, parentPath, name) {
    const dirPath = parentPath ? `${parentPath}/${name}` : name;
    state.payload = await postJson('/api/skills/directory/', { folder: folderName, path: dirPath });
    state.selectedFolder = folderName;
    state.expandedSkills.add(folderName);
    state.expandedDirs.add(`${folderName}/${dirPath}`);
    exitEditMode();
  }

  async function submitComposerFile(folderName, parentPath, rawName) {
    const allowedExtensions = Array.isArray(state.payload.allowed_extensions)
      ? state.payload.allowed_extensions
      : [];
    let name = rawName;
    const lastDot = name.lastIndexOf('.');
    const hasExt = lastDot > 0 && lastDot < name.length - 1;
    if (!hasExt) {
      name += '.md';
    }
    const filePath = parentPath ? `${parentPath}/${name}` : name;
    const title = name.replace(/\.[^.]+$/, '');
    const stub = name.endsWith('.md') ? `# ${title}\n\n` : '';
    state.payload = await requestJson('/api/skills/file/', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder: folderName, file: filePath, content: stub })
    });
    state.selectedFolder = folderName;
    state.selectedFile = filePath;
    state.expandedSkills.add(folderName);
    if (parentPath) {
      state.expandedDirs.add(`${folderName}/${parentPath}`);
    }
    await loadCurrentFile();
    exitEditMode();
  }

  function openSkillActions(folder, $anchor) {
    $('.skills-action-menu').remove();
    const $menu = $('<div class="skills-action-menu" role="menu">');
    const isEditing = state.editMode && state.editMode.skillName === folder.name;
    const actions = [
      [isEditing ? 'Done editing' : 'Edit skill', () => {
        if (isEditing) {
          exitEditMode();
        } else {
          enterEditMode(folder.name);
        }
      }],
      ['Rename skill', () => renameSkill(folder.name)],
      ['Delete skill', () => deleteSkill(folder.name)]
    ];
    actions.forEach(function addAction([label, handler]) {
      const $item = $('<button type="button" role="menuitem">').text(label);
      if (label.startsWith('Delete')) {
        $item.addClass('is-danger');
      }
      $item.on('click', function onAction(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        $menu.remove();
        handler();
      });
      $menu.append($item);
    });
    $('body').append($menu);
    const rect = $anchor[0].getBoundingClientRect();
    $menu.css({
      top: `${rect.bottom + 6}px`,
      right: `${Math.max(12, window.innerWidth - rect.right)}px`
    });
    setTimeout(function bindClose() {
      $(document).one('click.skillsActionMenu', function closeMenu() {
        $menu.remove();
      });
    }, 0);
  }

  function renderPreview($panel) {
    const file = state.currentFile && state.currentFile.file === state.selectedFile
      ? state.currentFile
      : null;
    const content = file && typeof file.content === 'string' ? file.content : '';
    const selected = state.selectedFile || '';
    const $preview = $('<div class="skills-preview markdown-body">');
    if (!selected) {
      $preview.text('No file selected.');
    } else if (selected.toLowerCase().endsWith('.md') && typeof marked !== 'undefined') {
      const rawHtml = marked.parse(stripFrontMatter(content));
      $preview.html(typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(rawHtml) : rawHtml);
    } else {
      $preview.append($('<pre>').text(content || ''));
    }
    $panel.append($preview);
  }

  function stripFrontMatter(content) {
    return String(content || '').replace(/^---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)/, '');
  }

  function renderSourceEditor($panel) {
    const file = state.currentFile;
    const content = file && typeof file.content === 'string' ? file.content : '';
    const $editor = $('<div class="skills-source-editor">');
    const $body = $('<div class="skills-source-body">');
    const $gutter = $('<div class="skills-source-gutter" aria-hidden="true">');
    const $cell = $('<div class="skills-source-cell">');
    const $highlight = $('<pre class="skills-source-highlight"><code></code></pre>');
    const $textarea = $('<textarea class="skills-source-textarea" spellcheck="false" autocapitalize="off" autocomplete="off" autocorrect="off">').val(content);
    const $actions = $('<div class="skills-source-actions">');
    const $save = $('<button type="button" class="preset-action-btn preset-action-btn-primary">').text('Save');
    const $path = $('<div class="skills-source-path">').text(state.selectedFile || '');

    function syncEditor() {
      const raw = $textarea.val();
      const lineCount = Math.max(1, String(raw || '').split('\n').length);
      $gutter.text(Array.from({ length: lineCount }, (_, index) => String(index + 1)).join('\n'));
      $highlight.find('code').html(highlightCode(raw, state.selectedFile));
    }

    $textarea.on('input', syncEditor);
    $textarea.on('scroll', function onScroll() {
      $highlight.css('transform', `translateY(-${$textarea.scrollTop()}px)`);
      $gutter.css('transform', `translateY(-${$textarea.scrollTop()}px)`);
    });
    $save.on('click', async function onSave() {
      try {
        state.payload = await requestJson('/api/skills/file/', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ folder: state.selectedFolder, file: state.selectedFile, content: $textarea.val() })
        });
        await loadCurrentFile();
        renderOverlay();
      } catch (error) {
        showError(error);
      }
    });
    $cell.append($highlight).append($textarea);
    $body.append($gutter).append($cell);
    $actions.append($path).append($save);
    $editor.append($body).append($actions);
    $panel.append($editor);
    requestAnimationFrame(syncEditor);
  }

  function highlightCode(source, filePath) {
    const text = String(source || '');
    if (typeof hljs === 'undefined' || !hljs.highlight) {
      return escapeHtml(text);
    }
    const language = languageForPath(filePath);
    try {
      return language
        ? hljs.highlight(text, { language, ignoreIllegals: true }).value
        : hljs.highlightAuto(text).value;
    } catch (_err) {
      return escapeHtml(text);
    }
  }

  function languageForPath(filePath) {
    const lower = String(filePath || '').toLowerCase();
    if (lower.endsWith('.md')) return 'markdown';
    if (lower.endsWith('.py')) return 'python';
    if (lower.endsWith('.js')) return 'javascript';
    if (lower.endsWith('.ts')) return 'typescript';
    if (lower.endsWith('.json')) return 'json';
    if (lower.endsWith('.yaml') || lower.endsWith('.yml')) return 'yaml';
    if (lower.endsWith('.html')) return 'xml';
    if (lower.endsWith('.css')) return 'css';
    if (lower.endsWith('.sh')) return 'bash';
    if (lower.endsWith('.ps1')) return 'powershell';
    return '';
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function init() {
    renderSidebarSummary();
    loadSkills().catch(function ignoreInitialLoad(error) {
      if (typeof window.console !== 'undefined' && window.console.warn) {
        window.console.warn(error);
      }
    });
  }

  return {
    init,
    openManager
  };
}
