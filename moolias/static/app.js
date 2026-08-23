const modeOptions = [...document.querySelectorAll('[data-mode-option]')];
const customLocalPart = document.querySelector('[data-custom-local-part]');
const copiedLabel = document.body.dataset.copiedLabel || 'Copied';
const uiLanguage = document.documentElement.lang?.toLowerCase().startsWith('de') ? 'de' : 'en';
const replacementText = {
  de: {
    action: 'Alias ersetzen',
    hint: 'Erstellt einen neuen Alias mit gleichem Zweck und deaktiviert diesen Alias.',
    title: 'Alias ersetzen',
    body: 'Wähle, in welchem Format der neue Alias erstellt werden soll. Zweck und SOGo-Einstellung werden übernommen. Der bisherige Alias wird deaktiviert, aber nicht gelöscht.',
    style: 'Format des neuen Alias',
    named: 'Name + Zufall',
    namedHint: 'Zweck als Name plus zwei leicht lesbare Zufallszeichen.',
    readable: 'Lesbarer Zufall',
    readableHint: 'Zwei kurze Wörter plus zweistellige Zahl.',
    custom: 'Eigene Adresse',
    customHint: 'Lokalen Teil der neuen Adresse selbst festlegen.',
    customAddress: 'Eigene Adresse',
    customPlaceholder: 'mein-alias',
    confirm: 'Ersetzen',
    cancel: 'Abbrechen',
    successTitle: 'Alias ersetzt',
    successBody: 'Der neue Alias ist aktiv. Der bisherige Alias wurde deaktiviert und bleibt gespeichert.',
    partialTitle: 'Alias teilweise ersetzt',
    partialBody: 'Der neue Alias wurde erstellt, aber der bisherige Alias konnte nicht deaktiviert werden. Bitte prüfe beide Aliase.',
    failed: 'Der Alias konnte nicht ersetzt werden.',
    newAlias: 'Neuer Alias',
    copy: 'Kopieren',
    close: 'Schließen',
    bulkAction: 'Aktion auswählen',
    apply: 'Ausführen',
  },
  en: {
    action: 'Replace alias',
    hint: 'Creates a new alias with the same purpose and disables this alias.',
    title: 'Replace alias',
    body: 'Choose the format for the new alias. Purpose and SOGo visibility are preserved. The current alias is disabled but not deleted.',
    style: 'New alias format',
    named: 'Name + random',
    namedHint: 'Purpose as the name plus two easy-to-read random characters.',
    readable: 'Readable random',
    readableHint: 'Two short words plus a two-digit number.',
    custom: 'Custom address',
    customHint: 'Choose the local part of the new address yourself.',
    customAddress: 'Custom address',
    customPlaceholder: 'my-alias',
    confirm: 'Replace',
    cancel: 'Cancel',
    successTitle: 'Alias replaced',
    successBody: 'The new alias is active. The previous alias was disabled and remains stored.',
    partialTitle: 'Alias partially replaced',
    partialBody: 'The new alias was created, but the previous alias could not be disabled. Please check both aliases.',
    failed: 'The alias could not be replaced.',
    newAlias: 'New alias',
    copy: 'Copy',
    close: 'Close',
    bulkAction: 'Choose action',
    apply: 'Apply',
  },
}[uiLanguage];

function syncAliasMode() {
  if (!customLocalPart) return;
  const selected = modeOptions.find((option) => option.checked)?.value;
  customLocalPart.classList.toggle('hidden', selected !== 'custom');
}

modeOptions.forEach((option) => option.addEventListener('change', syncAliasMode));
syncAliasMode();

function bindCopyButtons(root = document) {
  root.querySelectorAll('[data-copy]').forEach((button) => {
    if (button.dataset.bound === 'true') return;
    button.dataset.bound = 'true';
    button.addEventListener('click', async () => {
      await navigator.clipboard.writeText(button.dataset.copy);
      const original = button.textContent;
      button.textContent = copiedLabel;
      setTimeout(() => { button.textContent = original; }, 1200);
    });
  });
}

function bindConfirmForms(root = document) {
  root.querySelectorAll('[data-confirm]').forEach((form) => {
    if (form.dataset.bound === 'true') return;
    form.dataset.bound = 'true';
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });
}

