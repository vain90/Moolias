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
        processingTitle: "Newsletter wird abgemeldet",
        processingBody: "Moolias führt die direkte One-Click-Abmeldung durch und probiert bei Bedarf die gespeicherten Links nacheinander. Das kann einige Sekunden dauern.",
        successTitle: "Abmeldung erfolgreich",
        successBody: "Der Anbieter hat die direkte Abmeldung erfolgreich angenommen. Der Newsletter wurde als abgemeldet markiert.",
        errorTitle: "Abmeldung nicht möglich",
        errorBody: "Die direkte One-Click-Abmeldung konnte mit keinem der gespeicherten Links abgeschlossen werden.",
        errorAdvice: "Öffne eine aktuelle Newsletter-Mail und nutze dort den angebotenen Abmeldelink. Falls der Anbieter trotzdem weiter sendet oder keine Abmeldung möglich ist, kannst du den verwendeten Alias in Moolias deaktivieren oder ersetzen.",
        close: "Schließen",
      }
    : {
        processingTitle: "Unsubscribing",
        processingBody: "Moolias is performing the direct one-click unsubscribe and will try the stored links in order if needed. This may take a few seconds.",
        successTitle: "Unsubscribe successful",
        successBody: "The provider accepted the direct unsubscribe request. The newsletter has been marked as unsubscribed.",
        errorTitle: "Could not unsubscribe",
        errorBody: "The direct one-click unsubscribe could not be completed with any of the stored links.",
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

    const title = document.createElement("h2");
    title.textContent = labels.processingTitle;

    const body = document.createElement("p");
    body.className = "moolias-dialog-message";
    body.setAttribute("role", "status");
    body.textContent = labels.processingBody;

    const progress = document.createElement("progress");
    progress.className = "newsletter-unsubscribe-progress";
    progress.setAttribute("aria-label", labels.processingBody);

    dialog.append(title, body, progress);
    document.body.append(dialog);
    dialog.addEventListener("cancel", (event) => event.preventDefault());
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
    // The server-rendered notice is retained as a no-JavaScript fallback. Once the
    // interactive dialog is available it should not appear above the table as well.
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

    await api.error(`${labels.errorBody}\n\n${labels.errorAdvice}`, {
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
    form.addEventListener("submit", (event) => {
      if (form.dataset.newsletterProcessingSubmit === "1") {
        delete form.dataset.newsletterProcessingSubmit;
        return;
      }

      // The global Moolias confirmation handler runs in capture phase first. This
      // listener is reached only after the user has confirmed and the form is
      // resubmitted. Defer the final submit by two frames so the progress dialog is
      // visibly painted before navigation starts.
      event.preventDefault();
      const submitter = event.submitter;
      showProcessingDialog();
      form.dataset.mooliasConfirmed = "1";
      form.dataset.newsletterProcessingSubmit = "1";
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => form.requestSubmit(submitter || undefined));
      });
    });
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
