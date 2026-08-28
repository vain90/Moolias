(() => {
  "use strict";

  const LOGIN_AUTO_KEY = "moolias-action-required-after-login";
  let explicitQueryHandled = false;
  let autoLoginHandled = false;

  document.addEventListener("click", (event) => {
    const loginLink = event.target.closest?.('a[href="/login"]');
    if (!loginLink) return;
    try {
      sessionStorage.setItem(LOGIN_AUTO_KEY, "1");
    } catch (error) {
      console.debug("sessionStorage is unavailable", error);
    }
  });

  const handleExplicitQuery = async (api) => {
    if (explicitQueryHandled || !api?.open) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("action") !== "required") return;
    explicitQueryHandled = true;
    api.open();
  };

  const handleFreshLogin = async (api) => {
    if (autoLoginHandled || !api?.open || !api?.summary) return;
    let requested = false;
    try {
      requested = sessionStorage.getItem(LOGIN_AUTO_KEY) === "1";
      if (requested) sessionStorage.removeItem(LOGIN_AUTO_KEY);
    } catch (error) {
      console.debug("sessionStorage is unavailable", error);
    }
    if (!requested) return;

    autoLoginHandled = true;
    const summary = await api.summary();
    if ((summary?.total || 0) > 0) api.open();
  };

  const refresh = async () => {
    const api = window.MooliasActionRequired;
    if (!api) return;
    await handleFreshLogin(api);
    await handleExplicitQuery(api);
  };

  document.addEventListener("moolias:action-required-ready", () => void refresh());

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => void refresh(), { once: true });
  } else {
    void refresh();
  }
})();