function bindPageSize(root = document) {
  root.querySelectorAll('[data-page-size]').forEach((select) => {
    if (select.dataset.bound === 'true') return;
    select.dataset.bound = 'true';
    select.addEventListener('change', (event) => {
      event.currentTarget.form?.submit();
    });
  });
}

function bindAssignDialogs(root = document) {
  root.querySelectorAll('[data-open-assign-dialog]').forEach((button) => {
    if (button.dataset.bound === 'true') return;
    button.dataset.bound = 'true';
    button.addEventListener('click', () => {
      const dialogId = button.dataset.openAssignDialog;
      const dialog = document.querySelector(`[data-assign-dialog="${dialogId}"]`);
      dialog?.showModal();
      dialog?.querySelector('input[name="description"]')?.focus();
    });
  });

  root.querySelectorAll('[data-assign-dialog]').forEach((dialog) => {
    if (dialog.dataset.bound === 'true') return;
    dialog.dataset.bound = 'true';
    dialog.querySelector('[data-close-dialog]')?.addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', (event) => {
      if (event.target === dialog) {
        dialog.close();
      }
    });
  });
}

function createDialogHeading(title, closeLabel) {
  const head = document.createElement('div');
  head.className = 'dialog-head';

  const heading = document.createElement('h2');
  heading.textContent = title;

  const close = document.createElement('button');
  close.className = 'dialog-close';
  close.type = 'button';
  close.textContent = '×';
  close.setAttribute('aria-label', closeLabel);
  close.title = closeLabel;

  head.append(heading, close);
  return { head, close };
}

function replacementModeOption(name, value, title, example, hint, checked = false) {
  const label = document.createElement('label');
  label.className = 'mode-option';

  const radio = document.createElement('input');
  radio.type = 'radio';
  radio.name = name;
  radio.value = value;
  radio.checked = checked;

  const body = document.createElement('span');
  body.className = 'mode-option-body';

  const head = document.createElement('span');
  head.className = 'mode-option-head';
  const strong = document.createElement('strong');
  strong.textContent = title;
  head.append(strong);

  const code = document.createElement('code');
  code.textContent = example;

  const small = document.createElement('small');
  small.textContent = hint;

  body.append(head, code, small);
  label.append(radio, body);
  return { label, radio };
}

function showReplacementResult(address, partial = false) {
  const dialog = document.createElement('dialog');
  dialog.className = 'assign-dialog assign-dialog-single';
  const { head, close } = createDialogHeading(
    partial ? replacementText.partialTitle : replacementText.successTitle,
    replacementText.close,
  );

  const body = document.createElement('p');
  body.className = 'muted';
  body.textContent = partial ? replacementText.partialBody : replacementText.successBody;

  const label = document.createElement('p');
  label.className = 'hint';
  label.textContent = replacementText.newAlias;

  const addressCode = document.createElement('code');
  addressCode.className = 'assign-address';
  addressCode.textContent = address;

  const actions = document.createElement('div');
  actions.className = 'button-row top-gap';

  const copy = document.createElement('button');
  copy.className = 'button primary';
  copy.type = 'button';
  copy.dataset.copy = address;
  copy.textContent = replacementText.copy;

  const done = document.createElement('button');
  done.className = 'button';
  done.type = 'button';
  done.textContent = replacementText.close;

  actions.append(copy, done);
  dialog.append(head, body, label, addressCode, actions);
  document.body.append(dialog);
  bindCopyButtons(dialog);

  close.addEventListener('click', () => dialog.close());
  done.addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener('close', () => {
    dialog.remove();
    window.location.reload();
  }, { once: true });
  dialog.showModal();
}

