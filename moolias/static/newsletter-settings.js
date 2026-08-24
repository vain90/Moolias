(() => {
  const setting = document.querySelector('[data-newsletter-setting]');
  const nav = document.querySelector('[data-newsletter-nav]');
  if (!setting && !nav) return;

  const select = setting?.querySelector('[data-newsletter-mode-select]');
  const save = setting?.querySelector('[data-newsletter-save]');
  const state = setting?.querySelector('[data-newsletter-setting-state]');
  const language = document.documentElement.lang === 'de' ? 'de' : 'en';

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
            conflictOption.textContent = language === 'de' ? 'Tag-Konflikt beheben' : 'Fix tag conflict';
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
