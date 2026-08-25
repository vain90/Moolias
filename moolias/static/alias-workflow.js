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
      copy: "Kopieren",
      done: "Fertig",
      close: "Schließen",
      failedTitle: "Alias konnte nicht erstellt werden",
      failed: "Der Alias konnte nicht erstellt werden.",
    },
    en: {
      title: "Alias created successfully",
      body: "You can now use this address with the service, shop, or provider.",
      aliasName: "Alias name",
      description: "Description",
      address: "Your new alias address",
      copy: "Copy",
      done: "Done",
      close: "Close",
      failedTitle: "Alias could not be created",
      failed: "The alias could not be created.",
    },
  }[language];

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

  function workflowDialog(payload) {
    const dialog = document.createElement("dialog");
    dialog.className = "assign-dialog assign-dialog-single alias-workflow-dialog";
    dialog.dataset.aliasWorkflowDialog = "1";
    dialog.dataset.aliasWorkflowState = payload.state;

    const head = document.createElement("div");
    head.className = "dialog-head";

    const heading = document.createElement("h2");
    heading.textContent = text.title;

    const close = document.createElement("button");
    close.className = "dialog-close";
    close.type = "button";
    close.textContent = "×";
    close.setAttribute("aria-label", text.close);
    close.title = text.close;
    head.append(heading, close);

    const body = document.createElement("p");
    body.className = "muted alias-workflow-intro";
    body.textContent = text.body;

    const addressCard = document.createElement("section");
    addressCard.className = "alias-workflow-address-card";

    const addressCopy = document.createElement("div");
    addressCopy.className = "alias-workflow-address-copy";

    const addressLabel = document.createElement("span");
    addressLabel.className = "alias-workflow-address-label";
    addressLabel.textContent = text.address;

    const address = document.createElement("code");
    address.dataset.aliasWorkflowAddress = "1";
    address.textContent = payload.address;
    addressCopy.append(addressLabel, address);

    const copy = document.createElement("button");
    copy.className = "button primary compact alias-workflow-copy";
    copy.type = "button";
    copy.dataset.aliasWorkflowCopy = "1";
    copy.textContent = text.copy;

    addressCard.append(addressCopy, copy);

    const metadata = document.createElement("dl");
    metadata.className = "alias-workflow-meta";
    metadata.append(metadataRow(text.aliasName, payload.name, "aliasWorkflowName"));
    if (payload.description) {
      metadata.append(
        metadataRow(text.description, payload.description, "aliasWorkflowDescription"),
      );
    }

    const actions = document.createElement("div");
    actions.className = "button-row alias-workflow-actions";

    const done = document.createElement("button");
    done.className = "button primary";
    done.type = "button";
    done.dataset.aliasWorkflowDone = "1";
    done.textContent = text.done;

    actions.append(done);
    dialog.append(head, body, addressCard, metadata, actions);
    return { dialog, close, copy, done };
  }

  function showState(payload) {
    if (!payload || payload.kind !== "alias_creation" || payload.state !== "created") {
      throw new Error("Unsupported alias workflow state");
    }
    if (!payload.address || !payload.name) {
      throw new Error("Alias workflow response is incomplete");
    }

    const { dialog, close, copy, done } = workflowDialog(payload);
    document.body.append(dialog);

    let reloadOnClose = true;
    const finish = () => dialog.close();

    copy.addEventListener("click", async () => {
      await navigator.clipboard.writeText(payload.address);
      const original = copy.textContent;
      copy.textContent = copiedLabel;
      window.setTimeout(() => { copy.textContent = original; }, 1200);
    });
    close.addEventListener("click", finish);
    done.addEventListener("click", finish);
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) finish();
    });
    dialog.addEventListener("close", () => {
      dialog.remove();
      if (reloadOnClose) window.location.reload();
    }, { once: true });

    dialog.showModal();
    copy.focus();

    return {
      dialog,
      transition(nextPayload) {
        reloadOnClose = false;
        dialog.close();
        return showState(nextPayload);
      },
    };
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

    if (!payload || payload.kind !== "alias_creation") {
      throw new Error(text.failed);
    }

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
        } else {
          window.alert(message);
        }
      } finally {
        delete form.dataset.aliasWorkflowSubmitting;
        if (submitter) submitter.disabled = false;
      }
    });
  }

  window.MooliasAliasWorkflow = { showState };
  bindCreateForm();
})();
