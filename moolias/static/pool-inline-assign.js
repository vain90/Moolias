(() => {
  "use strict";

  const german = (document.documentElement.lang || "").toLowerCase().startsWith("de");
  const fieldLabel = german ? "Alias Name" : "Alias name";

  document.querySelectorAll(".offline-pool-row [data-open-assign-dialog]").forEach((button) => {
    const aliasId = button.dataset.openAssignDialog;
    if (!aliasId) return;

    const dialog = document.querySelector(
      `[data-assign-dialog="${CSS.escape(aliasId)}"]`,
    );
    const sourceForm = dialog?.querySelector("form");
    if (!sourceForm) return;

    const details = document.createElement("details");
    details.className = "pool-assign-action";
    details.dataset.poolInlineAssign = aliasId;

    const summary = document.createElement("summary");
    summary.className = button.className;
    summary.textContent = button.textContent.trim();
    summary.setAttribute("aria-label", button.textContent.trim());

    const panel = document.createElement("div");
    panel.className = "edit-panel";

    const form = sourceForm.cloneNode(true);
    form.classList.add("small");
    const description = form.querySelector('input[name="description"]');
    const label = description?.closest("label");
    if (label) {
      [...label.childNodes]
        .filter((node) => node.nodeType === Node.TEXT_NODE)
        .forEach((node) => node.remove());
      const caption = document.createElement("span");
      caption.dataset.fieldCaption = "1";
      caption.textContent = fieldLabel;
      label.prepend(caption);
    }

    const submit = form.querySelector('button[type="submit"]');
    submit?.classList.add("compact");

    panel.append(form);
    details.append(summary, panel);
    button.replaceWith(details);

    details.addEventListener("toggle", () => {
      if (details.open) {
        window.requestAnimationFrame(() => description?.focus());
      }
    });
  });
})();