function showReplacementDialog(aliasCheckbox, editDetails) {
  const csrfToken = document.querySelector('input[name="csrf_token"]')?.value;
  if (!csrfToken) {
    window.alert(replacementText.failed);
    return;
  }

  const oldAddress = aliasCheckbox.dataset.address;
  const domain = oldAddress.split('@').slice(1).join('@');
  const description = aliasCheckbox.dataset.description || 'alias';

  const dialog = document.createElement('dialog');
  dialog.className = 'assign-dialog';
  const { head, close } = createDialogHeading(replacementText.title, replacementText.close);

  const body = document.createElement('p');
  body.className = 'muted';
  body.textContent = replacementText.body;

  const oldAddressCode = document.createElement('code');
  oldAddressCode.className = 'assign-address';
  oldAddressCode.textContent = oldAddress;

  const fieldset = document.createElement('fieldset');
  fieldset.className = 'mode-picker top-gap';
  const legend = document.createElement('legend');
  legend.textContent = replacementText.style;
  fieldset.append(legend);

  const slugPreview = description
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '') || 'alias';
  const named = replacementModeOption(
    'replacement-mode',
    'named',
    replacementText.named,
    `${slugPreview}-k7@${domain}`,
    replacementText.namedHint,
    true,
  );
  const readable = replacementModeOption(
    'replacement-mode',
    'readable',
    replacementText.readable,
    `feder-hafen-27@${domain}`,
    replacementText.readableHint,
  );
  const custom = replacementModeOption(
    'replacement-mode',
    'custom',
    replacementText.custom,
    `${replacementText.customPlaceholder}@${domain}`,
    replacementText.customHint,
  );
  fieldset.append(named.label, readable.label, custom.label);

  const customLabel = document.createElement('label');
  customLabel.className = 'hidden top-gap';
  customLabel.textContent = replacementText.customAddress;

  const addressInput = document.createElement('div');
  addressInput.className = 'address-input';
  const localPart = document.createElement('input');
  localPart.maxLength = 63;
  localPart.placeholder = replacementText.customPlaceholder;
  localPart.autocomplete = 'off';
  const domainSuffix = document.createElement('span');
  domainSuffix.textContent = `@${domain}`;
  addressInput.append(localPart, domainSuffix);
  customLabel.append(addressInput);

  const syncReplacementMode = () => {
    customLabel.classList.toggle('hidden', !custom.radio.checked);
    if (custom.radio.checked) {
      localPart.focus();
    }
  };
  [named.radio, readable.radio, custom.radio].forEach((radio) => {
    radio.addEventListener('change', syncReplacementMode);
  });

  const actions = document.createElement('div');
  actions.className = 'button-row top-gap';

  const confirm = document.createElement('button');
  confirm.className = 'button primary';
  confirm.type = 'button';
  confirm.textContent = replacementText.confirm;

  const cancel = document.createElement('button');
  cancel.className = 'button';
  cancel.type = 'button';
  cancel.textContent = replacementText.cancel;

  actions.append(confirm, cancel);
  dialog.append(head, body, oldAddressCode, fieldset, customLabel, actions);
  document.body.append(dialog);
  editDetails?.removeAttribute('open');

  close.addEventListener('click', () => dialog.close());
  cancel.addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener('close', () => dialog.remove(), { once: true });

  confirm.addEventListener('click', async () => {
    const mode = [named.radio, readable.radio, custom.radio].find((radio) => radio.checked)?.value;
    if (!mode) return;
    if (mode === 'custom' && !localPart.value.trim()) {
      localPart.focus();
      return;
    }

    const form = new FormData();
    form.append('csrf_token', csrfToken);
    form.append('mode', mode);
    form.append('local_part', localPart.value.trim());
    confirm.disabled = true;
    cancel.disabled = true;

    try {
      const response = await fetch(`/aliases/${aliasCheckbox.value}/replace`, {
        method: 'POST',
        body: form,
      });
      let payload = {};
      try {
        payload = await response.json();
      } catch (error) {
        console.debug('Replacement response did not contain JSON', error);
      }

      if (!response.ok) {
        const detail = payload.detail;
        if (detail?.code === 'partial_replacement' && detail.address) {
          dialog.close();
          showReplacementResult(detail.address, true);
          return;
        }
        throw new Error(`Alias replacement failed with HTTP ${response.status}`);
      }

      if (!payload.address) {
        throw new Error('Alias replacement response did not contain an address');
      }

      dialog.close();
      showReplacementResult(payload.address);
    } catch (error) {
      console.error('Alias replacement failed', error);
      window.alert(replacementText.failed);
      confirm.disabled = false;
      cancel.disabled = false;
    }
  });

  dialog.showModal();
}

