(() => {
  "use strict";

  const forms = Array.from(document.querySelectorAll("[data-alias-wait-form]"));
  if (!forms.length) return;

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
          : []
      );
      for (const form of forms) {
        const address = String(form.dataset.address || "").toLowerCase();
        updateForm(form, active.has(address));
      }
    } catch (_) {
      // The form itself remains fully functional without the status enhancement.
    }
  };

  void refresh();
})();
