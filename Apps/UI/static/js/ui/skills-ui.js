// Copyright NGGT.LightKeeper. All Rights Reserved.

import { getJson, patchJson, postJson, requestJson } from '../main/api.js';
import { intlLocaleTag, t } from '../main/i18n.js';

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

  // Skill tree helpers.
  // Read the folder list from the latest skills payload.
  function folderList() {
    return Array.isArray(state.payload.folders) ? state.payload.folders : [];
  }

  // Find one skill folder record by name.
  function findFolder(name) {
    return folderList().find((folder) => String(folder.name || '') === String(name || '')) || null;
  }

  // Walk a directory tree and invoke a visitor for every node.
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

  // Return the first file path inside one folder for default selection.
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

  // Pick a default folder and file when the current selection is invalid.
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


  // Skills manager lifecycle.
  // Load skills payload from the backend and refresh all surfaces.
  async function loadSkills() {
    state.payload = await getJson('/api/skills/');
    selectFallback();
    renderSidebarSummary();
    renderComposerSkillsMenu();
    renderOverlay();
  }

  // Render the compact skills summary in the settings sidebar.
  function renderSidebarSummary() {
    if (!dom.$skillsSettingsContent || !dom.$skillsSettingsContent.length) {
      return;
    }
    const count = folderList().length;
    dom.$skillsSettingsContent.empty();
    const $btn = $('<button type="button" class="preset-action-btn skills-open-btn">').text(t('skills.manage'));
    const $summary = $('<div class="skills-settings-summary">').text(
      count === 1 ? t('skills.personalSkillOne') : t('skills.personalSkillMany', { count })
    );
    $btn.on('click', openManager);
    dom.$skillsSettingsContent.append($btn).append($summary);
  }

  // Create the full-screen skills manager overlay when needed.
  function ensureOverlay() {
    if ($overlay && $overlay.length) {
      return;
    }
    $overlay = $('<div class="skills-manager-backdrop" role="dialog" aria-modal="true">')
      .attr('aria-label', t('skills.customizeAria'));
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

  // Open the skills manager modal and load data.
  function openManager() {
    ensureOverlay();
    $('body').addClass('skills-manager-open');
    $overlay.addClass('is-open');
    loadSkills().catch(showError);
  }

  // Close the skills manager modal.
  function closeManager() {
    $('body').removeClass('skills-manager-open');
    if ($overlay) {
      $overlay.removeClass('is-open');
    }
  }

  // Surface one skills error in the detail pane or a dialog.
  function showError(error) {
    const message = error && error.message ? error.message : String(error);
    if ($detail && $detail.length) {
      $detail.find('.skills-detail-error').remove();
      $detail.prepend($('<div class="skills-detail-error" role="alert">').text(message));
    } else {
      showMessageDialog(t('skills.errorTitle'), message);
    }
  }

  // Show a simple acknowledgement dialog.
  function showMessageDialog(title, message) {
    return showConfirmDialog({
      title,
      message,
      confirmText: t('skills.dialogOk'),
      cancelText: '',
      danger: false
    });
  }

  // Inline dialog helpers.
  function showTextDialog(options) {
    ensureOverlay();
    return new Promise(function textDialogPromise(resolve) {
      const dialogOptions = options || {};
      const $backdrop = $('<div class="skills-inline-dialog-backdrop" role="dialog" aria-modal="true">');
      const $dialog = $('<div class="skills-inline-dialog">');
      const $title = $('<div class="skills-inline-dialog-title">').text(dialogOptions.title || t('skills.dialogInput'));
      const $label = $('<label class="skills-inline-dialog-label">').text(dialogOptions.label || '');
      const $input = $('<input class="skills-inline-dialog-input" type="text">')
        .val(dialogOptions.value || '')
        .attr('placeholder', dialogOptions.placeholder || '');
      const $error = $('<div class="skills-inline-dialog-error" role="alert">').hide();
      const $actions = $('<div class="skills-inline-dialog-actions">');
      const $cancel = $('<button type="button" class="preset-action-btn">').text(t('skills.dialogCancel'));
      const $confirm = $('<button type="button" class="preset-action-btn preset-action-btn-primary">').text(dialogOptions.confirmText || t('skills.dialogOk'));

      function close(value) {
        $backdrop.remove();
        resolve(value);
      }

      function submit() {
        const value = String($input.val() || '').trim();
        if (!value) {
          $error.text(t('skills.valueRequired')).show();
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

  // Show a confirm or cancel dialog inside the skills manager.
  function showConfirmDialog(options) {
    ensureOverlay();
    return new Promise(function confirmDialogPromise(resolve) {
      const dialogOptions = options || {};
      const $backdrop = $('<div class="skills-inline-dialog-backdrop" role="dialog" aria-modal="true">');
      const $dialog = $('<div class="skills-inline-dialog">');
      const $title = $('<div class="skills-inline-dialog-title">').text(dialogOptions.title || t('skills.dialogConfirm'));
      const $message = $('<div class="skills-inline-dialog-message">').text(dialogOptions.message || '');
      const $actions = $('<div class="skills-inline-dialog-actions">');
      const cancelText = dialogOptions.cancelText === undefined ? t('skills.dialogCancel') : String(dialogOptions.cancelText || '');
      const $confirm = $('<button type="button" class="preset-action-btn preset-action-btn-primary">')
        .toggleClass('preset-action-btn-danger', Boolean(dialogOptions.danger))
        .text(dialogOptions.confirmText || t('skills.dialogOk'));

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

  // Read one File object as UTF-8 text.
  function readFileAsText(file) {
    return new Promise(function readPromise(resolve, reject) {
      const reader = new FileReader();
      reader.onload = function onLoad(ev) { resolve(ev.target.result || ''); };
      reader.onerror = function onErr() {
        reject(new Error(t('skills.readFileFailed', { name: file.name })));
      };
      reader.readAsText(file);
    });
  }

  // Read the first path segment from a relative import path.
  function firstPathSegment(relativePath) {
    const norm = String(relativePath || '').replace(/\\/g, '/').replace(/^\/+/, '');
    const slash = norm.indexOf('/');
    return slash === -1 ? norm : norm.slice(0, slash);
  }

  // Strip the skill root prefix from one relative path.
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

  // Report whether one filename extension is allowed for import.
  function isAllowedImportFileName(fileName) {
    const ext = ('.' + String(fileName || '').split('.').pop()).toLowerCase();
    return ALLOWED_IMPORT_EXTENSIONS.has(ext);
  }

  // Read every entry from one directory reader batch.
  async function readAllDirectoryEntries(dirReader) {
    const all = [];
    let batch = [];
    do {
      batch = await new Promise(function (res, rej) { dirReader.readEntries(res, rej); });
      all.push(...batch);
    } while (batch.length > 0);
    return all;
  }

  // Collect allowed files from one filesystem entry tree.
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

  // Collect files from one dropped directory entry.
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

  // Collect files from one File System Access directory.
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

  // Collect files from one flat FileList under a skill root.
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

  // Group imported files by top-level skill folder name.
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

  // Resolve one import source into skill folder payloads.
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
        throw new Error(t('skills.importNameHintDropOne'));
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
      throw new Error(t('skills.importNameHintSelect'));
    }

    throw new Error(t('skills.importNoFiles'));
  }

  // Upload one resolved skill import to the backend.
  async function importSkillFromSource(source, explicitName) {
    const payloads = await resolveImportPayloads(source, explicitName);
    if (!payloads.length) {
      throw new Error(t('skills.importNoSupported'));
    }

    for (const payload of payloads) {
      const skillName = String(payload.skillName || '').trim();
      if (!skillName) {
        throw new Error(t('skills.skillNameRequired'));
      }
      if (!payload.files || !payload.files.length) {
        throw new Error(t('skills.importNoSupportedFor', { name: skillName }));
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

  // Show the add-skills import dialog.
  function showAddSkillsDialog() {
    ensureOverlay();
    return new Promise(function addDialogPromise(resolve) {
      const $backdrop = $('<div class="skills-inline-dialog-backdrop" role="dialog" aria-modal="true">');
      const $dialog = $('<div class="skills-inline-dialog skills-add-dialog">');

      // --- Create section ---
      const $createSection = $('<div class="skills-add-section">');
      const $createLabel = $('<div class="skills-add-section-title">').text(t('skills.createSkill'));
      const $createRow = $('<div class="skills-add-create-row">');
      const $nameInput = $('<input class="skills-inline-dialog-input" type="text" autocomplete="off" spellcheck="false">')
        .attr('placeholder', t('skills.skillNamePlaceholder'));
      const $createBtn = $('<button type="button" class="preset-action-btn preset-action-btn-primary">').text(t('skills.create'));
      const $createError = $('<div class="skills-inline-dialog-error" role="alert">').hide();
      $createRow.append($nameInput).append($createBtn);
      $createSection.append($createLabel).append($createRow).append($createError);

      // --- Divider ---
      const $divider = $('<div class="skills-add-divider">');

      // --- Import section ---
      const $importSection = $('<div class="skills-add-section">');
      const $importLabel = $('<div class="skills-add-section-title">').text(t('skills.importSkillFolder'));
      const $dropzone = $('<div class="skills-import-dropzone" role="button" tabindex="0">')
        .attr('aria-label', t('skills.dropzoneAria'));
      const $dropzoneText = $('<div class="skills-import-dropzone-text">').text(t('skills.dropzoneText'));
      const $dropzoneHint = $('<div class="skills-import-dropzone-hint">').text(t('skills.or'));
      const $browseBtn = $('<button type="button" class="preset-action-btn">').text(t('skills.browseFolder'));
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
          $createError.text(t('skills.skillNameRequired')).show();
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
        $importStatus.text(t('skills.importing')).removeClass('is-error').show();
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

  // Skill folder mutations.
  async function createSkill() {
    const name = await showTextDialog({
      title: t('skills.newSkill'),
      label: t('skills.skillFolderName'),
      placeholder: t('skills.skillFolderNamePlaceholder'),
      confirmText: t('skills.create')
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

  // Rename one skill folder on the server.
  async function renameSkill(folderName) {
    const nextName = await showTextDialog({
      title: t('skills.renameSkill'),
      label: t('skills.newSkillFolderName'),
      value: folderName,
      confirmText: t('sidebar.rename')
    });
    if (!nextName || nextName === folderName) {
      return;
    }
    state.payload = await patchJson('/api/skills/folder/', { old_name: folderName, new_name: nextName });
    state.selectedFolder = nextName.trim();
    state.expandedSkills.add(state.selectedFolder);
    renderOverlay();
  }

  // Delete one skill folder on the server.
  async function deleteSkill(folderName) {
    const confirmed = await showConfirmDialog({
      title: t('skills.deleteSkill'),
      message: t('skills.deleteSkillConfirm', { name: folderName }),
      confirmText: t('sidebar.delete'),
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

  // Create one new file inside a skill folder.
  async function createFile(folderName) {
    const filePath = await showTextDialog({
      title: t('skills.newSkillFile'),
      label: t('skills.filePathInSkill'),
      value: 'SKILL.md',
      placeholder: t('skills.filePathPlaceholder'),
      confirmText: t('skills.create')
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

  // Delete one file from a skill folder.
  async function deleteFile(folderName, filePath, options) {
    if (!filePath) {
      return;
    }
    const opts = options || {};
    if (!opts.skipConfirm) {
      const confirmed = await showConfirmDialog({
        title: t('skills.deleteFile'),
        message: t('skills.deleteFileConfirm'),
        confirmText: t('sidebar.delete'),
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

  // Skills tree UI rendering.
  function expandDirAncestors(folderName, dirPath) {
    if (!dirPath) {
      return;
    }
    const parts = dirPath.split('/').filter(Boolean);
    for (let index = 1; index <= parts.length; index += 1) {
      state.expandedDirs.add(`${folderName}/${parts.slice(0, index).join('/')}`);
    }
  }

  // Update expanded directory paths after a rename.
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

  // Focus the active chat composer input.
  function focusComposerInput() {
    requestAnimationFrame(function focusComposer() {
      const $input = $middle && $middle.find('.skills-edit-input').first();
      if ($input && $input.length) {
        $input.trigger('focus');
      }
    });
  }

  // Enter inline create mode at one tree location.
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

  // Rename one directory in the skills tree.
  async function renameTreeDirectory(folderName, dirPath) {
    const baseName = dirPath.split('/').pop() || dirPath;
    const newName = await showTextDialog({
      title: t('skills.renameFolder'),
      label: t('skills.folderName'),
      value: baseName,
      confirmText: t('sidebar.rename')
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

  // Rename one file in the skills tree.
  async function renameTreeFile(folderName, filePath) {
    const baseName = filePath.split('/').pop() || filePath;
    const newName = await showTextDialog({
      title: t('skills.renameFile'),
      label: t('skills.fileName'),
      value: baseName,
      confirmText: t('sidebar.rename')
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

  // Render action buttons for one directory row.
  function renderDirTools(folderName, dirPath) {
    const $tools = $('<div class="skills-tree-node-tools">');
    const $newFile = $('<button type="button" class="skills-tree-tool-btn">')
      .attr('title', t('skills.newFileAria'))
      .attr('aria-label', t('skills.newFileAria'))
      .html(icons.SKILLS_FILE_ICON || '+');
    const $rename = $('<button type="button" class="skills-tree-tool-btn">')
      .attr('title', t('skills.renameFolderAria'))
      .attr('aria-label', t('skills.renameFolderAria'))
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

  // Render action buttons for one file row.
  function renderFileTools(folderName, filePath) {
    const $tools = $('<div class="skills-tree-node-tools">');
    const $rename = $('<button type="button" class="skills-tree-tool-btn">')
      .attr('title', t('skills.renameFileAria'))
      .attr('aria-label', t('skills.renameFileAria'))
      .text('Aa');
    $rename.on('click', function onRename(ev) {
      ev.stopPropagation();
      renameTreeFile(folderName, filePath).catch(showError);
    });
    return $tools.append($rename);
  }

  // Sync one skill checkbox in the composer menu.
  function syncComposerSkillCheckbox(folderName) {
    const folder = findFolder(folderName);
    if (!folder) {
      return;
    }
    const enabled = folder.enabled !== false;
    dom.$composerSkillsHosts.find('.composer-skill-row').each(function syncRow() {
      const $row = $(this);
      if (String($row.attr('data-skill-name') || '') === String(folderName)) {
        $row.find('.tool-server-checkbox').prop('checked', enabled);
      }
    });
  }

  // Enable or disable one skill folder for the active chat.
  async function setEnabled(folderName, enabled) {
    state.payload = await patchJson('/api/skills/enabled/', { folder: folderName, enabled });
    syncComposerSkillCheckbox(folderName);
    renderOverlay();
  }

  // Rebuild the composer skills flyout menu.
  function renderComposerSkillsMenu() {
    if (!dom.$composerSkillsHosts || !dom.$composerSkillsHosts.length) {
      return;
    }
    const folders = folderList();
    const chevron = '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round"></path></svg>';

    dom.$composerSkillsHosts.each(function fillHost() {
      const $host = $(this);
      $host.empty();

      const $entry = $('<div class="composer-skills-entry">');
      const $trigger = $('<button type="button" class="composer-tool-row composer-skills-trigger" aria-haspopup="menu">');
      const $icon = $('<span class="composer-tool-icon is-skills" aria-hidden="true">');
      const $name = $('<span class="tool-server-name">').text(t('skills.title'));
      const $chev = $('<span class="composer-skills-chevron" aria-hidden="true">').html(chevron);
      $trigger.append($icon).append($name).append($chev);

      const $flyout = $('<div class="composer-skills-flyout" role="menu">')
        .attr('aria-label', t('skills.composerMenuAria'));
      const $list = $('<div class="composer-skills-flyout-list">');

      if (!folders.length) {
        $list.append($('<div class="composer-skills-empty">').text(t('skills.noSkillsYet')));
      } else {
        folders.forEach(function renderSkillRow(folder) {
          const folderName = String(folder.name || '');
          const label = String(folder.title || folderName).trim() || folderName;
          const $row = $('<label class="tool-server-row composer-tool-row composer-skill-row">')
            .attr('data-skill-name', folderName);
          const $rowIcon = $('<span class="composer-tool-icon is-skills-file" aria-hidden="true">');
          const $rowName = $('<span class="tool-server-name">').text(label);
          const $checkbox = $('<input type="checkbox" class="tool-server-checkbox">')
            .prop('checked', folder.enabled !== false);
          $row.on('mousedown click', function onSkillRowPointer(ev) {
            ev.stopPropagation();
          });
          $checkbox.on('mousedown click change', function onSkillCheckboxPointer(ev) {
            ev.stopPropagation();
          });
          $checkbox.on('change', function onEnabledChange() {
            const checked = this.checked;
            setEnabled(folderName, checked).catch(function onEnabledError(error) {
              $checkbox.prop('checked', !checked);
              showError(error);
            });
          });
          $row.append($rowIcon).append($rowName).append($checkbox);
          $list.append($row);
        });
      }

      const $manage = $('<button type="button" class="composer-menu-action composer-skills-manage" role="menuitem">')
        .append($('<span class="composer-tool-icon is-skills" aria-hidden="true">'))
        .append($('<span>').text(t('skills.manage')));
      $manage.on('click', function onManageClick(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        openManager();
      });

      $flyout.on('click', function onFlyoutClick(ev) {
        ev.stopPropagation();
      });
      $flyout.append($list).append($manage);
      $entry.append($trigger).append($flyout);
      $host.append($entry);
    });

    if (dom.$composerSkillsMenus && dom.$composerSkillsMenus.length) {
      dom.$composerSkillsMenus.show();
    }
  }

  // Load the selected skill file content from the server.
  async function loadCurrentFile() {
    if (!state.selectedFolder || !state.selectedFile) {
      state.currentFile = null;
      return;
    }
    state.currentFile = await getJson(
      `/api/skills/file/?folder=${encodeURIComponent(state.selectedFolder)}&file=${encodeURIComponent(state.selectedFile)}`
    );
  }

  // Render the full skills manager overlay shell.
  function renderOverlay() {
    if (!$overlay || !$overlay.length || !$overlay.hasClass('is-open')) {
      return;
    }
    selectFallback();
    renderTreePane();
    renderDetailPane();
  }

  // Render the skills sidebar tree list.
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

  // Render the skills tree pane with folders and files.
  function renderTreePane() {
    if (!$middle || !$middle.length) {
      return;
    }
    $middle.empty();
    const $head = $('<div class="skills-tree-head">');
    const $closeBtn = $('<button type="button" class="skills-manager-close skills-tree-close">')
      .attr('aria-label', t('skills.closeManagerAria'))
      .html(icons.CLOSE_ICON || '<span aria-hidden="true">×</span>');
    const $title = $('<div class="skills-tree-title">').text(t('skills.title'));
    const $actions = $('<div class="skills-tree-actions">');
    const $addBtn = $('<button type="button" class="skills-icon-btn">')
      .attr('title', t('skills.addSkillAria'))
      .attr('aria-label', t('skills.addSkillAria'))
      .html(icons.ADD_ICON || '+');
    $actions.append($addBtn);
    $head.append($closeBtn).append($title).append($actions);

    $closeBtn.on('click', closeManager);

    const $search = $('<input class="skills-search-input" type="search">')
      .attr('placeholder', t('skills.searchPlaceholder'))
      .val(state.query);
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

  // Render one skill folder section in the tree.
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
    const $actions = $('<button type="button" class="skills-folder-actions">')
      .attr('aria-label', t('skills.skillActionsAria'))
      .text('...');
    const $toggle = $('<button type="button" class="skills-tree-caret">')
      .attr('aria-label', t('skills.toggleSkillFilesAria'))
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
      appendTreeToCascade($cascade, folderName, folder.tree || [], 1);
      const editMode = state.editMode;
      if (editMode && editMode.skillName === folderName && editMode.parentPath === '') {
        $cascade.append(renderEditComposer(folderName, '', 1));
      }
    }
    return $wrap.append($cascade);
  }

  // Append tree nodes into one cascade submenu.
  function appendTreeToCascade($cascade, folderName, nodes, depth) {
    (Array.isArray(nodes) ? nodes : []).forEach(function visit(node) {
      if (!node || typeof node !== 'object') {
        return;
      }
      const path = String(node.path || '');
      if (node.type === 'directory') {
        $cascade.append(renderDirRow(folderName, node, depth));
        const key = `${folderName}/${path}`;
        if (state.expandedDirs.has(key)) {
          appendTreeToCascade($cascade, folderName, node.children || [], depth + 1);
          const editMode = state.editMode;
          if (editMode && editMode.skillName === folderName && editMode.parentPath === path) {
            $cascade.append(renderEditComposer(folderName, path, depth + 1));
          }
        }
        return;
      }
      $cascade.append(renderFileRow(folderName, node, depth));
    });
  }

  // Render one directory row in the skills tree.
  function renderDirRow(folderName, node, depth) {
    const path = String(node.path || '');
    const key = `${folderName}/${path}`;
    const expanded = state.expandedDirs.has(key);
    const dirIcon = expanded ? (icons.SKILLS_FOLDER_OPEN_ICON || '') : (icons.SKILLS_FOLDER_ICON || '');
    const $rowWrap = $('<div class="skills-tree-node-row skills-tree-dir-row">')
      .css('--skills-tree-depth', String(depth || 0));
    const $row = $('<button type="button" class="skills-tree-node is-dir">');
    const $toggle = $('<button type="button" class="skills-tree-caret">')
      .attr('aria-label', t('skills.toggleFolderAria'))
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

  // Render one file row in the skills tree.
  function renderFileRow(folderName, node, depth) {
    const path = String(node.path || '');
    const selected = folderName === state.selectedFolder && path === state.selectedFile;
    const $rowWrap = $('<div class="skills-tree-node-row skills-tree-file-row">')
      .css('--skills-tree-depth', String(depth || 0))
      .toggleClass('is-active', selected);
    const $file = $('<button type="button" class="skills-tree-node is-file">');
    const $delete = $('<button type="button" class="skills-tree-delete-btn">')
      .attr('title', t('skills.deleteFileAria'))
      .attr('aria-label', t('skills.deleteFileAria'))
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

  // Render the inline create-or-rename composer row.
  function renderEditComposer(folderName, parentPath, depth) {
    const editMode = state.editMode;
    if (!editMode) {
      return $();
    }
    const isFile = editMode.createKind === 'file';
    const $row = $('<div class="skills-edit-composer">')
      .css('--skills-tree-depth', String(depth || 0));
    const kindIcon = isFile ? (icons.SKILLS_FILE_ICON || '') : (icons.SKILLS_FOLDER_ICON || '');
    const $kindBtn = $('<button type="button" class="skills-edit-kind-toggle">')
      .attr('aria-label', t('skills.toggleKindAria'))
      .html(kindIcon);
    const $input = $('<input class="skills-edit-input" type="text" autocomplete="off" spellcheck="false">')
      .attr('placeholder', isFile ? t('skills.newFilePlaceholder') : t('skills.newFolderPlaceholder'));
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

  // Format one file path for the detail pane header.
  function formatDetailFilePath(folderName, filePath) {
    const folder = String(folderName || '').trim();
    const file = String(filePath || '').trim().replace(/^\/+/, '');
    if (!folder) {
      return file || t('skills.noFileSelected');
    }
    if (!file) {
      return folder;
    }
    return `${folder}/${file}`;
  }

  // Render the skills file detail pane.
  function renderDetailPane() {
    if (!$detail || !$detail.length) {
      return;
    }
    const folder = findFolder(state.selectedFolder);
    $detail.empty();
    if (!folder) {
      $detail.append($('<div class="skills-empty-state">').text(t('skills.emptyState')));
      return;
    }

    const $top = $('<div class="skills-detail-topbar">');
    const $title = $('<div class="skills-detail-title">').text(folder.title || folder.name);
    const $controls = $('<div class="skills-detail-controls skills-panel-tools">');
    const $previewBtn = $('<button type="button" class="skills-panel-toggle">')
      .toggleClass('is-active', state.mode === 'preview')
      .html(icons.EYE_ICON || t('skills.preview'));
    const $sourceBtn = $('<button type="button" class="skills-panel-toggle">').toggleClass('is-active', state.mode === 'source').text('</>');
    $previewBtn.on('click', function onPreview() {
      state.mode = 'preview';
      renderDetailPane();
    });
    $sourceBtn.on('click', function onSource() {
      state.mode = 'source';
      loadCurrentFile().catch(showError).finally(renderDetailPane);
    });
    $controls.append($previewBtn).append($sourceBtn);
    $top.append($title).append($controls);

    const $meta = $('<div class="skills-meta-grid skills-meta-grid--created">').append(
      metaBlock(t('skills.created'), formatCreatedAt(folder.created_at))
    );

    const $panel = $('<div class="skills-content-panel">');

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

  // Skill detail pane.
  function metaBlock(label, value) {
    return $('<div class="skills-meta-block">')
      .append($('<div class="skills-meta-label">').text(label))
      .append($('<div class="skills-meta-value">').text(value));
  }

  // Format one created-at timestamp for display.
  function formatCreatedAt(timestamp) {
    const value = Number(timestamp);
    if (!Number.isFinite(value) || value <= 0) {
      return t('skills.unknown');
    }
    const date = new Date(value * 1000);
    if (Number.isNaN(date.getTime())) {
      return t('skills.unknown');
    }
    return date.toLocaleString(intlLocaleTag(), {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  // Enter source edit mode for the selected skill file.
  function enterEditMode(folderName) {
    enterEditModeAt(folderName, deriveEditParentPath(folderName), 'folder');
  }

  // Leave source edit mode and return to preview.
  function exitEditMode() {
    state.editMode = null;
    renderTreePane();
  }

  // Derive the parent directory for inline tree editing.
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

  // Submit one inline folder create or rename action.
  async function submitComposerFolder(folderName, parentPath, name) {
    const dirPath = parentPath ? `${parentPath}/${name}` : name;
    state.payload = await postJson('/api/skills/directory/', { folder: folderName, path: dirPath });
    state.selectedFolder = folderName;
    state.expandedSkills.add(folderName);
    state.expandedDirs.add(`${folderName}/${dirPath}`);
    exitEditMode();
  }

  // Submit one inline file create action.
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

  // Open the floating actions menu for one skill folder.
  function openSkillActions(folder, $anchor) {
    $('.skills-action-menu').remove();
    const $menu = $('<div class="skills-action-menu" role="menu">');
    const isEditing = state.editMode && state.editMode.skillName === folder.name;
    const actions = [
      [isEditing ? t('skills.doneEditing') : t('skills.editSkill'), () => {
        if (isEditing) {
          exitEditMode();
        } else {
          enterEditMode(folder.name);
        }
      }],
      [t('skills.renameSkill'), () => renameSkill(folder.name)],
      [t('skills.deleteSkill'), () => deleteSkill(folder.name)]
    ];
    actions.forEach(function addAction([label, handler]) {
      const $item = $('<button type="button" role="menuitem">').text(label);
      if (label === t('skills.deleteSkill')) {
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

  // Render markdown preview for the selected skill file.
  function renderPreview($panel) {
    const file = state.currentFile && state.currentFile.file === state.selectedFile
      ? state.currentFile
      : null;
    const content = file && typeof file.content === 'string' ? file.content : '';
    const selected = state.selectedFile || '';
    const $preview = $('<div class="skills-preview markdown-body">');
    if (!selected) {
      $preview.text(t('skills.noFileSelectedPath'));
    } else if (selected.toLowerCase().endsWith('.md') && typeof marked !== 'undefined') {
      const rawHtml = marked.parse(stripFrontMatter(content));
      $preview.html(typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(rawHtml) : rawHtml);
    } else {
      $preview.append($('<pre>').text(content || ''));
    }
    $panel.append($preview);
  }

  // Remove YAML front matter from skill markdown content.
  function stripFrontMatter(content) {
    return String(content || '').replace(/^---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)/, '');
  }

  // Render the source editor for the selected skill file.
  function renderSourceEditor($panel) {
    const file = state.currentFile;
    const content = file && typeof file.content === 'string' ? file.content : '';
    const $editor = $('<div class="skills-source-editor">');
    const $body = $('<div class="skills-source-body">');
    const $gutter = $('<div class="skills-source-gutter" aria-hidden="true">');
    const $gutterInner = $('<div class="skills-source-gutter-inner">');
    const $cell = $('<div class="skills-source-cell">');
    const $highlight = $('<pre class="skills-source-highlight"><code></code></pre>');
    const $textarea = $('<textarea class="skills-source-textarea" spellcheck="false" autocapitalize="off" autocomplete="off" autocorrect="off">').val(content);
    const $actions = $('<div class="skills-source-actions">');
    const $path = $('<div class="skills-source-path">').text(
      formatDetailFilePath(state.selectedFolder, state.selectedFile)
    );
    const $save = $('<button type="button" class="preset-action-btn preset-action-btn-primary">').text(t('mcp.save'));

    function buildGutterLines(lineCount) {
      return Array.from({ length: lineCount }, function (_v, index) {
        return String(index + 1);
      }).join('\n');
    }

    function syncEditor() {
      const raw = String($textarea.val() || '');
      const lineCount = Math.max(1, raw.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n').length);
      $gutterInner.text(buildGutterLines(lineCount));
      const $code = $highlight.find('code');
      $code.html(highlightCode(raw, state.selectedFile));
      const scrollHeight = $textarea[0] ? $textarea[0].scrollHeight : 0;
      const minHeight = Math.max(scrollHeight, $textarea.outerHeight() || 0);
      $code.css('min-height', `${minHeight}px`);
    }

    function syncScroll() {
      const scrollTop = $textarea.scrollTop();
      $highlight.css('transform', `translateY(-${scrollTop}px)`);
      $gutterInner.css('transform', `translateY(-${scrollTop}px)`);
    }

    $gutter.append($gutterInner);
    $textarea.on('input', function onInput() {
      syncEditor();
      syncScroll();
    });
    $textarea.on('scroll', syncScroll);
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

  // Highlight source text with highlight.js when available.
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

  // Infer a highlight language from one file path.
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

  // Escape plain text for skills manager HTML output.
  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  // Skills manager bootstrap.
  function init() {
    renderSidebarSummary();
    renderComposerSkillsMenu();
    loadSkills().catch(function ignoreInitialLoad(error) {
      if (typeof window.console !== 'undefined' && window.console.warn) {
        window.console.warn(error);
      }
    });
  }

  return {
    init,
    openManager,
    renderComposerSkillsMenu,
    refreshComposerSkillsMenu: renderComposerSkillsMenu
  };
}
