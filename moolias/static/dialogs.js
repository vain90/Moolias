(() => {
  const language = document.documentElement.lang?.toLowerCase().startsWith('de') ? 'de' : 'en';
  const text = {
    de: {
      confirm: 'Bestätigen',
      cancel: 'Abbrechen',
      close: 'Schließen',
      confirmTitle: 'Bitte bestätigen',
      errorTitle: 'Aktion fehlgeschlagen',
      statsTitle: 'Statistikmodus ändern?',
      statsBody: (from, to) =>
        `Du wechselst die Nutzungsstatistik von „${from}“ auf „${to}“. Daten, die der niedrigere Modus nicht speichern darf, werden dabei dauerhaft gelöscht. Dieser Schritt kann nicht rückgängig gemacht werden.`,
      statsConfirm: 'Modus ändern',
    },
    en: {
      confirm: 'Confirm',
      cancel: 'Cancel',
      close: 'Close',
      confirmTitle: 'Please confirm',
      errorTitle: 'Action failed',
      statsTitle: 'Change statistics mode?',
      statsBody: (from, to) =>
        `You are changing usage statistics from “${from}” to “${to}”. Data that the lower mode is not allowed to retain will be permanently deleted. This cannot be undone.`,
      statsConfirm: 'Change mode',
    },
  }[language];

  const statsLabels = {
    de: { off: 'Aus', basic: 'Standard', domain: 'Domains', full: 'Vollständig' },
    en: { off: 'Off', basic: 'Standard', domain: 'Domains', full: 'Full' },
  }[language];
  const statsRanks = { off: 0, basic: 1, domain: 2, full: 3 };

  let nativeConfirmBypass = 0;

  function isBackdropClick(dialog, event) {
    if (!(dialog instanceof HTMLDialogElement) || event.target !== dialog) return false;
    const rect = dialog.getBoundingClientRect();
    return event.clientX < rect.left
      || event.clientX > rect.right
      || event.clientY < rect.top
      || event.clientY > rect.bottom;
  }

  function bindBackdropDismiss(dialog, dismiss) {
    dialog.addEventListener('click', (event) => {
      if (isBackdropClick(dialog, event)) dismiss(event);
    });
  }

  // Native <dialog> uses the dialog element itself as the click target for both
  // ::backdrop and visible padding/background. Protect existing dialog consumers
  // from treating an inside-surface click as a backdrop click.
  document.addEventListener('click', (event) => {
    const dialog = event.target;
    if (!(dialog instanceof HTMLDialogElement) || !dialog.matches(':modal')) return;
    if (!isBackdropClick(dialog, event)) event.stopPropagation();
  }, true);

  function dialogHeading(title, closeLabel) {
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

  function show({
    title,
    message,
    confirmLabel = text.confirm,
    cancelLabel = text.cancel,
    tone = 'default',
    showCancel = false,
    dismissOnBackdrop = true,
  }) {
    return new Promise((resolve) => {
      const dialog = document.createElement('dialog');
      dialog.className = `moolias-dialog moolias-dialog-${tone}`;
      dialog.dataset.mooliasDialog = showCancel ? 'confirm' : 'message';

      const { head, close } = dialogHeading(title, text.close);
      const body = document.createElement('p');
      body.className = 'moolias-dialog-message';
      body.textContent = message;

      const actions = document.createElement('div');
      actions.className = 'button-row moolias-dialog-actions';

      const confirm = document.createElement('button');
      confirm.className = `button ${tone === 'danger' ? 'danger' : 'primary'}`;
      confirm.type = 'button';
      confirm.dataset.mooliasDialogConfirm = '1';
      confirm.textContent = confirmLabel;
      actions.append(confirm);

      let cancel = null;
      if (showCancel) {
        cancel = document.createElement('button');
        cancel.className = 'button';
        cancel.type = 'button';
        cancel.dataset.mooliasDialogCancel = '1';
        cancel.textContent = cancelLabel;
        actions.append(cancel);
      }

      dialog.append(head, body, actions);
      document.body.append(dialog);

      let settled = false;
      const finish = (result) => {
        if (settled) return;
        settled = true;
        dialog.close();
        resolve(result);
      };

      confirm.addEventListener('click', () => finish(true));
      cancel?.addEventListener('click', () => finish(false));
      close.addEventListener('click', () => finish(false));
      dialog.addEventListener('cancel', (event) => {
        event.preventDefault();
        finish(false);
      });
      if (dismissOnBackdrop) bindBackdropDismiss(dialog, () => finish(false));
      dialog.addEventListener('close', () => dialog.remove(), { once: true });

      dialog.showModal();
      if (showCancel) cancel?.focus();
      else confirm.focus();
    });
  }

  const api = {
    confirm(options) {
      return show({
        title: options.title || text.confirmTitle,
        message: options.message,
        confirmLabel: options.confirmLabel || text.confirm,
        cancelLabel: options.cancelLabel || text.cancel,
        tone: options.tone || 'default',
        showCancel: true,
        dismissOnBackdrop: options.dismissOnBackdrop ?? true,
      });
    },
    info(options) {
      return show({
        title: options.title,
        message: options.message,
        confirmLabel: options.closeLabel || text.close,
        tone: options.tone || 'default',
      });
    },
    error(message, options = {}) {
      return show({
        title: options.title || text.errorTitle,
        message,
        confirmLabel: options.closeLabel || text.close,
        tone: 'danger',
      });
    },
    bindBackdropDismiss,
    isBackdropClick,
  };

  window.MooliasDialog = api;

  // Existing call sites are bridged while they are migrated to the asynchronous API.
  // Native browser dialogs are never shown.
  window.alert = (message) => {
    void api.error(String(message));
  };
  window.confirm = (message) => {
    if (nativeConfirmBypass > 0) {
      nativeConfirmBypass -= 1;
      return true;
    }
    console.warn('Blocked synchronous browser confirmation:', message);
    void api.info({ title: text.confirmTitle, message: String(message), tone: 'warning' });
    return false;
  };

  document.addEventListener('submit', async (event) => {
    const form = event.target.closest?.('form[data-confirm]');
    if (!form) return;
    if (form.dataset.mooliasConfirmed === '1') {
      delete form.dataset.mooliasConfirmed;
      return;
    }

    event.preventDefault();
    event.stopImmediatePropagation();
    const submitter = event.submitter;
    const accepted = await api.confirm({
      title: text.confirmTitle,
      message: form.dataset.confirm || '',
      tone: 'danger',
    });
    if (!accepted) return;

    form.dataset.mooliasConfirmed = '1';
    nativeConfirmBypass += 1;
    form.requestSubmit(submitter || undefined);
  }, true);

  document.addEventListener('submit', async (event) => {
    const form = event.target.closest?.('.usage-mode-form');
    if (!form) return;
    if (form.querySelector('input[name="confirm_downgrade"]')) return;

    const select = form.querySelector('select[name="mode"]');
    const current = document.body.dataset.statsEffective || 'off';
    const domainDefault = document.body.dataset.statsDomain || 'off';
    const selection = select?.value || 'inherit';
    const target = selection === 'inherit' ? domainDefault : selection;
    if (!(current in statsRanks) || !(target in statsRanks) || statsRanks[target] >= statsRanks[current]) {
      return;
    }

    event.preventDefault();
    event.stopImmediatePropagation();
    const submitter = event.submitter;
    const accepted = await api.confirm({
      title: text.statsTitle,
      message: text.statsBody(statsLabels[current], statsLabels[target]),
      confirmLabel: text.statsConfirm,
      tone: 'danger',
      dismissOnBackdrop: false,
    });
    if (!accepted) return;

    const confirmed = document.createElement('input');
    confirmed.type = 'hidden';
    confirmed.name = 'confirm_downgrade';
    confirmed.value = '1';
    form.append(confirmed);
    nativeConfirmBypass += 1;
    form.requestSubmit(submitter || undefined);
  }, true);
})();
