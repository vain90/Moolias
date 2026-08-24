(() => {
  const setting = document.querySelector('[data-newsletter-setting]');
  const nav = document.querySelector('[data-newsletter-nav]');
  const oldDialog = document.querySelector('[data-newsletter-opt-in-dialog]');
  oldDialog?.remove();
  if (!setting && !nav) return;

  const language = document.documentElement.lang === 'de' ? 'de' : 'en';
  const form = setting?.querySelector('form[action="/account/newsletter-management"]');
  const oldToggle = setting?.querySelector('[data-newsletter-toggle]');
  const oldSwitch = oldToggle?.closest('.switch-control');
  let select = setting?.querySelector('[data-newsletter-mode-select]');

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
  const description = setting?.querySelector('.setting-toggle-head .muted');
  const hint = setting?.querySelector('.hint');

  if (description) {
    description.textContent = language === 'de'
      ? 'Die Domain kann einen Standard vorgeben. Du kannst ihn für dein eigenes Postfach übernehmen oder mit An/Aus überschreiben.'
      : 'The domain can define a default. You can inherit it for your mailbox or override it with On/Off.';
  }
  if (hint) {
    hint.textContent = language === 'de'
      ? 'Wie bei der Statistik werden Newsletter-Tags direkt an Domain und Postfach in Mailcow ausgewertet. Ist die Funktion serverseitig deaktiviert, kann diese Einstellung nicht geändert werden.'
      : 'As with statistics, newsletter tags are evaluated directly on the Mailcow domain and mailbox. If the feature is disabled server-side, this setting cannot be changed.';
  }

  const labels = {
    de: {
      serverOff: 'Newsletter-Verwaltung ist serverseitig deaktiviert.',
      inheritedOn: 'Aktiviert über die Domain-Einstellung.',
      inheritedOff: 'Deaktiviert über die Domain-Einstellung.',
      mailboxOn: 'Für dieses Postfach aktiviert.',
      mailboxOff: 'Für dieses Postfach deaktiviert.',
      conflictMailbox: 'Widersprüchliche Newsletter-Tags am Postfach. Die Funktion bleibt aus, bis der Konflikt behoben ist.',
      conflictDomain: 'Widersprüchliche Newsletter-Tags an der Domain. Die Funktion bleibt aus, bis der Konflikt behoben ist.',
      unavailable: 'Die Newsletter-Einstellung konnte nicht geladen werden.',
    },
    en: {
      serverOff: 'Newsletter management is disabled server-side.',
      inheritedOn: 'Enabled by the domain setting.',
      inheritedOff: 'Disabled by the domain setting.',
      mailboxOn: 'Enabled for this mailbox.',
      mailboxOff: 'Disabled for this mailbox.',
      conflictMailbox: 'Conflicting newsletter tags on the mailbox. The feature stays off until the conflict is fixed.',
      conflictDomain: 'Conflicting newsletter tags on the domain. The feature stays off until the conflict is fixed.',
      unavailable: 'The newsletter setting could not be loaded.',
    },
  }[language];

  const setControlsDisabled = (disabled) => {
    if (select) select.disabled = disabled;
    if (save) save.disabled = disabled;
    setting?.classList.toggle('is-disabled', disabled);
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
})();
