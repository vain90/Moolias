(() => {
  "use strict";

  const language = document.documentElement.lang?.toLowerCase().startsWith("de") ? "de" : "en";
  const text = language === "de"
    ? {
        actionRequired: "Handlungsbedarf",
        actionRequiredCount: (count) => `Handlungsbedarf (${count})`,
        loading: "Handlungsbedarf wird geladen …",
      }
    : {
        actionRequired: "Action required",
        actionRequiredCount: (count) => `Action required (${count})`,
        loading: "Loading action-required items …",
      };

  const LOGIN_AUTO_KEY = "moolias-action-required-after-login";
  let explicitQueryHandled = false;
  let autoLoginHandled = false;
  let poolSourcePromise = null;

  document.addEventListener("click", (event) => {
    const loginLink = event.target.closest?.('a[href="/login"]');
    if (!loginLink) return;
    try {
      sessionStorage.setItem(LOGIN_AUTO_KEY, "1");
    } catch (error) {
      console.debug("sessionStorage is unavailable", error);
    }
  });

  const ensureAliasAction = () => {
    const filters = document.querySelector(".status-filters");
    if (!filters) return null;

    let actions = document.querySelector("[data-unexpected-review-actions]");
    if (!actions) {
      actions = document.createElement("div");
      actions.className = "unexpected-review-actions action-required-actions";
      actions.dataset.unexpectedReviewActions = "1";

      const button = document.createElement("button");
      button.type = "button";
      button.className = "button compact unexpected-review-all-button action-required-button";
      button.dataset.unexpectedReviewAll = "1";
      button.dataset.actionRequiredOpen = "1";
      button.textContent = text.actionRequired;
      actions.append(button);
      filters.insertAdjacentElement("beforebegin", actions);
    }
    return actions.querySelector("[data-action-required-open]");
  };

  const ensureOfflinePoolSource = async () => {
    if (document.querySelector(".pool-item")) return;
    if (document.querySelector("[data-action-required-pool-source]")) return;
    if (poolSourcePromise) return poolSourcePromise;

    poolSourcePromise = (async () => {
      try {
        const response = await fetch("/offline-pool", {
          headers: { Accept: "text/html" },
          credentials: "same-origin",
        });
        if (response.status === 401) {
          window.location.assign("/");
          return;
        }
        if (!response.ok) return;

        const sourceDocument = new DOMParser().parseFromString(
          await response.text(),
          "text/html",
        );
        const usedItems = [...sourceDocument.querySelectorAll(".pool-item.pool-item-used")];
        if (!usedItems.length) return;

        const source = document.createElement("div");
        source.hidden = true;
        source.dataset.actionRequiredPoolSource = "1";

        usedItems.forEach((item) => {
          const importedItem = document.importNode(item, true);
          source.append(importedItem);

          const aliasId = item.querySelector("[data-open-assign-dialog]")?.dataset.openAssignDialog;
          if (!aliasId) return;
          const dialog = sourceDocument.querySelector(
            `[data-assign-dialog="${CSS.escape(aliasId)}"]`,
          );
          if (dialog) source.append(document.importNode(dialog, true));
        });

        document.body.append(source);
      } catch (error) {
        console.error("Could not preload offline aliases for action required", error);
      }
    })();

    try {
      await poolSourcePromise;
    } finally {
      poolSourcePromise = null;
    }
  };

  const showActionLoadingState = (dialog) => {
    const content = dialog?.querySelector(".action-required-content");
    if (!content) return;

    const status = document.createElement("p");
    status.className = "muted action-required-loading";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.textContent = text.loading;

    const progress = document.createElement("progress");
    progress.className = "action-required-progress";
    progress.setAttribute("aria-label", text.loading);
    progress.style.width = "100%";

    content.replaceChildren(status, progress);
  };

  const openActionRequired = async () => {
    const api = window.MooliasActionRequired;
    if (!api?.open) return;

    const poolPromise = ensureOfflinePoolSource();
    const renderPromise = api.open();
    const dialog = document.querySelector("dialog[data-action-required-dialog]");

    showActionLoadingState(dialog);
    if (dialog && !dialog.open) dialog.showModal();

    await Promise.all([poolPromise, renderPromise]);

    const hasUsedPoolItem = Boolean(document.querySelector(".pool-item.pool-item-used"));
    if (hasUsedPoolItem && dialog && !dialog.querySelector(".action-required-pool-form")) {
      const rerenderPromise = api.open();
      showActionLoadingState(dialog);
      await rerenderPromise;
    }
  };

  const bindActionButtons = () => {
    document.querySelectorAll("[data-action-required-open]").forEach((button) => {
      if (button.dataset.actionRequiredBound === "1") return;
      button.dataset.actionRequiredBound = "1";
      button.addEventListener("click", openActionRequired);
      button.addEventListener("pointerenter", () => void ensureOfflinePoolSource(), { once: true });
      button.addEventListener("focus", () => void ensureOfflinePoolSource(), { once: true });
    });
  };

  const handleExplicitQuery = async (api) => {
    if (explicitQueryHandled || !api?.open) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("action") !== "required") return;

    explicitQueryHandled = true;
    await openActionRequired();
    params.delete("action");
    const query = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
  };

  const overviewActionCount = () => {
    const value = document.querySelector("[data-action-count]")?.textContent?.trim();
    if (value === undefined) return null;
    const count = Number.parseInt(value, 10);
    return Number.isFinite(count) ? count : null;
  };

  const handleFreshLogin = async (api, summary) => {
    if (autoLoginHandled || !api?.open) return;
    let requested = false;
    try {
      requested = sessionStorage.getItem(LOGIN_AUTO_KEY) === "1";
      if (requested) sessionStorage.removeItem(LOGIN_AUTO_KEY);
    } catch (error) {
      console.debug("sessionStorage is unavailable", error);
    }
    if (!requested) return;
    autoLoginHandled = true;
    const total = overviewActionCount() ?? summary?.total ?? 0;
    if (total > 0) await openActionRequired();
  };

  const refresh = async () => {
    const aliasAction = ensureAliasAction();
    bindActionButtons();
    const api = window.MooliasActionRequired;
    if (!api) return;

    let summary = null;
    if (api.summary) {
      summary = await api.summary();
      if (aliasAction) {
        aliasAction.textContent = summary.total > 0
          ? text.actionRequiredCount(summary.total)
          : text.actionRequired;
        aliasAction.classList.toggle("has-action-required", summary.total > 0);
      }
    }

    await handleFreshLogin(api, summary);
    await handleExplicitQuery(api);
  };

  const start = () => {
    ensureAliasAction();
    bindActionButtons();
    if (document.body.classList.contains("app-body")) refresh();

    const observer = new MutationObserver(() => {
      ensureAliasAction();
      bindActionButtons();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener("moolias:action-required-ready", refresh);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
