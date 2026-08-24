(() => {
  const setting = document.querySelector('[data-newsletter-setting]');
  const nav = document.querySelector('[data-newsletter-nav]');
  const dialog = document.querySelector('[data-newsletter-opt-in-dialog]');
  if (!setting && !nav && !dialog) return;

  const toggle = setting?.querySelector('[data-newsletter-toggle]');
  const save = setting?.querySelector('[data-newsletter-save]');
  const state = setting?.querySelector('[data-newsletter-setting-state]');
  const language = document.documentElement.lang === 'de' ? 'de' : 'en';

  const labels = {
    de: {
      serverOff: 'Serverseitig deaktiviert. Deine gespeicherte Auswahl bleibt erhalten.',
      enabled: 'Für dieses Postfach aktiviert.',
      disabled: 'Für dieses Postfach deaktiviert.',
      undecided: 'Für dieses Postfach wurde noch keine Auswahl getroffen.',
      unavailable: 'Die Newsletter-Einstellung konnte nicht geladen werden.',
    },
    en: {
      serverOff: 'Disabled server-side. Your saved mailbox choice is retained.',
      enabled: 'Enabled for this mailbox.',
      disabled: 'Disabled for this mailbox.',
      undecided: 'No choice has been made for this mailbox yet.',
      unavailable: 'The newsletter setting could not be loaded.',
    },
  }[language];

  const setControlsDisabled = (disabled) => {
    if (toggle) toggle.disabled = disabled;
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
      const preference = data.preference;
      const effectiveEnabled = data.effective_enabled === true;

      if (toggle) toggle.checked = preference === true;
      setControlsDisabled(!serverEnabled);
      if (nav) nav.hidden = !effectiveEnabled;

      if (state) {
        if (!serverEnabled) state.textContent = labels.serverOff;
        else if (preference === true) state.textContent = labels.enabled;
        else if (preference === false) state.textContent = labels.disabled;
        else state.textContent = labels.undecided;
      }

      if (serverEnabled && preference === null && dialog) {
        dialog.hidden = false;
        if (typeof dialog.showModal === 'function') dialog.showModal();
        else dialog.setAttribute('open', '');
      }
    })
    .catch(() => {
      setControlsDisabled(true);
      if (nav) nav.hidden = true;
      if (state) state.textContent = labels.unavailable;
    });
})();
