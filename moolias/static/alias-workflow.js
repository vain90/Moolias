(() => {
  "use strict";

  function showDialog(dialog) {
    if (!dialog || dialog.matches(":modal")) return;
    if (dialog.hasAttribute("open")) dialog.removeAttribute("open");
    dialog.showModal();
  }

  function clearAliasDialogParam(name) {
    if (window.location.pathname !== "/aliases") return;
    const url = new URL(window.location.href);
    if (!url.searchParams.has(name)) return;
    url.searchParams.delete(name);
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
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
    dialog.addEventListener("close", () => clearAliasDialogParam("workflow"));

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
        window.clearInterval(timer);
        window.location.reload();
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
  createDialog?.addEventListener("close", () => clearAliasDialogParam("create"));

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
  const replacementCustom = replacementDialog?.querySelector("[data-alias-replacement-custom]");
  const replacementModes = [
    ...(replacementDialog?.querySelectorAll("[data-alias-replacement-mode]") || []),
  ];

  function syncReplacementMode() {
    if (!replacementCustom) return;
    const selected = replacementModes.find((option) => option.checked)?.value;
    replacementCustom.classList.toggle("hidden", selected !== "custom");
  }

  replacementModes.forEach((option) => option.addEventListener("change", syncReplacementMode));
  syncReplacementMode();

  replacementDialog?.querySelectorAll("[data-close-alias-replacement]").forEach((control) => {
    control.addEventListener("click", (event) => {
      event.preventDefault();
      replacementDialog.close();
    });
  });
  replacementDialog?.addEventListener("click", (event) => {
    if (event.target === replacementDialog) replacementDialog.close();
  });
  replacementDialog?.addEventListener("close", () => clearAliasDialogParam("replace"));

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
