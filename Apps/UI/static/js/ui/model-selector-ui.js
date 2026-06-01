// Copyright NGGT.LightKeeper. All Rights Reserved.

import { escHtml, parseJsonScript } from '../main/utils.js';

// Custom model selector.
// Mirrors the native select so existing model-loading code keeps working.
export function createModelSelectorUi(context) {
  const { dom, state } = context;
  const uiIconPaths = parseJsonScript('uiIconPathsData') || {};
  const rowHeight = 34;
  const overscan = 6;
  const eagerCapabilityLimit = 15;
  const maxCapabilityCacheEntries = 300;
  const capabilityCache = new Map();
  const pendingCapabilityRequests = new Set();
  const queuedCapabilityRequests = new Map();
  const maxConcurrentCapabilityRequests = 2;
  let activeCapabilityRequests = 0;
  let allModels = [];
  let filteredModels = [];
  let highlightedIndex = -1;
  let isOpen = false;
  let requestTimer = null;

  const $wrap = dom.$modelSelector.closest('.model-selector-wrap');
  const $button = $(`
    <button type="button" class="custom-model-select" id="customModelSelect" aria-haspopup="listbox" aria-expanded="false">
      <span class="custom-model-select-value"></span>
      <span class="custom-model-select-vision-slot"></span>
      <span class="custom-model-select-chevron" aria-hidden="true"></span>
    </button>
  `);
  const $popover = $(`
    <div class="custom-model-popover" id="customModelPopover" style="display:none;">
      <div class="custom-model-search-wrap">
        <input class="custom-model-search" id="customModelSearch" type="text" placeholder="Search models" autocomplete="off" spellcheck="false">
      </div>
      <div class="custom-model-list" id="customModelList" role="listbox"></div>
    </div>
  `);
  const $value = $button.find('.custom-model-select-value');
  const $search = $popover.find('.custom-model-search');
  const $list = $popover.find('.custom-model-list');

  // Model list helpers.
  // Read the currently selected model from the hidden native select.
  function selectedModel() {
    return String(dom.$modelSelector.val() || '').trim();
  }

  // Build one cache key for capability lookups.
  function cacheKey(modelName) {
    return `${String(state.activeEngine || '').trim()}::${String(modelName || '').trim()}`;
  }

  // Mirror option rows from the native model select element.
  function modelsFromNativeSelect() {
    return dom.$modelSelector.find('option').map(function readOption() {
      const value = String($(this).val() || '').trim();
      const label = String($(this).text() || value).trim();
      return label ? { value, label } : null;
    }).get().filter(Boolean);
  }

  // Report whether one row is a non-selectable placeholder option.
  function isPlaceholderModel(model) {
    return !model || !model.value || model.value === 'No models available' || model.value === 'Models load on demand';
  }

  // Read cached vision and tool capability flags for one model.
  function currentCapabilities(modelName) {
    const key = cacheKey(modelName);
    const cached = capabilityCache.get(key);
    if (cached) {
      return cached;
    }
    if (modelName && modelName === selectedModel() && state.currentModelInfo) {
      return {
        vision: !!state.currentModelInfo.supports_vision,
        tools: !!state.currentModelInfo.supports_tool_calling
      };
    }
    return null;
  }

  // Store capability flags with a bounded LRU-style eviction policy.
  function cacheCapabilities(key, value) {
    if (capabilityCache.has(key)) {
      capabilityCache.delete(key);
    }
    capabilityCache.set(key, value);
    while (capabilityCache.size > maxCapabilityCacheEntries) {
      const oldestKey = capabilityCache.keys().next().value;
      if (!oldestKey) {
        break;
      }
      capabilityCache.delete(oldestKey);
    }
  }

  // Cache capabilities for the model currently loaded in app state.
  function rememberCurrentModelCapabilities() {
    const modelName = selectedModel();
    if (!modelName || !state.currentModelInfo) {
      return;
    }
    cacheCapabilities(cacheKey(modelName), {
      vision: !!state.currentModelInfo.supports_vision,
      tools: !!state.currentModelInfo.supports_tool_calling
    });
  }

  // Sync the custom selector button label with the active model.
  function updateButtonLabel() {
    const selected = selectedModel();
    const match = allModels.find(function findModel(model) {
      return model.value === selected;
    });
    $value.text((match && match.label) || selected || 'Models load on demand');
  }

  // Filter the virtual list from the search box and reset highlight.
  function applyFilter() {
    const query = String($search.val() || '').trim().toLowerCase();
    filteredModels = !query
      ? allModels.slice()
      : allModels.filter(function filterModel(model) {
        return model.label.toLowerCase().includes(query) || model.value.toLowerCase().includes(query);
      });

    const selected = selectedModel();
    highlightedIndex = Math.max(filteredModels.findIndex(function findSelected(model) {
      return model.value === selected;
    }), 0);
  }


  // Capability prefetch.
  // Queue capability lookups for rows visible in the virtual list.
  function requestVisibleCapabilities() {
    window.clearTimeout(requestTimer);
    requestTimer = window.setTimeout(function requestLater() {
      if (!isOpen) {
        return;
      }
      if (allModels.length > eagerCapabilityLimit) {
        return;
      }

      const scrollTop = $list.scrollTop();
      const viewportHeight = $list.innerHeight() || 0;
      const start = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
      const count = Math.ceil(viewportHeight / rowHeight) + overscan * 2;
      filteredModels.slice(start, start + count).forEach(function requestModel(model) {
        if (!model || isPlaceholderModel(model)) {
          return;
        }
        const key = cacheKey(model.value);
        if (capabilityCache.has(key) || pendingCapabilityRequests.has(key)) {
          return;
        }

        queuedCapabilityRequests.set(key, model.value);
      });
      processCapabilityQueue();
    }, 80);
  }

  // Drain the queued model_info requests with a concurrency limit.
  function processCapabilityQueue() {
    if (activeCapabilityRequests >= maxConcurrentCapabilityRequests || queuedCapabilityRequests.size === 0) {
      return;
    }

    const next = queuedCapabilityRequests.entries().next().value;
    if (!next) {
      return;
    }

    const [key, modelName] = next;
    queuedCapabilityRequests.delete(key);

    if (capabilityCache.has(key) || pendingCapabilityRequests.has(key)) {
      processCapabilityQueue();
      return;
    }

    activeCapabilityRequests += 1;
    pendingCapabilityRequests.add(key);
    fetch(`/api/model_info/?engine=${encodeURIComponent(state.activeEngine)}&model=${encodeURIComponent(modelName)}`)
      .then(function parseResponse(response) {
        if (!response.ok) {
          throw new Error(`model_info ${response.status}`);
        }
        return response.json();
      })
      .then(function cacheData(data) {
        cacheCapabilities(key, {
          vision: !!data.supports_vision,
          tools: !!data.supports_tool_calling
        });
        renderList();
      })
      .catch(function ignoreCapabilityError() {
        cacheCapabilities(key, { vision: false, tools: false, error: true });
      })
      .finally(function clearPending() {
        pendingCapabilityRequests.delete(key);
        activeCapabilityRequests = Math.max(0, activeCapabilityRequests - 1);
        processCapabilityQueue();
      });

    processCapabilityQueue();
  }


  // Popover rendering.
  // Build one virtualized model row HTML fragment.
  function optionHtml(model, index) {
    const selected = model.value === selectedModel();
    const highlighted = index === highlightedIndex;
    const capabilities = currentCapabilities(model.value);
    const vision = capabilities && capabilities.vision;
    const classes = [
      'custom-model-option',
      selected ? 'is-selected' : '',
      highlighted ? 'is-highlighted' : ''
    ].filter(Boolean).join(' ');

    return `
      <button type="button" class="${classes}" role="option" aria-selected="${selected ? 'true' : 'false'}" data-model-index="${index}" style="top:${index * rowHeight}px">
        <span class="custom-model-option-name">${escHtml(model.label)}</span>
        <span class="custom-model-option-meta" aria-hidden="true">
          ${vision ? `<span class="custom-model-meta-svg is-vision" title="Vision model"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><use href="${uiIconPaths.eye}#icon"></use></svg></span>` : ''}
        </span>
      </button>
    `;
  }

  // Render the visible slice of the virtualized model list.
  function renderList() {
    if (!isOpen) {
      return;
    }

    if (!filteredModels.length) {
      $list.css('height', '').html('<div class="custom-model-empty">No models found</div>');
      return;
    }

    const scrollTop = $list.scrollTop();
    const viewportHeight = $list.innerHeight() || 260;
    const totalHeight = filteredModels.length * rowHeight;
    const start = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
    const visibleCount = Math.ceil(viewportHeight / rowHeight) + overscan * 2;
    const end = Math.min(filteredModels.length, start + visibleCount);
    const html = `
      <div class="custom-model-virtual-canvas" style="height:${totalHeight}px">
        ${filteredModels.slice(start, end).map(function renderOption(model, offset) {
        return optionHtml(model, start + offset);
      }).join('')}
      </div>
    `;

    $list.html(html);
    requestVisibleCapabilities();
  }

  // Refresh list data from the hidden native select options.
  function syncFromNative() {
    rememberCurrentModelCapabilities();
    allModels = modelsFromNativeSelect();
    applyFilter();
    updateButtonLabel();
    renderList();
  }

  // Select one model by its index in the filtered list.
  function chooseModelByIndex(index) {
    const model = filteredModels[index];
    if (!model || isPlaceholderModel(model)) {
      return;
    }

    dom.$modelSelector.val(model.value).trigger('change');
    close();
  }

  // Keep the keyboard-highlighted row inside the scroll viewport.
  function scrollHighlightedIntoView() {
    if (highlightedIndex < 0) {
      return;
    }
    const top = highlightedIndex * rowHeight;
    const bottom = top + rowHeight;
    const currentTop = $list.scrollTop();
    const currentBottom = currentTop + ($list.innerHeight() || 0);
    if (top < currentTop) {
      $list.scrollTop(top);
    } else if (bottom > currentBottom) {
      $list.scrollTop(bottom - ($list.innerHeight() || rowHeight));
    }
  }

  // Position the popover below or above the trigger based on viewport space.
  function positionPopover() {
    if (!isOpen) {
      return;
    }
    const rect = $button.get(0).getBoundingClientRect();
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 720;
    const preferredMaxHeight = Math.min(320, Math.max(180, viewportHeight - 24));
    const spaceBelow = viewportHeight - rect.bottom - 8;
    const spaceAbove = rect.top - 8;
    const openAbove = spaceBelow < 220 && spaceAbove > spaceBelow;
    const maxHeight = Math.max(160, Math.min(preferredMaxHeight, openAbove ? spaceAbove : spaceBelow));

    $popover.css({
      left: `${Math.round(rect.left)}px`,
      top: openAbove ? 'auto' : `${Math.round(rect.bottom + 4)}px`,
      bottom: openAbove ? `${Math.round(viewportHeight - rect.top + 4)}px` : 'auto',
      width: `${Math.round(rect.width)}px`
    });
    $list.css('max-height', `${Math.max(112, maxHeight - 52)}px`);
  }

  // Open the custom model selector popover.
  function open() {
    if (isOpen) {
      return;
    }
    isOpen = true;
    syncFromNative();
    $button.attr('aria-expanded', 'true').addClass('is-open');
    $popover.show();
    positionPopover();
    $search.val('');
    applyFilter();
    renderList();
    requestAnimationFrame(function focusSearch() {
      positionPopover();
      $search.trigger('focus');
      scrollHighlightedIntoView();
      renderList();
    });
  }

  // Close the custom model selector popover.
  function close() {
    if (!isOpen) {
      return;
    }
    isOpen = false;
    $button.attr('aria-expanded', 'false').removeClass('is-open');
    $popover.hide();
  }

  // Toggle the custom model selector open state.
  function toggle() {
    if (isOpen) {
      close();
    } else {
      open();
    }
  }


  // Event wiring.
  // Bind popover, keyboard, and native select synchronization events.
  function bindEvents() {
    $button.on('click', function onButtonClick(event) {
      event.preventDefault();
      event.stopPropagation();
      toggle();
    });

    $search.on('input', function onSearchInput() {
      applyFilter();
      $list.scrollTop(0);
      renderList();
    });

    $list.on('scroll', renderList);

    $(window).on('resize.customModelSelector scroll.customModelSelector', positionPopover);
    dom.$sidebarRight.on('scroll.customModelSelector', positionPopover);

    $list.on('click', '.custom-model-option', function onOptionClick() {
      chooseModelByIndex(Number($(this).attr('data-model-index')));
    });

    $popover.on('mousedown click', function onPopoverPointer(event) {
      event.stopPropagation();
    });

    $(document).on('click', function onDocumentClick(event) {
      if (!$(event.target).closest('.model-selector-wrap').length) {
        close();
      }
    });

    $(document).on('keydown', function onDocumentKeydown(event) {
      if (!isOpen) {
        return;
      }

      if (event.key === 'Escape') {
        event.preventDefault();
        close();
        $button.trigger('focus');
        return;
      }
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        highlightedIndex = Math.min(filteredModels.length - 1, highlightedIndex + 1);
        scrollHighlightedIntoView();
        renderList();
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        highlightedIndex = Math.max(0, highlightedIndex - 1);
        scrollHighlightedIntoView();
        renderList();
        return;
      }
      if (event.key === 'Enter') {
        event.preventDefault();
        chooseModelByIndex(highlightedIndex);
      }
    });

    dom.$modelSelector.on('change', function onNativeChange() {
      syncFromNative();
    });

    $(document).on('aslm:modelCapabilitiesChanged', function onCapabilitiesChanged() {
      rememberCurrentModelCapabilities();
      renderList();
    });

    if (typeof MutationObserver !== 'undefined') {
      const observer = new MutationObserver(syncFromNative);
      observer.observe(dom.$modelSelector.get(0), {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['selected']
      });
    }
  }

  // Mount the custom selector UI once per page load.
  function init() {
    if (!$wrap.length || $wrap.data('customModelSelectorReady')) {
      return;
    }
    $wrap.data('customModelSelectorReady', true);
    dom.$modelSelector.addClass('native-model-selector');
    dom.$modelSelector.after($button);
    $button.find('.custom-model-select-vision-slot').append(dom.$modelVisionIndicator);
    $('body').append($popover);
    bindEvents();
    syncFromNative();
  }

  init();

  return {
    close,
    open,
    syncFromNative
  };
}
