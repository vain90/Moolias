(() => {
  "use strict";

  function ensureServiceIconPicker() {
    if (!document.querySelector("[data-alias-icon-select]")) return;
    if (document.querySelector("[data-icon-picker-trigger]")) return;

    if (!document.querySelector("link[data-service-icon-picker-styles]")) {
      const stylesheet = document.createElement("link");
      stylesheet.rel = "stylesheet";
      stylesheet.href = "/static/service-icon-picker.css?v=20260822-3";
      stylesheet.dataset.serviceIconPickerStyles = "";
      document.head.append(stylesheet);
    }

    if (!document.querySelector("script[data-service-icon-picker-script]")) {
      const script = document.createElement("script");
      script.src = "/static/service-icon-picker.js?v=20260822-3";
      script.dataset.serviceIconPickerScript = "";
      document.body.append(script);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ensureServiceIconPicker, { once: true });
  } else {
    ensureServiceIconPicker();
  }

  function showDialog(dialog) {
    if (!dialog || dialog.matches(":modal")) return;
    if (dialog.hasAttribute("open")) dialog.close();
    dialog.showModal();
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
  if (workflowDialog?.hasAttribute("open")) showDialog(workflowDialog);
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
        if (workflow.state !== workflowDialog.dataset.aliasWorkflowState) {
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
