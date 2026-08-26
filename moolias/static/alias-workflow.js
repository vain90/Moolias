(() => {
  "use strict";

  function showDialog(dialog) {
    if (!dialog) return;
    if (dialog.hasAttribute("open")) return;
    dialog.showModal();
  }

  const createDialog = document.querySelector("[data-create-alias-dialog]");
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

  const replacementDialog = document.querySelector("[data-alias-replacement-dialog]");
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

  replacementModes.forEach((option) => option.addEventListener("change", syncReplacementMode));
  syncReplacementMode();

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest?.("[data-alias-workflow-replace]");
    if (!trigger || !replacementDialog || !replacementForm) return;

    const aliasId = trigger.dataset.aliasWorkflowReplace;
    const address = trigger.dataset.aliasWorkflowAddress || "";
    const domain = address.includes("@") ? address.split("@").slice(1).join("@") : "";
    if (!aliasId || !address || !domain) return;

    event.preventDefault();
    event.stopImmediatePropagation();
    replacementForm.action = `/aliases/${aliasId}/replace`;
    if (replacementOldAddress) replacementOldAddress.textContent = address;
    if (replacementDomain) replacementDomain.textContent = `@${domain}`;
    replacementForm.querySelector('input[name="local_part"]')?.value = "";
    const named = replacementModes.find((option) => option.value === "named");
    if (named) named.checked = true;
    syncReplacementMode();
    trigger.closest("details.alias-edit-action")?.removeAttribute("open");
    showDialog(replacementDialog);
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

  document.querySelectorAll("[data-alias-workflow-copy]").forEach((button) => {
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

  const workflowDialog = document.querySelector("[data-alias-workflow-dialog]");
  const workflowId = workflowDialog?.dataset.aliasWorkflowId;
  const pollMs = Number.parseInt(workflowDialog?.dataset.aliasWorkflowPollMs || "0", 10);
  if (workflowDialog && workflowId && Number.isFinite(pollMs) && pollMs > 0) {
    let polling = false;
    window.setInterval(async () => {
      if (polling || document.hidden) return;
      polling = true;
      try {
        const response = await fetch(`/aliases/workflows/${workflowId}`, {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) return;
        const workflow = await response.json();
        if (
          workflow.state !== workflowDialog.dataset.aliasWorkflowState
          || String(Boolean(workflow.completed)) !== workflowDialog.dataset.aliasWorkflowCompleted
        ) {
          window.location.reload();
        }
      } catch (error) {
        console.debug("Could not refresh alias workflow state", error);
      } finally {
        polling = false;
      }
    }, pollMs);
  }
})();
