(() => {
  const page = document.querySelector("[data-newsletter-page]");
  if (!page) return;

  const language = document.documentElement.lang === "de" ? "de-DE" : "en-GB";
  const formatter = new Intl.DateTimeFormat(language, {
    dateStyle: "medium",
    timeStyle: "short",
  });

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

  page.querySelectorAll("[data-newsletter-unsubscribe-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const message = document.documentElement.lang === "de"
        ? "Diesen Newsletter jetzt direkt abmelden?"
        : "Unsubscribe from this newsletter now?";
      if (!window.confirm(message)) event.preventDefault();
    });
  });
})();
