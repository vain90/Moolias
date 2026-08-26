(() => {
  "use strict";

  const language = document.documentElement.lang?.toLowerCase().startsWith("de") ? "de" : "en";
  const copiedLabel = document.body.dataset.copiedLabel || (language === "de" ? "Kopiert" : "Copied");
  const text = {
    de: {
      title: "Alias erfolgreich erstellt",
      body: "Du kannst diese Adresse jetzt beim Dienst, Shop oder Anbieter eintragen.",
      aliasName: "Aliasname",
      description: "Beschreibung",
      address: "Deine neue Alias-Adresse",
      oldAddress: "Bisherige Alias-Adresse",
      copy: "Kopieren",
      done: "Fertig",
      close: "Schließen",
      failedTitle: "Alias konnte nicht erstellt werden",
      failed: "Der Alias konnte nicht erstellt werden.",
      waiting: "Warte auf die erste E-Mail an diese Adresse.",
      oldReceived: "An die alte Adresse ist noch eine E-Mail eingegangen. Die neue Adresse wird weiter geprüft.",
      received: "Neue E-Mail empfangen. Bitte schau in deinem Postfach nach.",
      stopped: "Die Prüfung ist pausiert. Du kannst sie jederzeit fortsetzen.",
      stop: "Nicht weiter warten",
      resume: "Prüfung fortsetzen",
      replacementTitle: "Aliaswechsel gestartet",
      replacementIntro: "Die alte und die neue Adresse bleiben zunächst aktiv. Sobald eine E-Mail an die neue Adresse angekommen ist, kannst du festlegen, wann die alte Adresse deaktiviert wird.",
      replacementStartTitle: "Alias ersetzen",
      replacementStartBody: "Wähle die neue Adresse. Die bisherige Adresse bleibt aktiv, bis du sie später ausdrücklich deaktivierst oder einen Zeitpunkt festlegst.",
      addressStyle: "Format der neuen Adresse",
      named: "Name + Zufall",
      readable: "Lesbarer Zufall",
      custom: "Eigene Adresse",
      customAddress: "Eigene Adresse",
      customPlaceholder: "mein-alias",
      startReplacement: "Aliaswechsel starten",
      cancel: "Abbrechen",
      replaceFailed: "Der Aliaswechsel konnte nicht gestartet werden.",
      pending: "Aliaswechsel läuft",
      oldBadge: "ALT",
      newBadge: "NEU",
      openStatus: "Status öffnen",
      deactivateTitle: "Wann soll die alte Adresse deaktiviert werden?",
      deactivateBody: "Die neue Adresse funktioniert. Du kannst die alte Adresse jetzt deaktivieren oder einen späteren Zeitpunkt wählen.",
      deactivateLater: "Später selbst",
      deactivateNow: "Jetzt deaktivieren",
      deactivate7: "In 7 Tagen",
      deactivate30: "In 30 Tagen",
      deactivateConfirmTitle: "Alte Adresse jetzt deaktivieren?",
      deactivateConfirmBody: "Die bisherige Alias-Adresse wird sofort deaktiviert. Die neue Adresse bleibt aktiv.",
      scheduled7: "Die alte Adresse wird in 7 Tagen deaktiviert.",
      scheduled30: "Die alte Adresse wird in 30 Tagen deaktiviert.",
      scheduledLater: "Die alte Adresse bleibt aktiv, bis du sie selbst deaktivierst.",
      completed: "Aliaswechsel abgeschlossen.",
    },
    en: {
      title: "Alias created successfully",
      body: "You can now use this address with the service, shop, or provider.",
      aliasName: "Alias name",
      description: "Description",
      address: "Your new alias address",
      oldAddress: "Previous alias address",
      copy: "Copy",
      done: "Done",
      close: "Close",
      failedTitle: "Alias could not be created",
      failed: "The alias could not be created.",
      waiting: "Waiting for the first email to this address.",
      oldReceived: "An email still arrived at the old address. The new address is still being checked.",
      received: "New email received. Please check your inbox.",
      stopped: "The check is paused. You can resume it at any time.",
      stop: "Stop waiting",
      resume: "Resume check",
      replacementTitle: "Alias change started",
      replacementIntro: "The old and new addresses stay active for now. Once an email reaches the new address, you can choose when to disable the old address.",
      replacementStartTitle: "Replace alias",
      replacementStartBody: "Choose the new address. The previous address stays active until you explicitly disable it or schedule deactivation later.",
      addressStyle: "New address format",
      named: "Name + random",
      readable: "Readable random",
      custom: "Custom address",
      customAddress: "Custom address",
      customPlaceholder: "my-alias",
      startReplacement: "Start alias change",
      cancel: "Cancel",
      replaceFailed: "The alias change could not be started.",
      pending: "Alias change in progress",
      oldBadge: "OLD",
      newBadge: "NEW",
      openStatus: "Open status",
      deactivateTitle: "When should the old address be disabled?",
      deactivateBody: "The new address works. You can disable the old address now or choose a later time.",
      deactivateLater: "Later, manually",
      deactivateNow: "Disable now",
      deactivate7: "In 7 days",
      deactivate30: "In 30 days",
      deactivateConfirmTitle: "Disable the old address now?",
      deactivateConfirmBody: "The previous alias address will be disabled immediately. The new address stays active.",
      scheduled7: "The old address will be disabled in 7 days.",
      scheduled30: "The old address will be disabled in 30 days.",
      scheduledLater: "The old address stays active until you disable it yourself.",
      completed: "Alias change completed.",
    },
  }[language];

  function ensureStyles() {
    if (document.querySelector('link[data-alias-workflow-styles]')) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/static/alias-workflow.css";
    link.dataset.aliasWorkflowStyles = "1";
    document.head.append(link);
  }

  function csrfToken() {
    return document.body.dataset.csrfToken
      || document.querySelector('input[name="csrf_token"]')?.value
      || "";
  }

  async function postWorkflow(workflowId, action, fields = {}) {
    const form = new FormData();
    form.append("csrf_token", csrfToken());
    Object.entries(fields).forEach(([key, value]) => form.append(key, String(value)));
    const response = await fetch(`/aliases/workflows/${workflowId}/${action}`, {
      method: "POST",
      body: form,
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      console.debug("Alias workflow response did not contain JSON", error);
    }
    if (!response.ok) {
      const detail = payload?.detail;
      throw new Error(typeof detail === "string" ? detail : `HTTP ${response.status}`);
    }
    return payload;
  }

  async function fetchWorkflow(workflowId) {
    const response = await fetch(`/aliases/workflows/${workflowId}`, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  function metadataRow(labelText, value, dataAttribute) {
    const row = document.createElement("div");
    row.className = "alias-workflow-meta-row";
    const label = document.createElement("dt");
    label.textContent = labelText;
    const valueElement = document.createElement("dd");
    if (dataAttribute) valueElement.dataset[dataAttribute] = "1";
    valueElement.textContent = value;
    row.append(label, valueElement);
    return row;
  }

  function createButton(label, className = "button compact") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    return button;
  }

  function statusMessage(workflow) {
    if (workflow.completed) return text.completed;
    if (workflow.state === "received") return text.received;
    if (workflow.state === "old_received") return text.oldReceived;
    if (workflow.state === "stopped") return text.stopped;
    return text.waiting;
  }

  function scheduledMessage(workflow) {
    if (workflow.deactivation_mode === "7d") return text.scheduled7;
    if (workflow.deactivation_mode === "30d") return text.scheduled30;
    return text.scheduledLater;
  }

  function workflowDialog(payload, initialWorkflow, replacement = false) {
    const dialog = document.createElement("dialog");
    dialog.className = "assign-dialog assign-dialog-single alias-workflow-dialog";
    dialog.dataset.aliasWorkflowDialog = "1";
    dialog.dataset.aliasWorkflowState = payload.state || "created";

    const head = document.createElement("div");
    head.className = "dialog-head";
    const heading = document.createElement("h2");
    heading.textContent = replacement ? text.replacementTitle : text.title;
    const close = createButton("×", "dialog-close");
    close.setAttribute("aria-label", text.close);
    close.title = text.close;
    head.append(heading, close);

    const body = document.createElement("p");
    body.className = "muted alias-workflow-intro";
    body.textContent = replacement ? text.replacementIntro : text.body;

    const addressCard = document.createElement("section");
    addressCard.className = "alias-workflow-address-card";
    const addressCopy = document.createElement("div");
    addressCopy.className = "alias-workflow-address-copy";
    const addressLabel = document.createElement("span");
    addressLabel.className = "alias-workflow-address-label";
    addressLabel.textContent = text.address;
    const address = document.createElement("code");
    address.dataset.aliasWorkflowAddress = "1";
    address.textContent = payload.address || initialWorkflow.new_address;
    addressCopy.append(addressLabel, address);
    const copy = createButton(text.copy, "button primary compact alias-workflow-copy");
    copy.dataset.aliasWorkflowCopy = "1";
    addressCard.append(addressCopy, copy);

    const metadata = document.createElement("dl");
    metadata.className = "alias-workflow-meta";
    const name = payload.name || initialWorkflow.name || "";
    const description = payload.description || initialWorkflow.description || "";
    if (name) metadata.append(metadataRow(text.aliasName, name, "aliasWorkflowName"));
    if (description) {
      metadata.append(metadataRow(text.description, description, "aliasWorkflowDescription"));
    }
    if (replacement && initialWorkflow.old_address) {
      metadata.append(metadataRow(text.oldAddress, initialWorkflow.old_address));
    }

    const statusBox = document.createElement("section");
    statusBox.className = "alias-workflow-status";
    statusBox.dataset.aliasWorkflowWaitingState = "1";
    const statusLabel = document.createElement("span");
    statusLabel.className = "alias-workflow-status-label";
    statusLabel.textContent = replacement ? text.pending : text.address;
    const statusText = document.createElement("strong");
    const statusActions = document.createElement("div");
    statusActions.className = "alias-workflow-wait-actions";
    statusBox.append(statusLabel, statusText, statusActions);

    const deactivation = document.createElement("section");
    deactivation.className = "alias-workflow-deactivation";
    deactivation.hidden = true;
    const deactivationTitle = document.createElement("h3");
    deactivationTitle.textContent = text.deactivateTitle;
    const deactivationBody = document.createElement("p");
    deactivationBody.textContent = text.deactivateBody;
    const deactivationCurrent = document.createElement("p");
    deactivationCurrent.className = "alias-workflow-current-choice";
    const deactivationActions = document.createElement("div");
    deactivationActions.className = "alias-workflow-deactivation-actions";
    deactivation.append(
      deactivationTitle,
      deactivationBody,
      deactivationCurrent,
      deactivationActions,
    );

    const actions = document.createElement("div");
    actions.className = "button-row alias-workflow-actions";
    const done = createButton(text.done, "button primary");
    done.dataset.aliasWorkflowDone = "1";
    actions.append(done);

    dialog.append(head, body, addressCard, metadata, statusBox, deactivation, actions);

    let workflow = initialWorkflow;
    let pollTimer = null;

    const stopPolling = () => {
      if (pollTimer !== null) {
        window.clearTimeout(pollTimer);
        pollTimer = null;
      }
    };

    const update = (nextWorkflow) => {
      workflow = nextWorkflow;
      dialog.dataset.aliasWorkflowState = nextWorkflow.state || "created";
      statusBox.className = "alias-workflow-status";
      if (nextWorkflow.state === "received") statusBox.classList.add("received");
      if (nextWorkflow.state === "old_received") statusBox.classList.add("old-received");
      if (nextWorkflow.state === "stopped") statusBox.classList.add("stopped");
      statusText.textContent = statusMessage(nextWorkflow);
      statusActions.replaceChildren();

      if (!nextWorkflow.completed && ["waiting", "old_received"].includes(nextWorkflow.state)) {
        const stop = createButton(text.stop, "button ghost compact");
        stop.dataset.aliasWorkflowStop = "1";
        stop.addEventListener("click", async () => {
          stop.disabled = true;
          try {
            update(await postWorkflow(nextWorkflow.id, "stop"));
          } catch (error) {
            console.error("Could not stop alias check", error);
            stop.disabled = false;
          }
        });
        statusActions.append(stop);
      } else if (!nextWorkflow.completed && nextWorkflow.state === "stopped") {
        const resume = createButton(text.resume, "button compact");
        resume.dataset.aliasWorkflowResume = "1";
        resume.addEventListener("click", async () => {
          resume.disabled = true;
          try {
            const resumed = await postWorkflow(nextWorkflow.id, "resume");
            update(resumed);
            schedulePoll();
          } catch (error) {
            console.error("Could not resume alias check", error);
            resume.disabled = false;
          }
        });
        statusActions.append(resume);
      }

      deactivation.hidden = !(replacement && nextWorkflow.state === "received" && !nextWorkflow.completed);
      if (!deactivation.hidden) {
        deactivationCurrent.textContent = scheduledMessage(nextWorkflow);
        deactivationActions.replaceChildren();
        const choices = [
          ["later", text.deactivateLater],
          ["7d", text.deactivate7],
          ["30d", text.deactivate30],
          ["now", text.deactivateNow],
        ];
        choices.forEach(([mode, label]) => {
          const button = createButton(
            label,
            mode === "now" ? "button danger compact" : "button compact",
          );
          if (nextWorkflow.deactivation_mode === mode) button.classList.add("primary");
          button.addEventListener("click", async () => {
            let confirmed = true;
            if (mode === "now") {
              confirmed = window.MooliasDialog?.confirm
                ? await window.MooliasDialog.confirm({
                    title: text.deactivateConfirmTitle,
                    message: text.deactivateConfirmBody,
                    confirmLabel: text.deactivateNow,
                    tone: "danger",
                    dismissOnBackdrop: false,
                  })
                : false;
            }
            if (!confirmed) return;
            button.disabled = true;
            try {
              const updated = await postWorkflow(nextWorkflow.id, "deactivation", {
                mode,
                confirm_now: mode === "now" ? "1" : "0",
              });
              update(updated);
              if (updated.completed) {
                window.setTimeout(() => dialog.close(), 700);
              }
            } catch (error) {
              console.error("Could not update alias deactivation", error);
              button.disabled = false;
            }
          });
          deactivationActions.append(button);
        });
      }

      if (nextWorkflow.completed || nextWorkflow.state === "received" || nextWorkflow.state === "stopped") {
        stopPolling();
      }
    };

    const schedulePoll = () => {
      stopPolling();
      if (!workflow?.id || workflow.completed || !["waiting", "old_received"].includes(workflow.state)) {
        return;
      }
      pollTimer = window.setTimeout(async () => {
        try {
          const current = await fetchWorkflow(workflow.id);
          update(current);
        } catch (error) {
          console.debug("Could not refresh alias workflow", error);
        }
        schedulePoll();
      }, 2000);
    };

    copy.addEventListener("click", async () => {
      await navigator.clipboard.writeText(address.textContent);
      const original = copy.textContent;
      copy.textContent = copiedLabel;
      window.setTimeout(() => { copy.textContent = original; }, 1200);
    });
    close.addEventListener("click", () => dialog.close());
    done.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener("close", () => {
      stopPolling();
      dialog.remove();
      window.location.reload();
    }, { once: true });

    update(workflow);
    dialog.showModal();
    copy.focus();
    schedulePoll();
    return { dialog, update };
  }

  function showState(payload) {
    if (!payload || payload.kind !== "alias_creation" || payload.state !== "created") {
      throw new Error("Unsupported alias workflow state");
    }
    if (!payload.address || !payload.name) {
      throw new Error("Alias workflow response is incomplete");
    }
    const workflow = payload.workflow || {
      id: null,
      kind: "creation",
      state: "stopped",
      new_address: payload.address,
      name: payload.name,
      description: payload.description || "",
      completed: false,
    };
    return workflowDialog(payload, workflow, false);
  }

  function showReplacementState(workflow, payload = {}) {
    return workflowDialog(
      {
        state: "created",
        address: workflow.new_address,
        name: payload.name || workflow.name,
        description: payload.description || workflow.description,
      },
      workflow,
      true,
    );
  }

  async function submitCreateForm(form, submitter) {
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      console.debug("Alias creation response did not contain JSON", error);
    }
    if (!response.ok) {
      const detail = payload?.detail;
      const message = typeof detail === "string" ? detail : text.failed;
      throw new Error(message);
    }
    if (!payload || payload.kind !== "alias_creation") throw new Error(text.failed);
    form.closest("dialog")?.close();
    form.reset();
    form.querySelector('[data-mode-option]:checked')?.dispatchEvent(new Event("change", { bubbles: true }));
    showState(payload);
    submitter?.blur();
  }

  function bindCreateForm() {
    const form = document.querySelector("[data-alias-create-form]");
    if (!form || form.dataset.aliasWorkflowBound === "1") return;
    form.dataset.aliasWorkflowBound = "1";
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (form.dataset.aliasWorkflowSubmitting === "1") return;
      const submitter = event.submitter;
      form.dataset.aliasWorkflowSubmitting = "1";
      if (submitter) submitter.disabled = true;
      try {
        await submitCreateForm(form, submitter);
      } catch (error) {
        console.error("Alias creation failed", error);
        const message = error instanceof Error && error.message ? error.message : text.failed;
        if (window.MooliasDialog?.error) {
          await window.MooliasDialog.error(message, { title: text.failedTitle });
        }
      } finally {
        delete form.dataset.aliasWorkflowSubmitting;
        if (submitter) submitter.disabled = false;
      }
    });
  }

  function replacementModeOption(value, title, checked = false) {
    const label = document.createElement("label");
    label.className = "mode-option";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "guided-replacement-mode";
    radio.value = value;
    radio.checked = checked;
    const body = document.createElement("span");
    body.className = "mode-option-body";
    const strong = document.createElement("strong");
    strong.textContent = title;
    body.append(strong);
    label.append(radio, body);
    return { label, radio };
  }

  function showReplacementDialog(aliasCheckbox, editDetails) {
    const oldAddress = aliasCheckbox.dataset.address || "";
    const domain = oldAddress.split("@").slice(1).join("@");
    const dialog = document.createElement("dialog");
    dialog.className = "assign-dialog alias-workflow-dialog";
    const head = document.createElement("div");
    head.className = "dialog-head";
    const heading = document.createElement("h2");
    heading.textContent = text.replacementStartTitle;
    const close = createButton("×", "dialog-close");
    close.setAttribute("aria-label", text.close);
    head.append(heading, close);
    const body = document.createElement("p");
    body.className = "muted";
    body.textContent = text.replacementStartBody;
    const oldCode = document.createElement("code");
    oldCode.className = "assign-address";
    oldCode.textContent = oldAddress;

    const fieldset = document.createElement("fieldset");
    fieldset.className = "mode-picker top-gap";
    const legend = document.createElement("legend");
    legend.textContent = text.addressStyle;
    const named = replacementModeOption("named", text.named, true);
    const readable = replacementModeOption("readable", text.readable);
    const custom = replacementModeOption("custom", text.custom);
    fieldset.append(legend, named.label, readable.label, custom.label);

    const customLabel = document.createElement("label");
    customLabel.className = "hidden top-gap";
    customLabel.textContent = text.customAddress;
    const addressInput = document.createElement("div");
    addressInput.className = "address-input";
    const localPart = document.createElement("input");
    localPart.maxLength = 63;
    localPart.placeholder = text.customPlaceholder;
    localPart.autocomplete = "off";
    const suffix = document.createElement("span");
    suffix.textContent = `@${domain}`;
    addressInput.append(localPart, suffix);
    customLabel.append(addressInput);
    [named.radio, readable.radio, custom.radio].forEach((radio) => {
      radio.addEventListener("change", () => {
        customLabel.classList.toggle("hidden", !custom.radio.checked);
      });
    });

    const actions = document.createElement("div");
    actions.className = "button-row top-gap";
    const confirm = createButton(text.startReplacement, "button primary");
    const cancel = createButton(text.cancel, "button");
    actions.append(confirm, cancel);
    dialog.append(head, body, oldCode, fieldset, customLabel, actions);
    document.body.append(dialog);
    editDetails?.removeAttribute("open");

    const closeDialog = () => dialog.close();
    close.addEventListener("click", closeDialog);
    cancel.addEventListener("click", closeDialog);
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) closeDialog();
    });
    dialog.addEventListener("close", () => dialog.remove(), { once: true });

    confirm.addEventListener("click", async () => {
      const mode = [named.radio, readable.radio, custom.radio].find((radio) => radio.checked)?.value;
      if (!mode) return;
      if (mode === "custom" && !localPart.value.trim()) {
        localPart.focus();
        return;
      }
      const form = new FormData();
      form.append("csrf_token", csrfToken());
      form.append("mode", mode);
      form.append("local_part", localPart.value.trim());
      confirm.disabled = true;
      cancel.disabled = true;
      try {
        const response = await fetch(`/aliases/${aliasCheckbox.value}/replace`, {
          method: "POST",
          body: form,
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        let payload = null;
        try {
          payload = await response.json();
        } catch (error) {
          console.debug("Alias replacement response did not contain JSON", error);
        }
        if (!response.ok || !payload?.workflow) {
          const detail = payload?.detail;
          if (detail?.code === "replacement_pending" && detail.workflow) {
            dialog.remove();
            showReplacementState(detail.workflow);
            return;
          }
          throw new Error(typeof detail === "string" ? detail : text.replaceFailed);
        }
        dialog.remove();
        showReplacementState(payload.workflow, payload);
      } catch (error) {
        console.error("Alias replacement failed", error);
        confirm.disabled = false;
        cancel.disabled = false;
        if (window.MooliasDialog?.error) {
          await window.MooliasDialog.error(text.replaceFailed, { title: text.replacementStartTitle });
        }
      }
    });

    dialog.showModal();
  }

  async function decoratePendingWorkflows() {
    try {
      const response = await fetch("/aliases/workflows", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return;
      const payload = await response.json();
      for (const workflow of payload.pending || []) {
        const roles = [
          [workflow.old_address, "old", text.oldBadge],
          [workflow.new_address, "new", text.newBadge],
        ];
        for (const [address, role, label] of roles) {
          if (!address) continue;
          const checkbox = [...document.querySelectorAll("[data-alias-select]")]
            .find((item) => (item.dataset.address || "").toLowerCase() === address.toLowerCase());
          const row = checkbox?.closest(".alias-row");
          if (!row || row.dataset.aliasWorkflowDecorated === `${workflow.id}-${role}`) continue;
          row.dataset.aliasWorkflowDecorated = `${workflow.id}-${role}`;
          row.classList.add(`alias-migration-${role}`);
          const identity = row.querySelector(".alias-info");
          const heading = identity?.querySelector("strong");
          if (heading) {
            const badge = document.createElement("span");
            badge.className = "alias-workflow-badge";
            badge.textContent = label;
            heading.after(badge);
          }
          if (identity) {
            const state = document.createElement("div");
            state.className = "alias-workflow-row-state";
            const labelText = document.createElement("span");
            labelText.textContent = statusMessage(workflow);
            const open = createButton(text.openStatus, "button ghost compact");
            open.addEventListener("click", () => showReplacementState(workflow));
            state.append(labelText, open);
            identity.append(state);
          }
          row.querySelector("[data-replace-alias]")?.setAttribute("disabled", "disabled");
        }
      }
    } catch (error) {
      console.debug("Could not load pending alias changes", error);
    }
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest?.("[data-replace-alias]");
    if (!button || button.disabled) return;
    const row = button.closest(".alias-row");
    const checkbox = row?.querySelector("[data-alias-select]");
    if (!checkbox) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    showReplacementDialog(checkbox, button.closest("details.alias-edit-action"));
  }, true);

  ensureStyles();
  window.MooliasAliasWorkflow = { showState, showReplacementState };
  bindCreateForm();
  void decoratePendingWorkflows();
})();
