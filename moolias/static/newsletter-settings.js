(() => {
  const setting = document.querySelector('[data-newsletter-setting]');
  const nav = document.querySelector('[data-newsletter-nav]');
  const oldDialog = document.querySelector('[data-newsletter-opt-in-dialog]');
  oldDialog?.remove();
  if (!setting && !nav) return;

  const language = document.documentElement.lang === 'de' ? 'de' : 'en';
  if (nav) {
    const iconUse = nav.querySelector('.nav-icon use');
    const label = nav.querySelector('.nav-icon + span');
    iconUse?.setAttribute('href', '/static/ui-icons.svg#icon-newspaper');
    if (label) {
      label.textContent = language === 'de'
        ? 'Newsletter-Verwaltung'
        : 'Newsletter Management';
    }
  }

  const form = setting?.querySelector('form[action="/account/newsletter-management"]');
  const oldToggle = setting?.querySelector('[data-newsletter-toggle]');
  const oldSwitch = oldToggle?.closest('.switch-control');
  let select = setting?.querySelector('[data-newsletter-mode-select]');
  let policyData = null;

  if (!select && form) {
    select = document.createElement('select');
    select.name = 'mode';
    select.dataset.newsletterModeSelect = '';
    select.setAttribute(
      'aria-label',
      language === 'de' ? 'Newsletter-Einstellung' : 'Newsletter setting',
    );
    const choices = language === 'de'
      ? [
          ['inherit', 'Domain-Einstellung verwenden'],
          ['off', 'Aus'],
          ['on', 'An'],
        ]
      : [
          ['inherit', 'Use domain setting'],
          ['off', 'Off'],
          ['on', 'On'],
        ];
    for (const [value, label] of choices) {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = label;
      select.append(option);
    }
    if (oldSwitch) oldSwitch.replaceWith(select);
    else form.prepend(select);
  }

  const save = setting?.querySelector('[data-newsletter-save]');
  const state = setting?.querySelector('[data-newsletter-setting-state]');
  const description = setting?.querySelector('.settings-section-body > .muted');
  const hint = setting?.querySelector('.settings-section-body > .hint');

  // Keep the normal settings view concise. Policy details belong in the documentation;
  // the user only needs the selection and the resulting effective state here.
  description?.remove();
  hint?.remove();

  const labels = {
    de: {
      serverOff: 'Serverseitig deaktiviert.',
      inheritedOn: 'Über die Domain-Einstellung aktiviert.',
      inheritedOff: 'Über die Domain-Einstellung deaktiviert.',
      mailboxOn: 'Für dieses Postfach aktiviert.',
      mailboxOff: 'Für dieses Postfach deaktiviert.',
      conflictMailbox: 'Widersprüchliche Newsletter-Tags am Postfach. Die Funktion bleibt aus, bis der Konflikt behoben ist.',
      conflictDomain: 'Widersprüchliche Newsletter-Tags an der Domain. Die Funktion bleibt aus, bis der Konflikt behoben ist.',
      unavailable: 'Die Newsletter-Einstellung konnte nicht geladen werden.',
      historyTitle: 'Vorhandene Newsletter-Historie einbeziehen?',
      historyBody: 'Möchtest du die noch verfügbare Historie nach bereits erkannten Newslettern durchsuchen?',
      historyInclude: 'Historie einbeziehen',
      historyNow: 'Nur ab jetzt erkennen',
      cancel: 'Abbrechen',
      close: 'Schließen',
      processingTitle: 'Newsletter-Verwaltung wird aktiviert',
      processingHistory: 'Die verfügbare Historie wird für den Import freigegeben. Die Einträge werden anschließend schrittweise verarbeitet.',
      processingNow: 'Die Einstellung wird gespeichert. Frühere Nachrichten werden nicht rückwirkend importiert.',
    },
    en: {
      serverOff: 'Disabled server-side.',
      inheritedOn: 'Enabled by the domain setting.',
      inheritedOff: 'Disabled by the domain setting.',
      mailboxOn: 'Enabled for this mailbox.',
      mailboxOff: 'Disabled for this mailbox.',
      conflictMailbox: 'Conflicting newsletter tags on the mailbox. The feature stays off until the conflict is fixed.',
      conflictDomain: 'Conflicting newsletter tags on the domain. The feature stays off until the conflict is fixed.',
      unavailable: 'The newsletter setting could not be loaded.',
      historyTitle: 'Include available newsletter history?',
      historyBody: 'Would you like Moolias to search the still-available history for previously detected newsletters?',
      historyInclude: 'Include history',
      historyNow: 'Detect from now on only',
      cancel: 'Cancel',
      close: 'Close',
      processingTitle: 'Enabling newsletter management',
      processingHistory: 'Available history is being enabled for import. Entries will then be processed incrementally.',
      processingNow: 'The setting is being saved. Earlier messages will not be imported retrospectively.',
    },
  }[language];

  const setControlsDisabled = (disabled) => {
    if (select) select.disabled = disabled;
    if (save) save.disabled = disabled;
    setting?.classList.toggle('is-disabled', disabled);
  };

  const historyChoiceDialog = () => new Promise((resolve) => {
    const dialog = document.createElement('dialog');
    dialog.className = 'moolias-dialog moolias-dialog-default newsletter-history-choice-dialog';

    const head = document.createElement('div');
    head.className = 'dialog-head';
    const title = document.createElement('h2');
    title.textContent = labels.historyTitle;
    const close = document.createElement('button');
    close.className = 'dialog-close';
    close.type = 'button';
    close.textContent = '×';
    close.setAttribute('aria-label', labels.close);
    close.title = labels.close;
    head.append(title, close);

    const body = document.createElement('p');
    body.className = 'moolias-dialog-message';
    body.textContent = labels.historyBody;

    const actions = document.createElement('div');
    actions.className = 'button-row moolias-dialog-actions newsletter-history-choice-actions';
    const include = document.createElement('button');
    include.className = 'button primary';
    include.type = 'button';
    include.textContent = labels.historyInclude;
    const fromNow = document.createElement('button');
    fromNow.className = 'button';
    fromNow.type = 'button';
    fromNow.textContent = labels.historyNow;
    const cancel = document.createElement('button');
    cancel.className = 'button ghost';
    cancel.type = 'button';
    cancel.textContent = labels.cancel;
    actions.append(include, fromNow, cancel);
    dialog.append(head, body, actions);
    document.body.append(dialog);

    let settled = false;
    const finish = (choice) => {
      if (settled) return;
      settled = true;
      dialog.close();
      resolve(choice);
    };
    include.addEventListener('click', () => finish('backfill'));
    fromNow.addEventListener('click', () => finish('now'));
    cancel.addEventListener('click', () => finish(null));
    close.addEventListener('click', () => finish(null));
    dialog.addEventListener('cancel', (event) => {
      event.preventDefault();
      finish(null);
    });
    dialog.addEventListener('close', () => dialog.remove(), { once: true });
    dialog.showModal();
    include.focus();
  });

  const showProcessingDialog = (choice) => {
    const dialog = document.createElement('dialog');
    dialog.className = 'moolias-dialog moolias-dialog-default newsletter-processing-dialog';
    dialog.setAttribute('aria-busy', 'true');
    const title = document.createElement('h2');
    title.textContent = labels.processingTitle;
    const body = document.createElement('p');
    body.className = 'moolias-dialog-message';
    body.setAttribute('role', 'status');
    body.textContent = choice === 'backfill'
      ? labels.processingHistory
      : labels.processingNow;
    const progress = document.createElement('progress');
    progress.setAttribute('aria-label', body.textContent);
    dialog.append(title, body, progress);
    document.body.append(dialog);
    dialog.showModal();
  };

  fetch('/account/newsletter-management', {
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
  })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((data) => {
      policyData = data;
      const serverEnabled = data.server_enabled === true;
      const effectiveEnabled = data.effective_enabled === true;
      const selection = data.selection || 'inherit';

      if (select) {
        if (selection === 'conflict') {
          let conflictOption = select.querySelector('option[value="conflict"]');
          if (!conflictOption) {
            conflictOption = document.createElement('option');
            conflictOption.value = 'conflict';
            conflictOption.disabled = true;
            conflictOption.textContent = language === 'de'
              ? 'Tag-Konflikt beheben'
              : 'Fix tag conflict';
            select.prepend(conflictOption);
          }
          select.value = 'conflict';
        } else {
          select.value = selection;
        }
      }
      setControlsDisabled(!serverEnabled);
      if (nav) nav.hidden = !effectiveEnabled;

      if (state) {
        if (!serverEnabled) state.textContent = labels.serverOff;
        else if (data.conflict === true) {
          state.textContent = data.conflict_source === 'mailbox'
            ? labels.conflictMailbox
            : labels.conflictDomain;
        } else if (data.source === 'mailbox') {
          state.textContent = effectiveEnabled ? labels.mailboxOn : labels.mailboxOff;
        } else {
          state.textContent = effectiveEnabled ? labels.inheritedOn : labels.inheritedOff;
        }
      }
    })
    .catch(() => {
      setControlsDisabled(true);
      if (nav) nav.hidden = true;
      if (state) state.textContent = labels.unavailable;
    });

  form?.addEventListener('submit', async (event) => {
    if (form.querySelector('input[name="backfill_history"]')) return;
    if (!policyData || !select) return;

    const current = policyData.conflict === true ? 'off' : (policyData.effective || 'off');
    const selection = select.value || 'inherit';
    const target = selection === 'inherit'
      ? (policyData.domain_default || 'off')
      : selection;
    if (current === 'on' || target !== 'on') return;

    event.preventDefault();
    event.stopImmediatePropagation();
    const submitter = event.submitter;
    const choice = await historyChoiceDialog();
    if (!choice) return;

    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'backfill_history';
    input.value = choice === 'backfill' ? '1' : '0';
    form.append(input);
    showProcessingDialog(choice);
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => form.requestSubmit(submitter || undefined));
    });
  });
})();
