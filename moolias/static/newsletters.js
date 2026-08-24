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