function bindReplacementActions(root = document) {
  root.querySelectorAll('.alias-row').forEach((row) => {
    const aliasCheckbox = row.querySelector('[data-alias-select]');
    const editDetails = row.querySelector('details.alias-edit-action');
    const panel = editDetails?.querySelector('.edit-panel');
    if (!aliasCheckbox || !panel || panel.querySelector('[data-replace-alias]')) return;

    const hint = document.createElement('p');
    hint.className = 'hint top-gap';
    hint.textContent = replacementText.hint;

    const button = document.createElement('button');
    button.className = 'button compact';
    button.type = 'button';
    button.dataset.replaceAlias = aliasCheckbox.value;
    button.textContent = replacementText.action;
    button.addEventListener('click', () => showReplacementDialog(aliasCheckbox, editDetails));

    panel.append(hint, button);
  });
}

function bindBulkActions(root = document) {
  root.querySelectorAll('[data-bulk-toolbar]').forEach((toolbar) => {
    if (toolbar.dataset.bound === 'true') return;
    toolbar.dataset.bound = 'true';

    const region = toolbar.closest('[data-alias-results-region]') || root;
    const selection = toolbar.querySelector('.bulk-selection');
    const actions = toolbar.querySelector('.bulk-actions');
    const count = toolbar.querySelector('[data-selected-count]');
    const oldSelectAll = toolbar.querySelector('[data-select-all]');
    const oldActionButtons = [...toolbar.querySelectorAll('[data-bulk-action]')];
    const selectedTemplate = toolbar.dataset.selectedTemplate || '{count} selected';
    const failureMessage = toolbar.dataset.bulkFailed || 'The bulk action could not be completed.';

    if (!selection || !actions) return;

    const masterLabel = document.createElement('label');
    masterLabel.className = 'check-row compact-check';
    const master = document.createElement('input');
    master.type = 'checkbox';
    master.dataset.selectMaster = 'true';
    const masterText = document.createElement('span');
    masterText.textContent = oldSelectAll?.textContent?.trim() || 'Select all';
    masterLabel.append(master, masterText);

    selection.innerHTML = '';
    selection.append(masterLabel);
    if (count) selection.append(count);

    const actionSelect = document.createElement('select');
    actionSelect.dataset.bulkActionSelect = 'true';
    actionSelect.style.width = 'auto';
    actionSelect.style.minWidth = '180px';

    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = replacementText.bulkAction;
    actionSelect.append(placeholder);

    oldActionButtons.forEach((button) => {
      const option = document.createElement('option');
      option.value = button.dataset.bulkAction;
      option.textContent = button.textContent.trim();
      actionSelect.append(option);
    });

    const apply = document.createElement('button');
    apply.className = 'button compact';
    apply.type = 'button';
    apply.textContent = replacementText.apply;
    apply.disabled = true;

    actions.innerHTML = '';
    actions.append(actionSelect, apply);

    const checkboxes = () => [...region.querySelectorAll('[data-alias-select]')];
    const selected = () => checkboxes().filter((checkbox) => checkbox.checked);

    const sync = () => {
      const all = checkboxes();
      const selectedCount = selected().length;
      if (count) {
        count.textContent = selectedTemplate.replace('{count}', String(selectedCount));
      }
      master.checked = all.length > 0 && selectedCount === all.length;
      master.indeterminate = selectedCount > 0 && selectedCount < all.length;
      actionSelect.disabled = selectedCount === 0;
      apply.disabled = selectedCount === 0 || !actionSelect.value;
    };

    checkboxes().forEach((checkbox) => checkbox.addEventListener('change', sync));

    master.addEventListener('change', () => {
      checkboxes().forEach((checkbox) => { checkbox.checked = master.checked; });
      sync();
    });

    actionSelect.addEventListener('change', sync);

    apply.addEventListener('click', async () => {
      const selectedAliases = selected();
      const action = actionSelect.value;
      if (!selectedAliases.length || !action) return;

      if (action === 'copy') {
        await navigator.clipboard.writeText(
          selectedAliases.map((checkbox) => checkbox.dataset.address).join('\n'),
        );
        const original = apply.textContent;
        apply.textContent = copiedLabel;
        setTimeout(() => { apply.textContent = original; }, 1200);
        return;
      }

      const csrfToken = document.querySelector('input[name="csrf_token"]')?.value;
      if (!csrfToken) {
        window.alert(failureMessage);
        return;
      }

      const form = new FormData();
      form.append('csrf_token', csrfToken);
      form.append('action', action);
      selectedAliases.forEach((checkbox) => form.append('alias_ids', checkbox.value));

      actionSelect.disabled = true;
      apply.disabled = true;
      try {
        const response = await fetch('/aliases/bulk', {
          method: 'POST',
          body: form,
        });
        if (!response.ok) {
          throw new Error(`Bulk action failed with HTTP ${response.status}`);
        }
        window.location.reload();
      } catch (error) {
        console.error('Bulk alias action failed', error);
        window.alert(failureMessage);
        sync();
      }
    });

    sync();
  });
}

