(() => {
  "use strict";

  function showDialog(dialog) {
    if (!dialog || dialog.matches(":modal")) return;
    if (dialog.hasAttribute("open")) dialog.removeAttribute("open");
    dialog.showModal();
  }

  function clearAliasDialogParam(name) {
    if (window.location.pathname !== "/aliases") return;
    const url = new URL(window.location.href);
    if (!url.searchParams.has(name)) return;
    url.searchParams.delete(name);
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }

  async function fetchRenderedPage(url) {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "text/html" },
    });
    if (!response.ok) {
      throw new Error(`Could not load dialog: HTTP ${response.status}`);
    }
    const html = await response.text();
    return new DOMParser().parseFromString(html, "text/html");
  }

  let aliasResultsController = null;
  let aliasSearchTimer = null;

  function aliasRelativeUrl(url) {
    return `${url.pathname}${url.search}${url.hash}`;
  }

  function syncAliasSearchClear() {
    const search = document.querySelector("[data-live-search]");
    const clear = document.querySelector("[data-search-clear]");
    if (!search || !clear) return;
    clear.hidden = search.value.length === 0;
  }

  function syncAliasSortHeader(url) {
    let activeSort = url.searchParams.get("sort") || "attention";
    if (activeSort === "most_used") activeSort = "usage";
    const activeDirection = url.searchParams.get("direction") === "asc" ? "asc" : "desc";

    document.querySelectorAll(".alias-table-head .alias-sort-link").forEach((link) => {
      const linkUrl = new URL(link.href, window.location.href);
      let key = linkUrl.searchParams.get("sort") || "";
      if (key === "most_used") key = "usage";
      if (!key) return;

      const defaultDirection = key === "purpose" || key === "status" ? "asc" : "desc";
      const isActive = activeSort === key;
      const nextDirection = isActive
        ? (activeDirection === "asc" ? "desc" : "asc")
        : defaultDirection;
      const nextUrl = new URL(url);
      nextUrl.searchParams.set("sort", key);
      nextUrl.searchParams.set("direction", nextDirection);
      nextUrl.searchParams.delete("page");
      link.href = aliasRelativeUrl(nextUrl);
      link.classList.toggle("current", isActive);

      const arrow = link.querySelector(".alias-sort-arrow");
      if (arrow) {
        arrow.textContent = isActive ? (activeDirection === "asc" ? "↑" : "↓") : "↕";
      }

      const column = link.closest('[role="columnheader"]');
      if (isActive) {
        column?.setAttribute(
          "aria-sort",
          activeDirection === "asc" ? "ascending" : "descending",
        );
      } else {
        column?.removeAttribute("aria-sort");
      }
    });
  }

  function syncAliasSortControls(renderedPage) {
    const currentForm = document.querySelector(".sort-controls");
    const nextForm = renderedPage.querySelector(".sort-controls");
    if (!currentForm || !nextForm) return;

    currentForm.querySelectorAll("[name]").forEach((control) => {
      const name = control.getAttribute("name");
      if (!name) return;
      const nextControl = nextForm.querySelector(`[name="${CSS.escape(name)}"]`);
      if (nextControl && "value" in control && "value" in nextControl) {
        control.value = nextControl.value;
      }
    });
  }

  function installRenderedAliasResults(renderedPage, url, keepSearchValue = true) {
    const currentRegion = document.querySelector("[data-alias-results-region]");
    const nextRegion = renderedPage.querySelector("[data-alias-results-region]");
    if (!currentRegion || !nextRegion) {
      throw new Error("Rendered alias results were not found");
    }

    const currentHead = currentRegion.querySelector(".alias-table-head");
    const nextHead = nextRegion.querySelector(".alias-table-head");
    if (currentHead?.querySelector(".alias-sort-link") && nextHead) {
      nextHead.replaceWith(currentHead);
    }

    currentRegion.replaceChildren(...nextRegion.childNodes);

    const currentFilters = document.querySelector(".status-filters");
    const nextFilters = renderedPage.querySelector(".status-filters");
    if (currentFilters && nextFilters) {
      currentFilters.replaceWith(nextFilters);
    }

    const currentSummary = document.querySelector("[data-assigned-summary]");
    const nextSummary = renderedPage.querySelector("[data-assigned-summary]");
    if (currentSummary && nextSummary) {
      currentSummary.replaceWith(nextSummary);
    }

    const currentSearch = document.querySelector("[data-live-search]");
    const nextSearch = renderedPage.querySelector("[data-live-search]");
    if (currentSearch && nextSearch) {
      currentSearch.dataset.status = nextSearch.dataset.status || "all";
      currentSearch.dataset.perPage = nextSearch.dataset.perPage || "25";
      if (!keepSearchValue) currentSearch.value = nextSearch.value;
    }

    syncAliasSortControls(renderedPage);
    syncAliasSortHeader(url);
    syncAliasSearchClear();
    if (typeof window.bindDynamicControls === "function") {
      window.bindDynamicControls(currentRegion);
    }
  }

  function setAliasHistory(url, mode) {
    if (mode === "push") {
      window.history.pushState(null, "", aliasRelativeUrl(url));
    } else if (mode === "replace") {
      window.history.replaceState(null, "", aliasRelativeUrl(url));
    }
  }

  async function refreshAliasResults(
    url,
    {
      historyMode = "replace",
      fallbackToNavigation = false,
      keepSearchValue = true,
    } = {},
  ) {
    const target = new URL(url, window.location.href);
    const search = document.querySelector("[data-live-search]");
    const region = document.querySelector("[data-alias-results-region]");

    aliasResultsController?.abort();
    const controller = new AbortController();
    aliasResultsController = controller;
    search?.classList.add("searching");
    region?.setAttribute("aria-busy", "true");

    try {
      const response = await fetch(target, {
        credentials: "same-origin",
        headers: {
          Accept: "text/html",
          "X-Moolias-Partial": "alias-results",
        },
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(`Could not refresh aliases: HTTP ${response.status}`);
      }

      const html = await response.text();
      const renderedPage = new DOMParser().parseFromString(html, "text/html");
      setAliasHistory(target, historyMode);
      installRenderedAliasResults(renderedPage, target, keepSearchValue);
      return true;
    } catch (error) {
      if (error.name === "AbortError") return false;
      console.debug("Could not refresh server-rendered alias results", error);
      if (fallbackToNavigation) {
        window.location.assign(aliasRelativeUrl(target));
      }
      return false;
    } finally {
      if (aliasResultsController === controller) aliasResultsController = null;
      search?.classList.remove("searching");
      region?.removeAttribute("aria-busy");
    }
  }

  function aliasSearchUrl() {
    const search = document.querySelector("[data-live-search]");
    const url = new URL(window.location.href);
    if (!search) return url;

    const rawQuery = search.value.trim();
    const activeQuery = rawQuery.length >= 2 ? rawQuery : "";
    url.searchParams.set("status", search.dataset.status || "all");
    url.searchParams.set("per_page", search.dataset.perPage || "25");
    url.searchParams.set("page", "1");
    if (activeQuery) {
      url.searchParams.set("q", activeQuery);
    } else {
      url.searchParams.delete("q");
    }
    return url;
  }

  function aliasFormSupportsPartialRefresh(form) {
    const path = new URL(form.action, window.location.href).pathname;
    return /^\/aliases\/\d+\/(?:metadata|toggle|sender-expectation)$/.test(path);
  }

  async function submitAliasFormWithoutReload(form, submitter) {
    if (!aliasFormSupportsPartialRefresh(form)) return false;

    const method = (form.method || "post").toUpperCase();
    const dialog = form.closest("dialog");
    if (submitter) submitter.disabled = true;
    form.setAttribute("aria-busy", "true");

    try {
      const response = await fetch(form.action, {
        method,
        body: new FormData(form),
        credentials: "same-origin",
        headers: { Accept: "text/html" },
      });
      if (!response.ok) {
        throw new Error(`Alias update failed with HTTP ${response.status}`);
      }

      const html = await response.text();
      const renderedPage = new DOMParser().parseFromString(html, "text/html");
      const responseUrl = new URL(response.url || window.location.href);
      if (responseUrl.pathname !== "/aliases") {
        throw new Error(`Alias update returned unexpected page: ${responseUrl.pathname}`);
      }

      setAliasHistory(responseUrl, "replace");
      installRenderedAliasResults(renderedPage, responseUrl, true);
      if (dialog?.matches(":modal")) dialog.close();
      return true;
    } catch (error) {
      console.debug("Could not apply alias update without reload", error);
      if (submitter) submitter.disabled = false;
      form.removeAttribute("aria-busy");
      return false;
    }
  }

  async function applyBulkAliasActionWithoutReload(toolbar, applyButton) {
    const actionSelect = toolbar.querySelector("[data-bulk-action-select]");
    const action = actionSelect?.value || "";
    if (!action || action === "copy") return false;

    const region = toolbar.closest("[data-alias-results-region]");
    const selected = [
      ...(region?.querySelectorAll("[data-alias-select]:checked") || []),
    ];
    if (!selected.length) return true;

    const csrfToken = document.body.dataset.csrfToken || "";
    if (!csrfToken) return false;

    const payload = new FormData();
    payload.append("csrf_token", csrfToken);
    payload.append("action", action);
    selected.forEach((checkbox) => payload.append("alias_ids", checkbox.value));

    applyButton.disabled = true;
    actionSelect.disabled = true;
    toolbar.setAttribute("aria-busy", "true");
    try {
      const response = await fetch("/aliases/bulk", {
        method: "POST",
        body: payload,
        credentials: "same-origin",
      });
      if (!response.ok) {
        throw new Error(`Bulk alias update failed with HTTP ${response.status}`);
      }
      await refreshAliasResults(window.location.href, {
        historyMode: "replace",
        fallbackToNavigation: true,
        keepSearchValue: true,
      });
      return true;
    } catch (error) {
      console.debug("Could not apply bulk alias update without reload", error);
      applyButton.disabled = false;
      actionSelect.disabled = false;
      toolbar.removeAttribute("aria-busy");
      window.alert(toolbar.dataset.bulkFailed || "The bulk action could not be completed.");
      return true;
    }
  }

  function installRenderedDialog(renderedPage, selector, bindDialog) {
    const nextDialog = renderedPage.querySelector(selector);
    if (!nextDialog) {
      throw new Error(`Rendered dialog not found: ${selector}`);
    }

    const currentDialog = document.querySelector(selector);
    if (currentDialog) {
      if (currentDialog.matches(":modal")) {
        currentDialog.dataset.refreshing = "1";
        currentDialog.close();
      }
      currentDialog.replaceWith(nextDialog);
    } else {
      document.body.append(nextDialog);
    }

    showDialog(nextDialog);
    bindDialog(nextDialog);
    return nextDialog;
  }

  async function openRenderedDialog(trigger, selector, bindDialog) {
    const href = trigger.getAttribute("href");
    if (!href) return;

    trigger.setAttribute("aria-busy", "true");
    try {
      const renderedPage = await fetchRenderedPage(href);
      installRenderedDialog(renderedPage, selector, bindDialog);
    } catch (error) {
      console.debug("Could not open server-rendered alias dialog", error);
      window.location.assign(href);
    } finally {
      trigger.removeAttribute("aria-busy");
    }
  }

  function bindWorkflowCopyButtons(dialog) {
    dialog.querySelectorAll("[data-alias-workflow-copy]").forEach((button) => {
      if (button.dataset.workflowCopyBound === "1") return;
      button.dataset.workflowCopyBound = "1";
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
  }

  function bindWorkflowDialog(dialog) {
    if (!dialog || dialog.dataset.workflowDialogBound === "1") return;
    dialog.dataset.workflowDialogBound = "1";
    bindWorkflowCopyButtons(dialog);

    dialog.querySelectorAll(".dialog-close, [data-alias-workflow-done]").forEach((control) => {
      control.addEventListener("click", (event) => {
        event.preventDefault();
        dialog.close();
      });
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener("close", () => {
      if (dialog.dataset.refreshing === "1") {
        delete dialog.dataset.refreshing;
        return;
      }
      clearAliasDialogParam("workflow");
    });

    const workflowId = dialog.dataset.aliasWorkflowId;
    const pollMs = Number.parseInt(dialog.dataset.aliasWorkflowPollMs || "0", 10);
    if (!workflowId || !Number.isFinite(pollMs) || pollMs <= 0) return;

    let polling = false;
    const timer = window.setInterval(async () => {
      if (!dialog.isConnected) {
        window.clearInterval(timer);
        return;
      }
      if (polling || document.hidden || !dialog.matches(":modal")) return;
      polling = true;
      try {
        const response = await fetch(`/aliases/workflows/${workflowId}`, {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) return;
        const workflow = await response.json();
        if (workflow.state === dialog.dataset.aliasWorkflowState) return;
        window.clearInterval(timer);
        window.location.reload();
      } catch (error) {
        console.debug("Could not refresh alias workflow state", error);
      } finally {
        polling = false;
      }
    }, pollMs);
  }

  function bindReplacementDeactivationDialog(dialog) {
    if (!dialog || dialog.dataset.replacementDeactivationBound === "1") return;
    dialog.dataset.replacementDeactivationBound = "1";

    dialog.querySelectorAll('.dialog-close, .alias-replacement-cancel-form a[href="/aliases"]').forEach(
      (control) => {
        control.addEventListener("click", (event) => {
          event.preventDefault();
          dialog.close();
        });
      },
    );
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener("close", () => clearAliasDialogParam("deactivate"));
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

  const createForm = createDialog?.querySelector("[data-alias-create-form]");
  const createLoadingDialog = document.querySelector("[data-alias-create-loading-dialog]");
  createForm?.addEventListener("submit", (event) => {
    if (createForm.dataset.submitting === "1") {
      event.preventDefault();
      return;
    }
    createForm.dataset.submitting = "1";
    const submitButton = event.submitter || createForm.querySelector('button[type="submit"]');
    if (submitButton) submitButton.disabled = true;
    showDialog(createLoadingDialog);
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

  document.addEventListener("input", (event) => {
    const search = event.target.closest?.("[data-live-search]");
    if (!search) return;
    event.stopImmediatePropagation();
    syncAliasSearchClear();
    window.clearTimeout(aliasSearchTimer);
    aliasSearchTimer = window.setTimeout(() => {
      void refreshAliasResults(aliasSearchUrl(), {
        historyMode: "replace",
        keepSearchValue: true,
      });
    }, 250);
  }, true);

  document.addEventListener("change", (event) => {
    const select = event.target.closest?.("[data-page-size]");
    if (!select || !select.form) return;
    event.preventDefault();
    event.stopImmediatePropagation();

    const url = new URL(select.form.action || "/aliases", window.location.href);
    const values = new FormData(select.form);
    values.forEach((value, key) => url.searchParams.set(key, String(value)));
    url.searchParams.delete("page");
    void refreshAliasResults(url, {
      historyMode: "push",
      fallbackToNavigation: true,
      keepSearchValue: true,
    });
  }, true);

  document.addEventListener("submit", (event) => {
    const form = event.target.closest?.("form");
    if (!form || event.defaultPrevented || !aliasFormSupportsPartialRefresh(form)) return;
    event.preventDefault();
    const submitter = event.submitter;
    void submitAliasFormWithoutReload(form, submitter).then((handled) => {
      if (!handled && form.isConnected) form.submit();
    });
  });

  document.addEventListener("click", (event) => {
    const searchClear = event.target.closest?.("[data-search-clear]");
    if (searchClear) {
      const search = document.querySelector("[data-live-search]");
      if (!search) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      window.clearTimeout(aliasSearchTimer);
      search.value = "";
      syncAliasSearchClear();
      search.focus();
      void refreshAliasResults(aliasSearchUrl(), {
        historyMode: "replace",
        keepSearchValue: true,
      });
      return;
    }

    const deactivationTrigger = event.target.closest?.(
      "[data-open-replacement-deactivation], [data-alias-workflow-cancel]",
    );
    if (deactivationTrigger) {
      event.preventDefault();
      event.stopImmediatePropagation();
      deactivationTrigger.closest("details.alias-edit-action")?.removeAttribute("open");
      const sourceWorkflow = deactivationTrigger.closest("dialog[data-alias-workflow-dialog]");
      if (sourceWorkflow?.matches(":modal")) sourceWorkflow.close();
      openRenderedDialog(
        deactivationTrigger,
        "[data-replacement-deactivation-dialog]",
        bindReplacementDeactivationDialog,
      );
      return;
    }

    const bulkApply = event.target.closest?.(
      "[data-bulk-toolbar] .bulk-actions button:not([data-bulk-action])",
    );
    if (bulkApply) {
      const toolbar = bulkApply.closest("[data-bulk-toolbar]");
      const action = toolbar?.querySelector("[data-bulk-action-select]")?.value || "";
      if (toolbar && action && action !== "copy") {
        event.preventDefault();
        event.stopImmediatePropagation();
        void applyBulkAliasActionWithoutReload(toolbar, bulkApply);
        return;
      }
    }

    const aliasNavigation = event.target.closest?.(
      ".status-filters a, .alias-sort-link, .pagination a, .alias-replacement-history-link",
    );
    if (aliasNavigation) {
      if (
        event.button !== 0
        || event.metaKey
        || event.ctrlKey
        || event.shiftKey
        || event.altKey
        || aliasNavigation.target
        || aliasNavigation.hasAttribute("download")
      ) {
        return;
      }
      const url = new URL(aliasNavigation.href, window.location.href);
      if (url.origin !== window.location.origin || url.pathname !== "/aliases") return;

      event.preventDefault();
      event.stopImmediatePropagation();
      void refreshAliasResults(url, {
        historyMode: "push",
        fallbackToNavigation: true,
        keepSearchValue: !aliasNavigation.matches(".alias-replacement-history-link"),
      });
      return;
    }

    const trigger = event.target.closest?.("[data-alias-workflow-replace]");
    if (!trigger) return;

    const aliasId = trigger.dataset.aliasWorkflowReplace;
    const address = trigger.dataset.aliasWorkflowAddress || "";
    if (!aliasId || !address) return;

    event.preventDefault();
    event.stopImmediatePropagation();
    openReplacement(aliasId, address, trigger.closest("details.alias-edit-action"));
  }, true);

  window.addEventListener("popstate", () => {
    if (window.location.pathname !== "/aliases") return;
    void refreshAliasResults(window.location.href, {
      historyMode: "none",
      fallbackToNavigation: true,
      keepSearchValue: false,
    });
  });

  replacementDialog?.querySelectorAll("[data-close-alias-replacement]").forEach((control) => {
    control.addEventListener("click", (event) => {
      event.preventDefault();
      replacementDialog.close();
    });
  });
  replacementDialog?.addEventListener("click", (event) => {
    if (event.target === replacementDialog) replacementDialog.close();
  });

  const replacementDeactivationDialog = document.querySelector(
    "[data-replacement-deactivation-dialog]",
  );
  if (replacementDeactivationDialog?.hasAttribute("open")) {
    showDialog(replacementDeactivationDialog);
  }
  bindReplacementDeactivationDialog(replacementDeactivationDialog);

  const workflowDialog = document.querySelector("[data-alias-workflow-dialog]");
  if (workflowDialog?.hasAttribute("open")) showDialog(workflowDialog);
  bindWorkflowDialog(workflowDialog);
})();
