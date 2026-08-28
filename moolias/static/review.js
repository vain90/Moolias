(() => {
  "use strict";

  const REOPEN_KEY = "moolias-unexpected-review-reopen";
  const RESOLVED_FEEDBACK_MS = 450;
  let actionDialogChanged = false;

  const actionDialog = () => document.querySelector("dialog[data-action-required-dialog]");

  const markForReopen = () => {
    try {
      sessionStorage.setItem(REOPEN_KEY, "1");
    } catch (error) {
      console.debug("sessionStorage is unavailable", error);
    }
  };

  const clearReopen = () => {
    try {
      sessionStorage.removeItem(REOPEN_KEY);
    } catch (error) {
      console.debug("sessionStorage is unavailable", error);
    }
  };

  const openActionDialog = () => {
    const dialog = actionDialog();
    if (!dialog) return false;
    if (dialog.open && !dialog.matches(":modal")) dialog.close();
    if (!dialog.open) dialog.showModal();
    return true;
  };

  const closeActionDialog = () => {
    const dialog = actionDialog();
    if (dialog?.open) dialog.close();
    clearReopen();
    const url = new URL(window.location.href);
    if (url.searchParams.get("action") === "required") {
      url.searchParams.delete("action");
      window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
    }
    if (actionDialogChanged && window.location.pathname === "/aliases") {
      actionDialogChanged = false;
      window.location.reload();
    }
  };

  const getSummary = () => {
    const total = Number.parseInt(actionDialog()?.dataset.actionRequiredTotal || "0", 10);
    return { total: Number.isFinite(total) ? total : 0 };
  };

  const parseServerDocument = async (response) => {
    if (response.status === 401) {
      window.location.assign("/");
      return null;
    }
    if (!response.ok) {
      throw new Error(`Action-required request failed with HTTP ${response.status}`);
    }
    return new DOMParser().parseFromString(await response.text(), "text/html");
  };

  const selectorValue = (value) => CSS.escape(String(value || ""));

  const syncSenderRow = (currentRow, freshRow) => {
    currentRow.className = freshRow.className;

    const currentState = currentRow.querySelector(".sender-review-state");
    const freshState = freshRow.querySelector(".sender-review-state");
    if (currentState && freshState) currentState.textContent = freshState.textContent;

    const currentCount = currentRow.querySelector(".sender-message-count");
    const freshCount = freshRow.querySelector(".sender-message-count");
    if (currentCount && freshCount) currentCount.textContent = freshCount.textContent;

    const currentForm = currentRow.querySelector("[data-action-sender-form]");
    const freshForm = freshRow.querySelector("[data-action-sender-form], .sender-review-form");
    const currentDecision = currentForm?.querySelector('input[name="decision"]');
    const freshDecision = freshForm?.querySelector('input[name="decision"]');
    const currentButton = currentForm?.querySelector('button[type="submit"]');
    const freshButton = freshForm?.querySelector('button[type="submit"]');
    if (currentDecision && freshDecision) currentDecision.value = freshDecision.value;
    if (currentButton && freshButton) {
      currentButton.textContent = freshButton.textContent;
      currentButton.className = freshButton.className;
      currentButton.disabled = false;
    }
  };

  const freshSenderRow = (serverDocument, aliasId, senderKey) => {
    const senderSelector = `[data-action-sender-row][data-alias-id="${selectorValue(aliasId)}"][data-sender-key="${selectorValue(senderKey)}"]`;
    const actionRow = serverDocument.querySelector(
      `dialog[data-action-required-dialog] ${senderSelector}`,
    );
    if (actionRow) return actionRow;

    const aliasSelect = serverDocument.querySelector(
      `[data-alias-select][value="${selectorValue(aliasId)}"]`,
    );
    const aliasRow = aliasSelect?.closest(".alias-row");
    if (!aliasRow) return null;
    return [...aliasRow.querySelectorAll('.sender-review-form input[name="sender_key"]')]
      .find((input) => input.value === senderKey)
      ?.closest(".sender-stats-row") || null;
  };

  const hideAfterResolvedFeedback = (element) => {
    if (!element) return;
    window.setTimeout(() => {
      if (element.isConnected) element.hidden = true;
    }, RESOLVED_FEEDBACK_MS);
  };

  const syncActionSummary = (serverDocument) => {
    const currentDialog = actionDialog();
    const freshDialog = serverDocument.querySelector("dialog[data-action-required-dialog]");
    if (currentDialog && freshDialog) {
      currentDialog.dataset.actionRequiredTotal = freshDialog.dataset.actionRequiredTotal || "0";

      const currentDialogEmpty = currentDialog.querySelector("[data-action-required-empty]");
      const freshDialogEmpty = freshDialog.querySelector("[data-action-required-empty]");
      if (currentDialogEmpty && freshDialogEmpty) {
        currentDialogEmpty.hidden = freshDialogEmpty.hidden;
      }
    }

    const currentOverviewCount = document.querySelector("[data-action-count]");
    const freshOverviewCount = serverDocument.querySelector("[data-action-count]");
    if (currentOverviewCount && freshOverviewCount) {
      currentOverviewCount.textContent = freshOverviewCount.textContent;
    }

    const currentEmpty = document.querySelector("[data-action-empty]");
    const freshEmpty = serverDocument.querySelector("[data-action-empty]");
    if (currentEmpty && freshEmpty) currentEmpty.hidden = freshEmpty.hidden;

    const currentTrigger = document.querySelector(
      ".action-required-button[data-action-required-open]",
    );
    const freshTrigger = serverDocument.querySelector(
      ".action-required-button[data-action-required-open]",
    );
    if (currentTrigger && freshTrigger) {
      currentTrigger.textContent = freshTrigger.textContent;
      currentTrigger.className = freshTrigger.className;
    }
  };

  const syncUnexpectedReview = (serverDocument, aliasId, senderKey) => {
    const dialog = actionDialog();
    if (!dialog) return;

    const aliasSelector = `[data-action-alias-id="${selectorValue(aliasId)}"]`;
    const currentAlias = dialog.querySelector(aliasSelector);
    const freshAlias = serverDocument.querySelector(
      `dialog[data-action-required-dialog] ${aliasSelector}`,
    );

    if (!currentAlias) return;
    const senderSelector = `[data-action-sender-row][data-alias-id="${selectorValue(aliasId)}"][data-sender-key="${selectorValue(senderKey)}"]`;
    const currentRow = currentAlias.querySelector(senderSelector);
    const freshRow = freshSenderRow(serverDocument, aliasId, senderKey);
    if (currentRow && freshRow) syncSenderRow(currentRow, freshRow);

    if (!freshAlias) {
      hideAfterResolvedFeedback(currentAlias);
    } else {
      const currentBadge = currentAlias.querySelector("[data-action-alias-unexpected-count]");
      const freshBadge = freshAlias.querySelector("[data-action-alias-unexpected-count]");
      if (currentBadge && freshBadge) currentBadge.textContent = freshBadge.textContent;
    }

    const currentSection = dialog.querySelector("[data-action-required-unexpected-section]");
    const freshSection = serverDocument.querySelector(
      "dialog[data-action-required-dialog] [data-action-required-unexpected-section]",
    );
    if (currentSection) {
      if (!freshSection) {
        hideAfterResolvedFeedback(currentSection);
      } else {
        const currentCount = currentSection.querySelector("[data-action-unexpected-count]");
        const freshCount = freshSection.querySelector("[data-action-unexpected-count]");
        if (currentCount && freshCount) currentCount.textContent = freshCount.textContent;
      }
    }

    syncActionSummary(serverDocument);
  };

  const submitExpectedSender = async (form) => {
    const row = form.closest("[data-action-sender-row]");
    const aliasId = row?.dataset.aliasId;
    const senderKey = row?.dataset.senderKey;
    const button = form.querySelector('button[type="submit"]');
    if (!row || !aliasId || !senderKey) return false;

    if (button) button.disabled = true;
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: { Accept: "text/html" },
      });
      const serverDocument = await parseServerDocument(response);
      if (!serverDocument) return true;
      actionDialogChanged = true;
      syncUnexpectedReview(serverDocument, aliasId, senderKey);
      return true;
    } catch (error) {
      console.error("Sender review failed", error);
      if (button) button.disabled = false;
      return false;
    }
  };

  const saveIgnoredAlias = async (form, checkbox) => {
    const payload = new FormData(form);
    checkbox.disabled = true;
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: payload,
        credentials: "same-origin",
      });
      if (response.status === 401) {
        window.location.assign("/");
        return;
      }
      if (!response.ok) throw new Error(`Unexpected monitoring update failed with HTTP ${response.status}`);
      markForReopen();
      window.location.reload();
    } catch (error) {
      console.error("Could not save unexpected sender setting", error);
      checkbox.checked = false;
      checkbox.disabled = false;
    }
  };

  const syncPoolSelection = (row) => {
    const checkbox = row.querySelector("[data-pool-selected]");
    const purpose = row.querySelector("[data-pool-purpose]");
    const label = row.querySelector("[data-pool-selection-label]");
    if (!checkbox || !purpose) return;
    purpose.disabled = !checkbox.checked;
    purpose.required = checkbox.checked;
    row.classList.toggle("skipped", !checkbox.checked);
    if (label) {
      label.textContent = checkbox.checked
        ? (document.documentElement.lang.startsWith("de") ? "Jetzt zuordnen" : "Assign now")
        : (document.documentElement.lang.startsWith("de") ? "Vorerst nicht zuordnen" : "Leave unassigned for now");
    }
  };

  const assignUsedPoolAliases = async (form) => {
    const selected = [...form.querySelectorAll("[data-pool-alias-id]")].filter(
      (row) => row.querySelector("[data-pool-selected]")?.checked,
    );
    if (!selected.length) return;

    for (const row of selected) {
      const purpose = row.querySelector("[data-pool-purpose]");
      if (!purpose?.value.trim()) {
        purpose?.focus();
        return;
      }
    }

    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.disabled = true;
    const csrfToken = document.body.dataset.csrfToken || "";
    try {
      for (const row of selected) {
        const aliasId = row.dataset.poolAliasId;
        const purpose = row.querySelector("[data-pool-purpose]");
        const payload = new FormData();
        payload.append("csrf_token", csrfToken);
        payload.append("description", purpose.value.trim());
        const response = await fetch(`/offline-pool/${encodeURIComponent(aliasId)}/assign`, {
          method: "POST",
          body: payload,
          credentials: "same-origin",
        });
        if (response.status === 401) {
          window.location.assign("/");
          return;
        }
        if (!response.ok) throw new Error(`Offline alias assignment failed with HTTP ${response.status}`);
      }
      markForReopen();
      window.location.reload();
    } catch (error) {
      console.error("Offline alias assignment failed", error);
      if (submit) submit.disabled = false;
    }
  };

  document.addEventListener("click", (event) => {
    const opener = event.target.closest?.("[data-action-required-open]");
    if (opener && openActionDialog()) {
      event.preventDefault();
      return;
    }

    const closer = event.target.closest?.("[data-action-required-close]");
    if (closer && closer.closest("dialog[data-action-required-dialog]")) {
      event.preventDefault();
      closeActionDialog();
    }
  });

  document.addEventListener("submit", async (event) => {
    const senderForm = event.target.closest?.("[data-action-sender-form]");
    if (senderForm) {
      const decision = senderForm.querySelector('input[name="decision"]')?.value;
      if (decision === "expected") {
        event.preventDefault();
        await submitExpectedSender(senderForm);
      } else {
        markForReopen();
      }
      return;
    }

    const poolForm = event.target.closest?.("[data-action-required-pool-form]");
    if (poolForm) {
      event.preventDefault();
      await assignUsedPoolAliases(poolForm);
    }
  });

  document.addEventListener("change", (event) => {
    const poolCheckbox = event.target.closest?.("[data-pool-selected]");
    if (poolCheckbox) {
      const row = poolCheckbox.closest("[data-pool-alias-id]");
      if (row) syncPoolSelection(row);
      return;
    }

    const ignore = event.target.closest?.("[data-action-ignore]");
    if (ignore?.checked) {
      const form = ignore.closest("[data-action-ignore-form]");
      if (form) void saveIgnoredAlias(form, ignore);
    }
  });

  window.MooliasActionRequired = {
    open: openActionDialog,
    summary: async () => getSummary(),
    markForReopen,
  };

  const start = () => {
    const dialog = actionDialog();
    dialog?.addEventListener("cancel", (event) => {
      event.preventDefault();
      closeActionDialog();
    });
    document.querySelectorAll("[data-pool-alias-id]").forEach(syncPoolSelection);
    try {
      if (sessionStorage.getItem(REOPEN_KEY) === "1") {
        sessionStorage.removeItem(REOPEN_KEY);
        openActionDialog();
      }
    } catch (error) {
      console.debug("sessionStorage is unavailable", error);
    }
    document.dispatchEvent(new CustomEvent("moolias:action-required-ready"));
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