function bindDynamicControls(root = document) {
  bindCopyButtons(root);
  bindConfirmForms(root);
  bindPageSize(root);
  bindAssignDialogs(root);
  bindReplacementActions(root);
  bindBulkActions(root);
}

bindDynamicControls();

const helpDialog = document.querySelector('[data-help-dialog]');
document.querySelector('[data-open-help-dialog]')?.addEventListener('click', () => {
  helpDialog?.showModal();
});
helpDialog?.querySelector('[data-close-help-dialog]')?.addEventListener('click', () => {
  helpDialog.close();
});
helpDialog?.addEventListener('click', (event) => {
  if (event.target === helpDialog) {
    helpDialog.close();
  }
});

document.addEventListener('pointerdown', (event) => {
  document.querySelectorAll('details.alias-edit-action[open]').forEach((details) => {
    if (!details.contains(event.target)) {
      details.removeAttribute('open');
    }
  });
});

document.querySelector('[data-copy-pool]')?.addEventListener('click', async (event) => {
  const addresses = [...document.querySelectorAll('.offline-pool-row:not(.pool-item-used) [data-pool-address]')]
    .map((element) => element.textContent.trim())
    .join('\n');
  await navigator.clipboard.writeText(addresses);
  const button = event.currentTarget;
  const original = button.textContent;
  button.textContent = copiedLabel;
  setTimeout(() => { button.textContent = original; }, 1200);
});

const searchInput = document.querySelector('[data-live-search]');
const searchClear = document.querySelector('[data-search-clear]');
let searchTimer;
let searchController;

function syncSearchClear() {
  if (!searchClear || !searchInput) return;
  searchClear.hidden = searchInput.value.length === 0;
}

async function refreshAliasResults() {
  if (!searchInput) return;

  const rawQuery = searchInput.value.trim();
  const activeQuery = rawQuery.length >= 2 ? rawQuery : '';
  const url = new URL(window.location.href);
  url.searchParams.set('status', searchInput.dataset.status || 'all');
  url.searchParams.set('per_page', searchInput.dataset.perPage || '25');
  url.searchParams.set('page', '1');
  if (activeQuery) {
    url.searchParams.set('q', activeQuery);
  } else {
    url.searchParams.delete('q');
  }

  searchController?.abort();
  searchController = new AbortController();
  searchInput.classList.add('searching');

  try {
    const response = await fetch(url, {
      headers: { 'X-Moolias-Partial': 'alias-results' },
      signal: searchController.signal,
    });
    if (!response.ok) return;

    const html = await response.text();
    const parsed = new DOMParser().parseFromString(html, 'text/html');
    const nextRegion = parsed.querySelector('[data-alias-results-region]');
    const currentRegion = document.querySelector('[data-alias-results-region]');
    const nextSummary = parsed.querySelector('[data-assigned-summary]');
    const currentSummary = document.querySelector('[data-assigned-summary]');

    if (nextRegion && currentRegion) {
      currentRegion.innerHTML = nextRegion.innerHTML;
      bindDynamicControls(currentRegion);
    }
    if (nextSummary && currentSummary) {
      currentSummary.textContent = nextSummary.textContent.trim();
    }
    window.history.replaceState(null, '', `${url.pathname}${url.search}`);
  } catch (error) {
    if (error.name !== 'AbortError') {
      console.error('Alias search failed', error);
    }
  } finally {
    searchInput.classList.remove('searching');
  }
}

searchInput?.addEventListener('input', () => {
  syncSearchClear();
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(refreshAliasResults, 250);
});

searchClear?.addEventListener('click', () => {
  if (!searchInput) return;
  window.clearTimeout(searchTimer);
  searchInput.value = '';
  syncSearchClear();
  searchInput.focus();
  refreshAliasResults();
});

syncSearchClear();
