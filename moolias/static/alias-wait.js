(() => {
  "use strict";

  const forms = () => Array.from(document.querySelectorAll("[data-alias-wait-form]"));
  if (!forms().length) return;

  const german = (document.documentElement.lang || "").toLowerCase().startsWith("de");
  const text = german
    ? {
        title: "Auf E-Mail warten",
        intro:
          "Moolias wartet jetzt auf die nächste E-Mail an diesen Alias. Sobald sie erkannt wurde, kannst du direkt in deinem Postfach nachsehen.",
        address: "Alias-Adresse",
        copy: "Kopieren",
        copied: "Kopiert",
        status: "E-Mail-Empfang",
        waiting: "Warte auf die nächste E-Mail an diesen Alias.",
        received: "Neue E-Mail empfangen. Bitte schau in deinem Postfach nach.",
        stopped:
          "Es wird nicht mehr auf eine E-Mail gewartet. Du kannst die Wartezeit erneut starten.",
        hint: "Du kannst dieses Fenster geöffnet lassen. Der Status wird automatisch aktualisiert.",
        stop: "Nicht weiter warten",
        restart: "Erneut auf Mail warten",
        done: "Fertig",
        close: "Schließen",
      }
    : {
        title: "Wait for email",
        intro:
          "Moolias is now waiting for the next email to this alias. As soon as it is detected, you can check your inbox.",
        address: "Alias address",
        copy: "Copy",
        copied: "Copied",
        status: "Email delivery",
        waiting: "Waiting for the next email to this alias.",
        received: "New email received. Please check your inbox.",
        stopped: "Moolias is no longer waiting for an email. You can start the waiting period again.",
        hint: "You can leave this window open. The status updates automatically.",
        stop: "Stop waiting",
        restart: "Wait for mail again",
        done: "Done",
        close: "Close",
      };

  document.querySelectorAll("[data-alias-wait-indicator]").forEach((indicator) => {
    indicator.classList.remove("mini-meta");
    indicator.classList.add("alias-wait-indicator");
  });

  const ensureWorkflowStyles = () => {
    if (document.querySelector('[data-alias-workflow-styles="1"]')) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/static/alias-workflow.css";
    link.dataset.aliasWorkflowStyles = "1";
    document.head.append(link);
  };

  const icon = (name) =>
    `<svg class="ui-icon" aria-hidden="true" focusable="false"><use href="/static/ui-icons.svg#icon-${name}"></use></svg>`;

  const updateWaitIcons = () => {
    for (const form of forms()) {
      const use = form.querySelector("[data-alias-wait-button] use");
      if (use) use.setAttribute("href", "/static/ui-icons.svg#icon-mail-search");
    }
  };

  let refreshTimer;
  let dialogPollTimer;
  let activeDialogForm = null;
  let activeWorkflowId = null;
  let activePollSeconds = 2;

  const updateForm = (form, active) => {
    const button = form.querySelector("[data-alias-wait-button]");
    if (!button) return;

    const startLabel = button.dataset.startLabel || "Wait for mail";
    const restartLabel = button.dataset.restartLabel || startLabel;
    const label = active ? restartLabel : startLabel;
    button.title = label;
    button.setAttribute("aria-label", label);
    button.dataset.waitActive = active ? "1" : "0";

    const row = form.closest(".alias-table-row");
    const indicator = row?.querySelector("[data-alias-wait-indicator]");
    if (indicator) indicator.hidden = !active;
  };

  const scheduleRefresh = (seconds) => {
    window.clearTimeout(refreshTimer);
    const delay = Math.max(1, Number(seconds) || 2) * 1000;
    refreshTimer = window.setTimeout(() => void refresh(), delay);
  };

  const refresh = async () => {
    try {
      const response = await fetch("/aliases/wait-status", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return;
      const payload = await response.json();
      const active = new Set(
        Array.isArray(payload.active)
          ? payload.active.map((item) => String(item.address || "").toLowerCase())
          : [],
      );
      for (const form of forms()) {
        const address = String(form.dataset.address || "").toLowerCase();
        updateForm(form, active.has(address));
      }
      updateWaitIcons();
      if (active.size > 0) scheduleRefresh(payload.poll_seconds);
    } catch (_) {
      // The form itself remains fully functional without the status enhancement.
    }
  };

  const ensureDialog = () => {
    let dialog = document.querySelector("[data-alias-manual-wait-dialog]");
    if (dialog) return dialog;

    ensureWorkflowStyles();
    dialog = document.createElement("dialog");
    dialog.className = "assign-dialog assign-dialog-single alias-workflow-dialog";
    dialog.dataset.aliasManualWaitDialog = "1";
    dialog.innerHTML = `
      <div class="dialog-head">
        <div>
          <h2>${text.title}</h2>
          <p class="muted alias-workflow-intro">${text.intro}</p>
        </div>
        <button class="dialog-close" type="button" aria-label="${text.close}" title="${text.close}" data-alias-wait-close>${icon("x")}</button>
      </div>
      <section class="alias-workflow-address-card">
        <div class="alias-workflow-address-copy">
          <span class="alias-workflow-address-label">${text.address}</span>
          <code data-alias-manual-wait-address></code>
        </div>
        <button class="button primary compact alias-workflow-copy" type="button" data-alias-manual-wait-copy>${text.copy}</button>
      </section>
      <section class="alias-workflow-status waiting" data-alias-manual-wait-status>
        <span class="alias-workflow-status-label">${text.status}</span>
        <div class="alias-workflow-status-message">
          <span class="alias-workflow-wait-spinner" aria-hidden="true" data-alias-manual-wait-spinner></span>
          <strong data-alias-manual-wait-message>${text.waiting}</strong>
        </div>
        <p class="muted alias-workflow-intro" data-alias-manual-wait-hint>${text.hint}</p>
        <div class="alias-workflow-wait-actions">
          <button class="button compact" type="button" data-alias-manual-wait-stop>${text.stop}</button>
          <button class="button compact" type="button" data-alias-manual-wait-restart hidden>${text.restart}</button>
        </div>
      </section>
      <div class="button-row top-gap">
        <button class="button" type="button" data-alias-manual-wait-done>${text.done}</button>
      </div>
    `;
    document.body.append(dialog);

    const close = () => {
      window.clearTimeout(dialogPollTimer);
      if (dialog.matches(":modal")) dialog.close();
    };
    dialog.querySelector("[data-alias-wait-close]")?.addEventListener("click", close);
    dialog.querySelector("[data-alias-manual-wait-done]")?.addEventListener("click", close);
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) close();
    });

    dialog.querySelector("[data-alias-manual-wait-copy]")?.addEventListener("click", async () => {
      const address = dialog.querySelector("[data-alias-manual-wait-address]")?.textContent || "";
      if (!address) return;
      await navigator.clipboard.writeText(address);
      const button = dialog.querySelector("[data-alias-manual-wait-copy]");
      if (!button) return;
      button.textContent = text.copied;
      window.setTimeout(() => {
        button.textContent = text.copy;
      }, 1200);
    });

    dialog.querySelector("[data-alias-manual-wait-stop]")?.addEventListener("click", async () => {
      if (!activeDialogForm || !activeWorkflowId) return;
      const csrf = activeDialogForm.querySelector('input[name="csrf_token"]')?.value || "";
      const body = new FormData();
      body.set("csrf_token", csrf);
      try {
        const response = await fetch(`/aliases/workflows/${activeWorkflowId}/stop`, {
          method: "POST",
          credentials: "same-origin",
          headers: { Accept: "application/json" },
          body,
        });
        if (!response.ok) return;
        renderDialogState("stopped");
        updateForm(activeDialogForm, false);
        window.clearTimeout(dialogPollTimer);
      } catch (_) {
        // Keep the current state visible; the normal form workflow remains available.
      }
    });

    dialog.querySelector("[data-alias-manual-wait-restart]")?.addEventListener("click", () => {
      if (activeDialogForm) void startWait(activeDialogForm);
    });

    return dialog;
  };

  const renderDialogState = (state) => {
    const dialog = ensureDialog();
    const status = dialog.querySelector("[data-alias-manual-wait-status]");
    const spinner = dialog.querySelector("[data-alias-manual-wait-spinner]");
    const message = dialog.querySelector("[data-alias-manual-wait-message]");
    const hint = dialog.querySelector("[data-alias-manual-wait-hint]");
    const stop = dialog.querySelector("[data-alias-manual-wait-stop]");
    const restart = dialog.querySelector("[data-alias-manual-wait-restart]");

    status?.classList.remove("waiting", "received", "stopped");
    status?.classList.add(state === "received" ? "received" : state === "stopped" ? "stopped" : "waiting");

    if (state === "received") {
      if (message) message.textContent = text.received;
      if (spinner) spinner.hidden = true;
      if (hint) hint.hidden = true;
      if (stop) stop.hidden = true;
      if (restart) restart.hidden = true;
      return;
    }
    if (state === "stopped") {
      if (message) message.textContent = text.stopped;
      if (spinner) spinner.hidden = true;
      if (hint) hint.hidden = true;
      if (stop) stop.hidden = true;
      if (restart) restart.hidden = false;
      return;
    }

    if (message) message.textContent = text.waiting;
    if (spinner) spinner.hidden = false;
    if (hint) hint.hidden = false;
    if (stop) stop.hidden = false;
    if (restart) restart.hidden = true;
  };

  const scheduleDialogPoll = () => {
    window.clearTimeout(dialogPollTimer);
    dialogPollTimer = window.setTimeout(() => void pollDialog(), Math.max(1, activePollSeconds) * 1000);
  };

  const pollDialog = async () => {
    const dialog = document.querySelector("[data-alias-manual-wait-dialog]");
    if (!dialog?.matches(":modal") || !activeWorkflowId) return;
    try {
      const response = await fetch(`/aliases/workflows/${activeWorkflowId}`, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return;
      const workflow = await response.json();
      const state = String(workflow.state || "waiting");
      renderDialogState(state);
      if (state === "received" || state === "stopped") {
        window.clearTimeout(dialogPollTimer);
        void refresh();
        return;
      }
    } catch (_) {
      // A later poll can recover from a transient request failure.
    }
    scheduleDialogPoll();
  };

  const openDialog = (form, payload) => {
    const dialog = ensureDialog();
    activeDialogForm = form;
    activeWorkflowId = Number(payload.workflow_id) || null;
    activePollSeconds = Math.max(1, Number(payload.poll_seconds) || 2);
    const address = dialog.querySelector("[data-alias-manual-wait-address]");
    if (address) address.textContent = String(payload.address || form.dataset.address || "");
    renderDialogState(String(payload.state || "waiting"));
    if (!dialog.matches(":modal")) {
      if (dialog.hasAttribute("open")) dialog.removeAttribute("open");
      dialog.showModal();
    }
    scheduleDialogPoll();
  };

  async function startWait(form) {
    const button = form.querySelector("[data-alias-wait-button]");
    if (button?.disabled) return;
    if (button) button.disabled = true;
    try {
      const response = await fetch(form.action, {
        method: "POST",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        body: new FormData(form),
      });
      if (!response.ok) throw new Error(`Alias wait failed with HTTP ${response.status}`);
      const payload = await response.json();
      updateForm(form, true);
      openDialog(form, payload);
      scheduleRefresh(payload.poll_seconds);
    } catch (_) {
      form.submit();
    } finally {
      if (button) button.disabled = false;
    }
  }

  for (const form of forms()) {
    if (form.dataset.aliasWaitBound === "1") continue;
    form.dataset.aliasWaitBound = "1";
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void startWait(form);
    });
  }

  updateWaitIcons();
  void refresh();
})();
