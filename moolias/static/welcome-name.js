(() => {
  "use strict";

  const target = document.querySelector("[data-welcome-name]");
  if (!target) return;

  fetch("/account/profile", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  })
    .then((response) => (response.ok ? response.json() : null))
    .then((payload) => {
      const name = String(payload?.welcome_name || "").trim();
      if (name) target.textContent = `, ${name}`;
    })
    .catch((error) => {
      console.debug("Could not load Mailcow welcome name", error);
    });
})();
