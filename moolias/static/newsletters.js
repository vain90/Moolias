(() => {
  const page = document.querySelector("[data-newsletter-page]");
  if (!page) return;

  const isGerman = document.documentElement.lang === "de";
  const language = isGerman ? "de-DE" : "en-GB";
  const formatter = new Intl.DateTimeFormat(language, {
    dateStyle: "medium",
    timeStyle: "short",
  });

  const labels = isGerman
    ? {
        confirmTitle: "Newsletter abmelden?",
        confirmBody: "Möchtest du diesen Newsletter jetzt per One-Click abmelden?",
        confirm: "Abmelden",
        cancel: "Abbrechen",
        processingTitle: "Newsletter wird abgemeldet",
        processingBody: "Die Abmeldung wird durchgeführt. Das kann einige Sekunden dauern.",
        successTitle: "Abmeldung erfolgreich",
        successBody: "Der Anbieter hat die Abmeldung bestätigt. Der Newsletter wurde als abgemeldet markiert.",
        errorTitle: "Abmeldung nicht möglich",
        errorBody: "Die Abmeldung konnte nicht abgeschlossen werden.",
        errorAdvice: "Öffne eine aktuelle Newsletter-Mail und nutze dort den angebotenen Abmeldelink. Falls der Anbieter trotzdem weiter sendet oder keine Abmeldung möglich ist, kannst du den verwendeten Alias in Moolias deaktivieren oder ersetzen.",
        close: "Schließen",
      }
    : {
        confirmTitle: "Unsubscribe from newsletter?",
        confirmBody: "Do you want to unsubscribe from this newsletter using one-click now?",
        confirm: "Unsubscribe",
        cancel: "Cancel",
        processingTitle: "Unsubscribing",
        processingBody: "The unsubscribe request is being processed. This may take a few seconds.",
        successTitle: "Unsubscribe successful",
        successBody: "The provider confirmed the unsubscribe request. The newsletter has been marked as unsubscribed.",
        errorTitle: "Could not unsubscribe",
        errorBody: "The unsubscribe request could not be completed.",
        errorAdvice: "Open a recent newsletter message and use the unsubscribe link provided there. If the provider still keeps sending or no unsubscribe works, you can disable or replace the alias in Moolias.",
        close: "Close",
      };

  const showProcessingDialog = () => {
    const existing = document.querySelector("[data-newsletter-unsubscribe-processing]");
    if (existing) return existing;

    const dialog = document.createElement("dialog");
    dialog.className = "moolias-dialog moolias-dialog-default newsletter-unsubscribe-processing";
    dialog.dataset.newsletterUnsubscribeProcessing = "1";
    dialog.setAttribute("aria-busy", "true");

    const head = document.createElement("div");
    head.className = "dialog-head";

    const title = document.createElement("h2");
    title.textContent = labels.processingTitle;

    const close = document.createElement("button");
    close.className = "dialog-close";
    close.type = "button";
    close.textContent = "×";
    close.setAttribute("aria-label", labels.close);
    close.title = labels.close;

    head.append(title, close);

    const body = document.createElement("p");
    body.className = "moolias-dialog-message";
    body.setAttribute("role", "status");
    body.textContent = labels.processingBody;

    const progress = document.createElement("progress");
    progress.className = "newsletter-unsubscribe-progress";
    progress.setAttribute("aria-label", labels.processingBody);

    dialog.append(head, body, progress);
    document.body.append(dialog);

    const dismiss = () => {
      if (dialog.open) dialog.close();
      else dialog.remove();
    };
    close.addEventListener("click", dismiss);
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      dismiss();
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dismiss();
    });
    dialog.addEventListener("close", () => dialog.remove(), { once: true });

    dialog.showModal();
    return dialog;
  };

  const cleanupResultQuery = () => {
    const url = new URL(window.location.href);
    url.searchParams.delete("unsubscribed");
    url.searchParams.delete("unsubscribe_error");
    window.history.replaceState({}, "", url.toString());
  };

  const showResultDialog = async (success) => {
    // Keep the server-rendered notice only as a no-JavaScript fallback. With the
    // interactive flow the result belongs in the modal, not above the table.
    const queryNotice = page.querySelector(".newsletter-notice");
    queryNotice?.remove();
    cleanupResultQuery();

    const api = window.MooliasDialog;
    if (!api) return;

    if (success) {
      await api.info({
        title: labels.successTitle,
        message: labels.successBody,
        closeLabel: labels.close,
      });
      return;
    }

    await api.error(`${labels.errorBody} ${labels.errorAdvice}`, {
      title: labels.errorTitle,
      closeLabel: labels.close,
    });
  };

  const currentUrl = new URL(window.location.href);
  if (currentUrl.searchParams.has("unsubscribed")) {
    void showResultDialog(true);
  } else if (currentUrl.searchParams.has("unsubscribe_error")) {
    void showResultDialog(false);
  }

  page.querySelectorAll("[data-newsletter-time]").forEach((element) => {
    const seconds = Number(element.dataset.newsletterTime || "0");
    if (!Number.isFinite(seconds) || seconds <= 0) return;
    const date = new Date(seconds * 1000);
    element.dateTime = date.toISOString();
    element.textContent = formatter.format(date);
  });

  page.querySelectorAll("[data-newsletter-details-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.dataset.newsletterDetailsToggle;
      const details = id ? document.getElementById(id) : null;
      if (!details) return;
      const opening = details.hidden;
      details.hidden = !opening;
      button.setAttribute("aria-expanded", opening ? "true" : "false");
    });
  });

  page.querySelectorAll('form[action^="/newsletters/"][action$="/unsubscribe"]').forEach((form) => {
    // app.js binds generic data-confirm forms before this page-specific script runs.
    // The newsletter handler therefore runs in the capture phase and stops the old
    // listener so the second programmatic submit cannot be blocked by a stale confirm.
    form.removeAttribute("data-confirm");

    form.addEventListener("submit", async (event) => {
      if (form.dataset.newsletterProcessingSubmit === "1") {
        delete form.dataset.newsletterProcessingSubmit;
        event.stopImmediatePropagation();
        return;
      }

      event.preventDefault();
      event.stopImmediatePropagation();
      const api = window.MooliasDialog;
      if (!api) return;
      const submitter = event.submitter;
      const accepted = await api.confirm({
        title: labels.confirmTitle,
        message: labels.confirmBody,
        confirmLabel: labels.confirm,
        cancelLabel: labels.cancel,
        tone: "danger",
        dismissOnBackdrop: false,
      });
      if (!accepted) return;

      showProcessingDialog();
      form.dataset.newsletterProcessingSubmit = "1";
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => form.requestSubmit(submitter || undefined));
      });
    }, true);
  });

  const search = page.querySelector("[data-newsletter-search]");
  const clear = page.querySelector("[data-newsletter-search-clear]");
  let searchTimer = null;

  const navigateSearch = (value) => {
    const url = new URL(window.location.href);
    const query = value.trim();
    if (query) url.searchParams.set("q", query);
    else url.searchParams.delete("q");
    url.searchParams.delete("page");
    window.location.assign(url.toString());
  };

  if (search) {
    search.addEventListener("input", () => {
      if (clear) clear.hidden = !search.value;
      if (searchTimer) window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => navigateSearch(search.value), 350);
    });

    search.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      if (searchTimer) window.clearTimeout(searchTimer);
      navigateSearch(search.value);
    });
  }

  clear?.addEventListener("click", () => {
    if (searchTimer) window.clearTimeout(searchTimer);
    if (search) search.value = "";
    clear.hidden = true;
    navigateSearch("");
  });

  page.querySelectorAll("[data-newsletter-page-size]").forEach((select) => {
    select.addEventListener("change", () => select.form?.submit());
  });
})();
