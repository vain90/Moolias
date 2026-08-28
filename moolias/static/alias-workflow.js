(() => {
  "use strict";

  function showDialog(dialog) {
    if (!dialog || dialog.matches(":modal")) return;
    if (dialog.hasAttribute("open")) dialog.close();
    dialog.showModal();
  }

  function clearAliasDialogParam(name) {
    if (window.location.pathname !== "/aliases") return;
    const url = new URL(window.location.href);
    if (!url.searchParams.has(name)) return;
    url.searchParams.delete(name);
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }

  async function fetchRenderedPage(url) {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "text/html" },
    });
    if (!response.ok) {
      throw new Error(`Could not load dialog: HTTP ${response.status}`);
    }
    const html = await response.text();
    return new DOMParser().parseFromString(html, "text/html");
  }

  function installRenderedDialog(renderedPage, selector, bindDialog) {
    const nextDialog = renderedPage.querySelector(selector);
    if (!nextDialog) {
      throw new Error(`Rendered dialog not found: ${selector}`);
    }

    const currentDialog = document.querySelector(selector);
    if (currentDialog) {
      if (currentDialog.matches(":modal")) {
        currentDialog.dataset.refreshing = "1";
        currentDialog.close();
      }
      currentDialog.replaceWith(nextDialog);
    } else {
      document.body.append(nextDialog);
    }

    showDialog(nextDialog);
    bindDialog(nextDialog);
    return nextDialog;
  }

  async function openRenderedDialog(trigger, selector, bindDialog) {
    const href = trigger.getAttribute("href");
    if (!href) return;

    trigger.setAttribute("aria-busy", "true");
    try {
      const renderedPage = await fetchRenderedPage(href);
      installRenderedDialog(renderedPage, selector, bindDialog);
    } catch (error) {
      console.debug("Could not open server-rendered alias dialog", error);
      window.location.assign(href);
    } finally {
      trigger.removeAttribute("aria-busy");
    }
  }

  function workflowPageUrl(workflowId) {
    const url = new URL(window.location.href);
    url.pathname = "/aliases";
    url.searchParams.delete("create");
    url.searchParams.delete("replace");
    url.searchParams.delete("deactivate");
    url.searchParams.set("workflow", workflowId);
    return `${url.pathname}${url.search}${url.hash}`;
  }

  function bindWorkflowCopyButtons(dialog) {
    dialog.querySelectorAll("[data-alias-workflow-copy]").forEach((button) => {
      if (button.dataset.workflowCopyBound === "1") return;
      button.dataset.workflowCopyBound = "1";
      button.addEventListener("click", async () => {
        const address = button.dataset.aliasWorkflowCopy || "";
        if (!address) return;
        await navigator.clipboard.writeText(address);
        const original = button.dataset.copyLabel || button.textContent;
        button.textContent = button.dataset.copiedLabel || original;
        window.setTimeout(() => {
          button.textContent = original;
        }, 1200);
      });
    });
  }

  function bindWorkflowDialog(dialog) {
    if (!dialog || dialog.dataset.workflowDialogBound === "1") return;
    dialog.dataset.workflowDialogBound = "1";
    bindWorkflowCopyButtons(dialog);

    dialog.querySelectorAll(".dialog-close, [data-alias-workflow-done]").forEach((control) => {
      control.addEventListener("click", (event) => {
        event.preventDefault();
        dialog.close();
      });
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener("close", () => {
      if (dialog.dataset.refreshing === "1") {
        delete dialog.dataset.refreshing;
        return;
      }
      clearAliasDialogParam("workflow");
    });

    const workflowId = dialog.dataset.aliasWorkflowId;
    const pollMs = Number.parseInt(dialog.dataset.aliasWorkflowPollMs || "0", 10);
    if (!workflowId || !Number.isFinite(pollMs) || pollMs <= 0) return;

    let polling = false;
    const timer = window.setInterval(async () => {
      if (!dialog.isConnected) {
        window.clearInterval(timer);
        return;
      }
      if (polling || document.hidden || !dialog.matches(":modal")) return;
      polling = true;
      try {
        const response = await fetch(`/aliases/workflows/${workflowId}`, {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) return;
        const workflow = await response.json();
        if (workflow.state === dialog.dataset.aliasWorkflowState) return;

        const renderedPage = await fetchRenderedPage(workflowPageUrl(workflowId));
        installRenderedDialog(
          renderedPage,
          `[data-alias-workflow-dialog][data-alias-workflow-id="${CSS.escape(workflowId)}"]`,
          bindWorkflowDialog,
        );
      } catch (error) {
        console.debug("Could not refresh alias workflow state", error);
      } finally {
        polling = false;
      }
    }, pollMs);
  }

  function bindReplacementDeactivationDialog(dialog) {
    if (!dialog || dialog.dataset.replacementDeactivationBound === "1") return;
    dialog.dataset.replacementDeactivationBound = "1";

    dialog.querySelectorAll('.dialog-close, .alias-replacement-cancel-form a[href="/aliases"]').forEach(
      (control) => {
        control.addEventListener("click", (event) => {
          event.preventDefault();
          dialog.close();
        });
      },
    );
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener("close", () => clearAliasDialogParam("deactivate"));
  }

  const createDialog = document.querySelector("[data-create-alias-dialog]");
  if (createDialog?.hasAttribute("open")) showDialog(createDialog);
  document.querySelector("[data-open-create-alias]")?.addEventListener("click", (event) => {
    if (!createDialog) return;
    event.preventDefault();
    showDialog(createDialog);
    createDialog.querySelector('input[name="description"]')?.focus();
  });
  createDialog?.querySelector("[data-close-create-alias]")?.addEventListener("click", (event) => {
    event.preventDefault();
    createDialog.close();
  });
  createDialog?.addEventListener("click", (event) => {
    if (event.target === createDialog) createDialog.close();
  });

  const createForm = createDialog?.querySelector("[data-alias-create-form]");
  const createLoadingDialog = document.querySelector("[data-alias-create-loading-dialog]");
  createForm?.addEventListener("submit", (event) => {
    if (createForm.dataset.submitting === "1") {
      event.preventDefault();
      return;
    }
    createForm.dataset.submitting = "1";
    const submitButton = event.submitter || createForm.querySelector('button[type="submit"]');
    if (submitButton) submitButton.disabled = true;
    showDialog(createLoadingDialog);
  });

  const replacementDialog = document.querySelector("[data-alias-replacement-dialog]");
  if (replacementDialog?.hasAttribute("open")) showDialog(replacementDialog);
  const replacementForm = replacementDialog?.querySelector("[data-alias-replacement-form]");
  const replacementOldAddress = replacementDialog?.querySelector("[data-alias-replacement-old-address]");
  const replacementDomain = replacementDialog?.querySelector("[data-alias-replacement-domain]");
  const replacementCustom = replacementDialog?.querySelector("[data-alias-replacement-custom]");
  const replacementModes = [...(replacementDialog?.querySelectorAll("[data-alias-replacement-mode]") || [])];

  function syncReplacementMode() {
    if (!replacementCustom) return;
    const selected = replacementModes.find((option) => option.checked)?.value;
    replacementCustom.classList.toggle("hidden", selected !== "custom");
  }

  function openReplacement(aliasId, address, editDetails = null) {
    if (!aliasId) return;
    if (!replacementDialog || !replacementForm) {
      window.location.assign(`/aliases?replace=${encodeURIComponent(aliasId)}`);
      return;
    }
    if (!address) return;
    const domain = address.includes("@") ? address.split("@").slice(1).join("@") : "";
    if (!domain) return;

    replacementForm.action = `/aliases/${aliasId}/replace`;
    if (replacementOldAddress) replacementOldAddress.textContent = address;
    if (replacementDomain) replacementDomain.textContent = `@${domain}`;
    const localPart = replacementForm.querySelector('input[name="local_part"]');
    if (localPart) localPart.value = "";
    const named = replacementModes.find((option) => option.value === "named");
    if (named) named.checked = true;
    syncReplacementMode();
    editDetails?.removeAttribute("open");
    showDialog(replacementDialog);
  }

  replacementModes.forEach((option) => option.addEventListener("change", syncReplacementMode));
  syncReplacementMode();

  window.showReplacementDialog = (aliasSelect, editDetails = null) => {
    openReplacement(aliasSelect?.value, aliasSelect?.dataset.address || "", editDetails);
  };

  document.addEventListener("click", (event) => {
    const workflowTrigger = event.target.closest?.("[data-open-alias-workflow]");
    if (workflowTrigger) {
      const workflowId = workflowTrigger.dataset.openAliasWorkflow;
      if (!workflowId) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      workflowTrigger.closest("details.alias-edit-action")?.removeAttribute("open");
      openRenderedDialog(
        workflowTrigger,
        `[data-alias-workflow-dialog][data-alias-workflow-id="${CSS.escape(workflowId)}"]`,
        bindWorkflowDialog,
      );
      return;
    }

    const deactivationTrigger = event.target.closest?.(
      "[data-open-replacement-deactivation], [data-alias-workflow-cancel]",
    );
    if (deactivationTrigger) {
      event.preventDefault();
      event.stopImmediatePropagation();
      deactivationTrigger.closest("details.alias-edit-action")?.removeAttribute("open");
      const sourceWorkflow = deactivationTrigger.closest("dialog[data-alias-workflow-dialog]");
      if (sourceWorkflow?.matches(":modal")) sourceWorkflow.close();
      openRenderedDialog(
        deactivationTrigger,
        "[data-replacement-deactivation-dialog]",
        bindReplacementDeactivationDialog,
      );
      return;
    }

    const trigger = event.target.closest?.("[data-alias-workflow-replace]");
    if (!trigger) return;

    const aliasId = trigger.dataset.aliasWorkflowReplace;
    const address = trigger.dataset.aliasWorkflowAddress || "";
    if (!aliasId || !address) return;

    event.preventDefault();
    event.stopImmediatePropagation();
    openReplacement(aliasId, address, trigger.closest("details.alias-edit-action"));
  }, true);

  replacementDialog?.querySelectorAll("[data-close-alias-replacement]").forEach((control) => {
    control.addEventListener("click", (event) => {
      event.preventDefault();
      replacementDialog.close();
    });
  });
  replacementDialog?.addEventListener("click", (event) => {
    if (event.target === replacementDialog) replacementDialog.close();
  });

  const replacementDeactivationDialog = document.querySelector(
    "[data-replacement-deactivation-dialog]",
  );
  if (replacementDeactivationDialog?.hasAttribute("open")) {
    showDialog(replacementDeactivationDialog);
  }
  bindReplacementDeactivationDialog(replacementDeactivationDialog);

  const workflowDialog = document.querySelector("[data-alias-workflow-dialog]");
  if (workflowDialog?.hasAttribute("open")) showDialog(workflowDialog);
  bindWorkflowDialog(workflowDialog);
})();