// Copyright NEXTGGTECH. Elastic License 2.0.

import { escHtml } from '../main/utils.js';

// Custom settings-sidebar selects.
// Mirror native <select> controls with the model-selector look (no search, no
// capability markers) so engine / preset / parameter dropdowns match the model
// control. The model selector itself is intentionally left alone.

const ENHANCED_ATTR = 'data-settings-select-ready';

// Create the settings-select manager for one app context.
export function createSettingsSelectUi(context) {
  const { dom } = context;
  /** @type {Map<HTMLElement, SettingsSelectInstance>} */
  const instances = new Map();
  let openInstance = null;
  let documentBound = false;

  // Report whether a native select should be upgraded.
  function isEligibleSelect(selectEl) {
    if (!selectEl || selectEl.tagName !== 'SELECT') {
      return false;
    }
    if (selectEl.id === 'modelSelector') {
      return false;
    }
    if (selectEl.classList.contains('native-model-selector')) {
      return false;
    }
    if (selectEl.closest('.model-selector-wrap')) {
      return false;
    }
    if (!selectEl.closest('.settings-panel')) {
      return false;
    }
    return selectEl.classList.contains('model-selector')
      || selectEl.classList.contains('setting-select');
  }

  // Close every open settings select popover.
  function closeAll() {
    instances.forEach(function closeOne(instance) {
      instance.close();
    });
    openInstance = null;
  }

  // Position a popover under (or above) its trigger within the viewport.
  function positionPopover($button, $popover, $list) {
    const buttonEl = $button.get(0);
    const popoverEl = $popover.get(0);
    if (!buttonEl || !popoverEl) {
      return;
    }
    const rect = buttonEl.getBoundingClientRect();
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 720;
    const preferredMaxHeight = Math.min(280, Math.max(140, viewportHeight - 24));
    const spaceBelow = viewportHeight - rect.bottom - 8;
    const spaceAbove = rect.top - 8;
    const openAbove = spaceBelow < 160 && spaceAbove > spaceBelow;
    const maxHeight = Math.max(120, Math.min(preferredMaxHeight, openAbove ? spaceAbove : spaceBelow));

    $popover.css({
      left: `${Math.round(rect.left)}px`,
      top: openAbove ? 'auto' : `${Math.round(rect.bottom + 4)}px`,
      bottom: openAbove ? `${Math.round(viewportHeight - rect.top + 4)}px` : 'auto',
      width: `${Math.round(rect.width)}px`
    });
    $list.css('max-height', `${Math.max(96, maxHeight - 12)}px`);
  }

  // Build one enhanced instance around a native select element.
  function enhanceSelect(selectEl) {
    if (!isEligibleSelect(selectEl) || selectEl.getAttribute(ENHANCED_ATTR) === '1') {
      return null;
    }

    const $select = $(selectEl);
    selectEl.setAttribute(ENHANCED_ATTR, '1');
    $select.addClass('native-settings-select');

    const isCompact = $select.hasClass('setting-control-compact');
    const $wrap = $('<div class="settings-select-wrap">');
    const $button = $(`
      <button type="button" class="settings-select-trigger${isCompact ? ' setting-control-compact' : ''}" aria-haspopup="listbox" aria-expanded="false">
        <span class="settings-select-value"></span>
        <span class="settings-select-chevron" aria-hidden="true"></span>
      </button>
    `);
    const $value = $button.find('.settings-select-value');
    const $popover = $(`
      <div class="settings-select-popover" style="display:none;" role="presentation">
        <div class="settings-select-list" role="listbox"></div>
      </div>
    `);
    const $list = $popover.find('.settings-select-list');

    $select.before($wrap);
    $wrap.append($select);
    $wrap.append($button);
    $('body').append($popover);

    let isOpen = false;
    let options = [];
    let highlightedIndex = -1;
    let optionObserver = null;

    // Read options and the current value from the native select.
    function readOptions() {
      options = $select.find('option').map(function mapOption() {
        const $opt = $(this);
        return {
          value: String($opt.val()),
          label: String($opt.text() || $opt.val() || '').trim(),
          disabled: !!$opt.prop('disabled'),
          hidden: !!$opt.prop('hidden')
        };
      }).get().filter(function keepVisible(option) {
        return !option.hidden;
      });
    }

    // Sync the trigger label and disabled state with the native select.
    function updateButton() {
      const selectedValue = String($select.val() ?? '');
      const match = options.find(function findOption(option) {
        return option.value === selectedValue;
      });
      const selectedOption = $select.find('option:selected').first();
      const label = (match && match.label)
        || String(selectedOption.text() || selectedValue || '').trim()
        || '—';
      $value.text(label);
      $button.prop('disabled', !!$select.prop('disabled'));

      if ($select.attr('id')) {
        $button.attr('id', `${$select.attr('id')}_trigger`);
      }
      if ($select.attr('aria-label')) {
        $button.attr('aria-label', $select.attr('aria-label'));
      }
    }

    // Render option buttons into the popover list.
    function renderList() {
      if (!options.length) {
        $list.html('<div class="settings-select-empty">No options</div>');
        return;
      }

      const selectedValue = String($select.val() ?? '');
      $list.html(options.map(function renderOption(option, index) {
        const selected = option.value === selectedValue;
        const highlighted = index === highlightedIndex;
        const classes = [
          'settings-select-option',
          selected ? 'is-selected' : '',
          highlighted ? 'is-highlighted' : ''
        ].filter(Boolean).join(' ');
        return `
          <button
            type="button"
            class="${classes}"
            role="option"
            aria-selected="${selected ? 'true' : 'false'}"
            data-option-index="${index}"
            ${option.disabled ? 'disabled' : ''}>
            <span class="settings-select-option-label">${escHtml(option.label)}</span>
          </button>
        `;
      }).join(''));
    }

    // Keep the keyboard highlight inside the scrollable list.
    function scrollHighlightedIntoView() {
      const item = $list.find(`[data-option-index="${highlightedIndex}"]`).get(0);
      if (item && typeof item.scrollIntoView === 'function') {
        item.scrollIntoView({ block: 'nearest' });
      }
    }

    // Refresh mirrored state from the native select.
    function syncFromNative() {
      readOptions();
      updateButton();
      if (isOpen) {
        const selectedValue = String($select.val() ?? '');
        highlightedIndex = Math.max(0, options.findIndex(function findSelected(option) {
          return option.value === selectedValue;
        }));
        renderList();
      }
    }

    // Choose one option and close the popover.
    function chooseByIndex(index) {
      const option = options[index];
      if (!option || option.disabled) {
        return;
      }
      const previous = String($select.val() ?? '');
      if (previous !== option.value) {
        $select.val(option.value).trigger('change');
      } else {
        updateButton();
      }
      close();
      $button.trigger('focus');
    }

    // Open this instance's popover (closing any sibling first).
    function open() {
      if (isOpen || $select.prop('disabled')) {
        return;
      }
      if (openInstance && openInstance !== instance) {
        openInstance.close();
      }
      isOpen = true;
      openInstance = instance;
      syncFromNative();
      const selectedValue = String($select.val() ?? '');
      highlightedIndex = Math.max(0, options.findIndex(function findSelected(option) {
        return option.value === selectedValue;
      }));
      $button.attr('aria-expanded', 'true').addClass('is-open');
      $popover.show();
      positionPopover($button, $popover, $list);
      renderList();
      requestAnimationFrame(function afterOpen() {
        positionPopover($button, $popover, $list);
        scrollHighlightedIntoView();
      });
    }

    // Close this instance's popover.
    function close() {
      if (!isOpen) {
        return;
      }
      isOpen = false;
      if (openInstance === instance) {
        openInstance = null;
      }
      $button.attr('aria-expanded', 'false').removeClass('is-open');
      $popover.hide();
    }

    // Reposition the open popover (viewport / sidebar scroll).
    function reposition() {
      if (!isOpen) {
        return;
      }
      positionPopover($button, $popover, $list);
    }

    // Toggle open / closed.
    function toggle() {
      if (isOpen) {
        close();
      } else {
        open();
      }
    }

    // Handle keyboard navigation while open (or on the trigger).
    function onKeydown(event) {
      if (!isOpen) {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          open();
        }
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
        highlightedIndex = Math.min(options.length - 1, highlightedIndex + 1);
        renderList();
        scrollHighlightedIntoView();
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        highlightedIndex = Math.max(0, highlightedIndex - 1);
        renderList();
        scrollHighlightedIntoView();
        return;
      }
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        chooseByIndex(highlightedIndex);
        return;
      }
      if (event.key === 'Home') {
        event.preventDefault();
        highlightedIndex = 0;
        renderList();
        scrollHighlightedIntoView();
        return;
      }
      if (event.key === 'End') {
        event.preventDefault();
        highlightedIndex = Math.max(0, options.length - 1);
        renderList();
        scrollHighlightedIntoView();
      }
    }

    $button.on('click', function onTriggerClick(event) {
      event.preventDefault();
      // Let the event reach the document so the model selector can close itself
      // (it listens for outside clicks). Do not stopPropagation.
      toggle();
    });

    $button.on('keydown', onKeydown);

    $list.on('click', '.settings-select-option', function onOptionClick(event) {
      event.preventDefault();
      event.stopPropagation();
      chooseByIndex(Number($(this).attr('data-option-index')));
    });

    $list.on('mousemove', '.settings-select-option', function onOptionHover() {
      const index = Number($(this).attr('data-option-index'));
      if (!Number.isFinite(index) || index === highlightedIndex) {
        return;
      }
      highlightedIndex = index;
      $list.find('.settings-select-option').each(function syncHighlight() {
        const $opt = $(this);
        $opt.toggleClass('is-highlighted', Number($opt.attr('data-option-index')) === highlightedIndex);
      });
    });

    $popover.on('mousedown click', function stopPopoverBubble(event) {
      event.stopPropagation();
    });

    $select.on('change.settingsSelect', function onNativeChange() {
      syncFromNative();
    });

    // Labels with for=selectId still focus the hidden select; forward to trigger.
    $select.on('focus.settingsSelect', function onNativeFocus() {
      $button.trigger('focus');
    });

    if (typeof MutationObserver !== 'undefined') {
      optionObserver = new MutationObserver(function onSelectMutated() {
        // Select may have been removed from the DOM during re-render.
        if (!document.body.contains(selectEl)) {
          destroy();
          return;
        }
        syncFromNative();
      });
      optionObserver.observe(selectEl, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['disabled', 'selected', 'value']
      });
    }

    // Tear down DOM + observers when the native select is gone.
    function destroy() {
      close();
      if (optionObserver) {
        optionObserver.disconnect();
        optionObserver = null;
      }
      $select.off('.settingsSelect');
      $button.off();
      $list.off();
      $popover.remove();
      // If the wrap is still in the document and still owns the select, unwrap.
      // During parameter re-renders the whole group is often removed already.
      if ($wrap.parent().length && $select.parent().is($wrap)) {
        $wrap.before($select);
        $wrap.remove();
      } else if ($button.parent().length && !$button.parent().is($wrap)) {
        $button.remove();
      } else if ($wrap.parent().length && !document.body.contains(selectEl)) {
        $wrap.remove();
      }
      $select.removeClass('native-settings-select');
      selectEl.removeAttribute(ENHANCED_ATTR);
      instances.delete(selectEl);
    }

    const instance = {
      close,
      open,
      reposition,
      syncFromNative,
      destroy,
      isOpen: function getIsOpen() {
        return isOpen;
      },
      containsEventTarget: function containsEventTarget(target) {
        return !!(target && (
          $wrap.get(0).contains(target)
          || $popover.get(0).contains(target)
        ));
      }
    };

    instances.set(selectEl, instance);
    syncFromNative();
    return instance;
  }

  // Upgrade every eligible select currently in the settings panel.
  function scan() {
    // Drop instances whose select left the document.
    Array.from(instances.entries()).forEach(function prune(entry) {
      const selectEl = entry[0];
      const instance = entry[1];
      if (!document.body.contains(selectEl)) {
        instance.destroy();
      }
    });

    const root = document.querySelector('.settings-panel');
    if (!root) {
      return;
    }

    root.querySelectorAll('select.model-selector, select.setting-select').forEach(function maybeEnhance(selectEl) {
      if (isEligibleSelect(selectEl) && selectEl.getAttribute(ENHANCED_ATTR) !== '1') {
        enhanceSelect(selectEl);
      }
    });
  }

  // Wire global dismiss / reposition handlers once.
  function bindDocumentHandlers() {
    if (documentBound) {
      return;
    }
    documentBound = true;

    // Capture phase so we still close when the model selector (or other menus)
    // stopPropagation on their own trigger clicks.
    document.addEventListener('click', function onDocumentClickCapture(event) {
      if (!openInstance) {
        return;
      }
      if (openInstance.containsEventTarget(event.target)) {
        return;
      }
      closeAll();
    }, true);

    $(document).on('keydown.settingsSelectUi', function onDocumentKeydown(event) {
      if (event.key === 'Escape' && openInstance) {
        closeAll();
      }
    });

    $(window).on('resize.settingsSelectUi', function onResize() {
      if (openInstance) {
        openInstance.reposition();
      }
    });

    let $scrollRoots = $();
    if (dom.$sidebarRight && dom.$sidebarRight.length) {
      $scrollRoots = $scrollRoots.add(dom.$sidebarRight);
    }
    const settingsPanel = document.querySelector('.settings-panel');
    if (settingsPanel) {
      $scrollRoots = $scrollRoots.add(settingsPanel);
    }
    if ($scrollRoots.length) {
      $scrollRoots.on('scroll.settingsSelectUi', closeAll);
    }
  }

  // Observe the settings panel for dynamically rendered parameter selects.
  function observePanel() {
    const root = document.querySelector('.settings-panel');
    if (!root || typeof MutationObserver === 'undefined') {
      return;
    }

    let scanTimer = null;
    const panelObserver = new MutationObserver(function onPanelMutated() {
      // Debounce: parameter re-renders swap many nodes at once.
      window.clearTimeout(scanTimer);
      scanTimer = window.setTimeout(scan, 0);
    });
    panelObserver.observe(root, {
      childList: true,
      subtree: true
    });
  }

  // Mount the manager once.
  function init() {
    bindDocumentHandlers();
    observePanel();
    scan();
  }

  init();

  return {
    scan,
    closeAll,
    enhanceSelect
  };
}
