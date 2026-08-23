(() => {
  const language = document.documentElement.lang?.toLowerCase().startsWith('de') ? 'de' : 'en';
  const text = {
    de: {
      title: 'Vorhandene Historie einbeziehen?',
      body: 'Möchtest du die noch verfügbare Mailcow/Rspamd-Historie auswerten, um deine Statistik soweit wie möglich rückwirkend zu vervollständigen? Es werden nur Daten übernommen, die der gewählte Statistikmodus speichern darf. Wie weit die Auswertung zurückreicht, hängt von der in Mailcow noch verfügbaren Historie ab.',
      include: 'Historie einbeziehen',
      fromNow: 'Nur ab jetzt erfassen',
      cancel: 'Abbrechen',
      close: 'Schließen',
    },
    en: {
      title: 'Include available history?',
      body: 'Would you like Moolias to evaluate the Mailcow/Rspamd history that is still available and complete your statistics as far back as possible? Only data permitted by the selected statistics mode will be stored. How far the evaluation can go back depends on the history still available in Mailcow.',
      include: 'Include history',
      fromNow: 'Collect from now on only',
      cancel: 'Cancel',
      close: 'Close',
    },
  }[language];

  const ranks = { off: 0, basic: 1, domain: 2, full: 3 };

  function historyChoiceDialog() {
    return new Promise((resolve) => {
      const dialog = document.createElement('dialog');
      dialog.className = 'moolias-dialog moolias-dialog-default stats-history-choice-dialog';

      const head = document.createElement('div');
      head.className = 'dialog-head';
      const title = document.createElement('h2');
      title.textContent = text.title;
      const close = document.createElement('button');
      close.className = 'dialog-close';
      close.type = 'button';
      close.textContent = '×';
      close.setAttribute('aria-label', text.close);
      close.title = text.close;
      head.append(title, close);

      const body = document.createElement('p');
      body.className = 'moolias-dialog-message';
      body.textContent = text.body;

      const actions = document.createElement('div');
      actions.className = 'button-row moolias-dialog-actions stats-history-choice-actions';
      const include = document.createElement('button');
      include.className = 'button primary';
      include.type = 'button';
      include.textContent = text.include;
      const fromNow = document.createElement('button');
      fromNow.className = 'button';
      fromNow.type = 'button';
      fromNow.textContent = text.fromNow;
      const cancel = document.createElement('button');
      cancel.className = 'button ghost';
      cancel.type = 'button';
      cancel.textContent = text.cancel;
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
  }

  document.addEventListener('submit', async (event) => {
    const form = event.target.closest?.('.usage-mode-form');
    if (!form || form.querySelector('input[name="backfill_history"]')) return;

    const select = form.querySelector('select[name="mode"]');
    const current = document.body.dataset.statsEffective || 'off';
    const domainDefault = document.body.dataset.statsDomain || 'off';
    const selection = select?.value || 'inherit';
    const target = selection === 'inherit' ? domainDefault : selection;
    if (!(current in ranks) || !(target in ranks) || ranks[target] <= ranks[current]) return;

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
    form.requestSubmit(submitter || undefined);
  });
})();