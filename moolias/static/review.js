(() => {
  const language = document.documentElement.lang?.toLowerCase().startsWith("de") ? "de" : "en";
  const text = {
    de: {
      title: "Handlungsbedarf",
      intro: "Hier findest du alles, was aktuell deine Aufmerksamkeit braucht.",
      empty: "Nichts weiter zu tun.",
      close: "Schließen",
      offlineTitle: "Benutzte Offline-Aliase",
      offlineIntro: (count) =>
        count === 1
          ? "Ein noch nicht zugeordneter Offline-Alias wurde bereits benutzt. Ordne ihn einem Zweck zu oder erledige das später."
          : `${count} noch nicht zugeordnete Offline-Aliase wurden bereits benutzt. Ordne sie einem Zweck zu oder erledige das später.`,
      poolPrivacyHint: "Angezeigt werden nur die Absenderinformationen, die dein aktueller Statistikmodus speichern darf.",
      poolAssign: "Ausgewählte zuordnen",
      poolPurpose: "Name / Zweck",
      poolPurposePlaceholder: "z. B. Hotel, Shop, Newsletter …",
      poolSelected: "Jetzt zuordnen",
      poolSkipped: "Vorerst nicht zuordnen",
      poolMissingPurpose: "Bitte trage für jeden ausgewählten Alias einen Namen oder Zweck ein.",
      poolFailed: "Mindestens ein Offline-Alias konnte nicht zugeordnet werden. Die Ansicht wird neu geladen, damit du den aktuellen Stand siehst.",
      unexpectedTitle: "Absender prüfen",
      unexpectedIntro: (count) =>
        count === 1
          ? "Ein aktiver Alias hat mindestens einen nicht automatisch erkannten Absender."
          : `${count} aktive Aliase haben mindestens einen nicht automatisch erkannten Absender.`,
      unexpected: (count) => `${count} nicht erkannt`,
      ignoreUnexpected: "Prüfung für diesen Alias ignorieren",
      ignoreUnexpectedHint: "Wird nicht mehr als zu prüfen markiert. Absender und Statistiken bleiben sichtbar.",
      ignoreUnexpectedFailed: "Die Einstellung für die Absenderprüfung konnte nicht gespeichert werden.",
      replace: "Alias ersetzen",
      healthTitle: "Statistik-Collector",
      healthStates: {
        low: "Historienpuffer niedrig",
        gap: "Mögliche Lücke in der Rspamd-Historie",
        stale: "Collector-Status veraltet",
        failed: "Collector-Fehler",
      },
      healthHints: {
        low: "Der vorherige Watermark liegt nahe am ältesten Rand der geladenen Historie. Prüfe die Collector-Details und erhöhe bei Bedarf das History-Maximum.",
        gap: "Der vorherige Watermark ist nicht mehr sicher vom aktuellen History-Fenster abgedeckt. Statistiken können eine Lücke enthalten.",
        stale: "Seit mehreren erwarteten Poll-Intervallen gab es keinen erfolgreichen Collector-Lauf.",
        failed: "Der letzte Collector-Lauf ist fehlgeschlagen. Prüfe die Collector-Details und die Server-Logs.",
      },
      healthDetails: "Die vollständigen Collector-Details stehen bei den Statistik-Einstellungen.",
      senderTitle: "Absender",
      poolHint: "Dieser Offline-Alias ist noch nicht zugeordnet. Die Absenderbewertung steht nach der Zuordnung zur Verfügung.",
      pendingReview: "Noch nicht bewertet",
      loadFailed: "Der Handlungsbedarf konnte nicht vollständig geladen werden.",
    },
    en: {
      title: "Action required",
      intro: "This is the single place for everything that currently needs your attention.",
      empty: "Nothing to do.",
      close: "Close",
      offlineTitle: "Used offline aliases",
      offlineIntro: (count) =>
        count === 1
          ? "One unassigned offline alias has already been used. Assign a purpose now or leave it for later."
          : `${count} unassigned offline aliases have already been used. Assign purposes now or leave them for later.`,
      poolPrivacyHint: "Only sender information permitted by your current statistics mode is shown.",
      poolAssign: "Assign selected",
      poolPurpose: "Name / purpose",
      poolPurposePlaceholder: "e.g. hotel, shop, newsletter …",
      poolSelected: "Assign now",
      poolSkipped: "Leave unassigned for now",
      poolMissingPurpose: "Enter a name or purpose for every selected alias.",
      poolFailed: "At least one offline alias could not be assigned. The page will reload so you can see the current state.",
      unexpectedTitle: "Unexpected senders",
      unexpectedIntro: (count) =>
        count === 1
          ? "One active alias contains at least one unexpected sender."
          : `${count} active aliases contain at least one unexpected sender.`,
      unexpected: (count) => `${count} unexpected`,
      ignoreUnexpected: "Ignore unexpected senders for this alias",
      ignoreUnexpectedHint: "Sender details and statistics remain visible, but this alias is no longer reported as requiring attention.",
      ignoreUnexpectedFailed: "The unexpected-sender setting could not be saved.",
      replace: "Replace alias",
      healthTitle: "Statistics collector",
      healthStates: {
        low: "Low history headroom",
        gap: "Possible Rspamd history gap",
        stale: "Collector status is stale",
        failed: "Collector failure",
      },
      healthHints: {
        low: "The previous watermark is close to the oldest edge of the loaded history. Check the collector details and increase the history maximum if needed.",
        gap: "The previous watermark is no longer safely covered by the current history window. Statistics may contain a gap.",
        stale: "No successful collector run has completed for several expected poll intervals.",
        failed: "The latest collector run failed. Check the collector details and server logs.",
      },
      healthDetails: "Full collector details are available in the statistics settings.",
      senderTitle: "Senders",
      poolHint: "This offline alias has not been assigned yet. Sender review becomes available after assignment.",
      pendingReview: "Not reviewed yet",
      loadFailed: "Action-required items could not be loaded completely.",
    },
  }[language];

  // Keep the existing key so sender-domain review and the replacement workflow
  // can preserve the aggregate review context across a reload.
  const REOPEN_KEY = "moolias-unexpected-review-reopen";
  const ACTIONABLE_HEALTH_STATES = new Set(["low", "gap", "stale", "failed"]);

  let actionDialog = null;
  let actionIntro = null;
  let actionContent = null;
  let healthPromise = null;

  const handleAuthenticationLoss = (response) => {
    if (response.status !== 401) return false;
    window.location.assign("/");
    return true;
  };

  const csrfToken = () => document.querySelector('input[name="csrf_token"]')?.value || "";

  const markForReopen = () => {
    try {
      sessionStorage.setItem(REOPEN_KEY, "1");
    } catch (error) {
      console.debug("sessionStorage is unavailable", error);
    }
  };

  const clearReopen = () => {
    try {
      sessionStorage.removeItem(REOPEN_KEY);
    } catch (error) {
      console.debug("sessionStorage is unavailable", error);
    }
  };

  const parseTotalPages = (documentRoot) => {
    const pages = [...documentRoot.querySelectorAll(".pagination .page-link")]
      .map((item) => Number.parseInt(item.textContent.trim(), 10))
      .filter(Number.isFinite);
    return pages.length ? Math.max(...pages) : 1;
  };

  const fetchAliasPage = async (page) => {
    const url = new URL("/aliases", window.location.origin);
    url.searchParams.set("status", "unexpected");
    url.searchParams.set("per_page", "100");
    url.searchParams.set("page", String(page));

    const response = await fetch(url, {
      headers: {
        Accept: "text/html",
        "X-Moolias-Partial": "action-required",
      },
      credentials: "same-origin",
    });
    if (handleAuthenticationLoss(response)) throw new Error("Authentication required");
    if (!response.ok) {
      throw new Error(`Action-required request failed with HTTP ${response.status}`);
    }
    return new DOMParser().parseFromString(await response.text(), "text/html");
  };

  const loadUnexpectedRows = async () => {
    const first = await fetchAliasPage(1);
    const documents = [first];
    const totalPages = parseTotalPages(first);
    if (totalPages > 1) {
      const rest = await Promise.all(
        Array.from({ length: totalPages - 1 }, (_, index) => fetchAliasPage(index + 2)),
      );
      documents.push(...rest);
    }

    return documents.flatMap((documentRoot) =>
      [...documentRoot.querySelectorAll(".alias-row")]
        .filter((row) => row.querySelector("[data-alias-select]")?.dataset.active !== "0")
        .map((row) => row.cloneNode(true)),
    );
  };

  const usedPoolItems = () => [...document.querySelectorAll(".pool-item.pool-item-used")];

  const loadCollectorHealth = async ({ fresh = false } = {}) => {
    if (!fresh && healthPromise) return healthPromise;
    healthPromise = fetch("/aliases/collector-health", { credentials: "same-origin" })
      .then((response) => {
        if (handleAuthenticationLoss(response)) throw new Error("Authentication required");
        if (!response.ok) throw new Error(`Collector health request failed with HTTP ${response.status}`);
        return response.json();
      })
      .catch((error) => {
        console.error("Could not load collector health for action required", error);
        return null;
      });
    return healthPromise;
  };

  const actionableHealth = (payload) =>
    payload?.enabled && ACTIONABLE_HEALTH_STATES.has(payload.state) ? payload : null;

  const currentUnexpectedCount = () => {
    const value = document.querySelector("[data-unexpected-filter] > span")?.textContent?.trim();
    const count = Number.parseInt(value || "", 10);
    return Number.isFinite(count) ? count : 0;
  };

  const getSummary = async () => {
    const health = actionableHealth(await loadCollectorHealth());
    const offline = usedPoolItems().length;
    const unexpected = currentUnexpectedCount();
    return {
      offline,
      unexpected,
      health: health ? 1 : 0,
      total: offline + unexpected + (health ? 1 : 0),
    };
  };

  const dialogHeading = () => {
    const head = document.createElement("div");
    head.className = "dialog-head";
    const headingWrap = document.createElement("div");
    const heading = document.createElement("h2");
    heading.textContent = text.title;
    actionIntro = document.createElement("p");
    actionIntro.className = "muted action-required-intro";
    actionIntro.textContent = text.intro;
    headingWrap.append(heading, actionIntro);

    const close = document.createElement("button");
    close.className = "dialog-close";
    close.type = "button";
    close.textContent = "×";
    close.setAttribute("aria-label", text.close);
    close.title = text.close;
    head.append(headingWrap, close);
    return { head, close };
  };

  const bindDialogClose = (dialog, close) => {
    close.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  };

  const ensureActionDialog = () => {
    if (actionDialog?.isConnected) return actionDialog;

    actionDialog = document.createElement("dialog");
    actionDialog.className = "assign-dialog unexpected-review-dialog action-required-dialog";
    actionDialog.dataset.actionRequiredDialog = "1";
    // Kept for sender-domain.js and the #56 replacement integration.
    actionDialog.dataset.unexpectedReviewDialog = "1";

    const { head, close } = dialogHeading();
    actionContent = document.createElement("div");
    actionContent.className = "action-required-content";
    actionDialog.append(head, actionContent);
    document.body.append(actionDialog);
    bindDialogClose(actionDialog, close);
    return actionDialog;
  };

  const makeSection = (title, count) => {
    const section = document.createElement("section");
    section.className = "action-required-section";
    const header = document.createElement("div");
    header.className = "action-required-section-head";
    const heading = document.createElement("h3");
    heading.textContent = title;
    const badge = document.createElement("span");
    badge.className = "count";
    badge.textContent = String(count);
    header.append(heading, badge);
    section.append(header);
    return section;
  };

  const buildOfflineSection = (items) => {
    if (!items.length) return null;
    const section = makeSection(text.offlineTitle, items.length);
    const intro = document.createElement("p");
    intro.className = "muted";
    intro.textContent = text.offlineIntro(items.length);
    const privacy = document.createElement("p");
    privacy.className = "hint";
    privacy.textContent = text.poolPrivacyHint;

    const form = document.createElement("form");
    form.className = "stack used-pool-form action-required-pool-form";
    const list = document.createElement("div");
    list.className = "used-pool-list";

    items.forEach((item) => {
      const assignButton = item.querySelector("[data-open-assign-dialog]");
      const aliasId = assignButton?.dataset.openAssignDialog;
      const address = item.querySelector("[data-pool-address]")?.textContent.trim();
      const sourceDialog = aliasId
        ? document.querySelector(`[data-assign-dialog="${CSS.escape(aliasId)}"]`)
        : null;
      if (!aliasId || !address || !sourceDialog) return;

      const row = document.createElement("section");
      row.className = "used-pool-row";
      row.dataset.poolAliasId = aliasId;

      const selectLabel = document.createElement("label");
      selectLabel.className = "used-pool-select check-row";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = true;
      const selectText = document.createElement("span");
      selectLabel.append(checkbox, selectText);

      const identity = document.createElement("div");
      identity.className = "used-pool-identity";
      const code = document.createElement("code");
      code.textContent = address;
      identity.append(code);
      const usage = sourceDialog.querySelector(".pool-assignment-usage")?.cloneNode(true);
      if (usage) identity.append(usage);

      const purposeLabel = document.createElement("label");
      purposeLabel.className = "used-pool-purpose";
      const purposeText = document.createElement("span");
      purposeText.textContent = text.poolPurpose;
      const purpose = document.createElement("input");
      purpose.type = "text";
      purpose.maxLength = 160;
      purpose.required = true;
      purpose.placeholder = text.poolPurposePlaceholder;
      purpose.autocomplete = "off";
      purposeLabel.append(purposeText, purpose);

      const syncSelection = () => {
        purpose.disabled = !checkbox.checked;
        purpose.required = checkbox.checked;
        row.classList.toggle("skipped", !checkbox.checked);
        selectText.textContent = checkbox.checked ? text.poolSelected : text.poolSkipped;
      };
      checkbox.addEventListener("change", syncSelection);
      syncSelection();
      row.append(selectLabel, identity, purposeLabel);
      list.append(row);
    });

    if (!list.children.length) return null;

    const actions = document.createElement("div");
    actions.className = "button-row used-pool-actions";
    const assign = document.createElement("button");
    assign.className = "button primary";
    assign.type = "submit";
    assign.textContent = text.poolAssign;
    actions.append(assign);
    form.append(list, actions);

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const selected = [...list.querySelectorAll(".used-pool-row")].filter(
        (row) => row.querySelector('input[type="checkbox"]')?.checked,
      );
      if (!selected.length) return;

      for (const row of selected) {
        const purpose = row.querySelector(".used-pool-purpose input");
        if (!purpose?.value.trim()) {
          await window.MooliasDialog.error(text.poolMissingPurpose);
          purpose?.focus();
          return;
        }
      }

      assign.disabled = true;
      let failed = false;
      for (const row of selected) {
        const aliasId = row.dataset.poolAliasId;
        const purpose = row.querySelector(".used-pool-purpose input");
        const sourceForm = document.querySelector(
          `[data-assign-dialog="${CSS.escape(aliasId)}"] form`,
        );
        if (!sourceForm || !purpose) {
          failed = true;
          break;
        }

        const csrf = sourceForm.querySelector('input[name="csrf_token"]')?.value;
        if (!csrf) {
          failed = true;
          break;
        }
        const data = new FormData();
        data.append("csrf_token", csrf);
        data.append("description", purpose.value.trim());

        try {
          const response = await fetch(sourceForm.action, {
            method: "POST",
            body: data,
            credentials: "same-origin",
          });
          if (handleAuthenticationLoss(response)) return;
          if (!response.ok) {
            failed = true;
            break;
          }
        } catch (error) {
          console.error("Offline alias assignment failed", error);
          failed = true;
          break;
        }
      }

      markForReopen();
      if (failed) await window.MooliasDialog.error(text.poolFailed);
      window.location.reload();
    });

    section.append(intro, privacy, form);
    return section;
  };

  const saveUnexpectedIgnored = async (sourceRow) => {
    const select = sourceRow.querySelector("[data-alias-select]");
    const aliasId = select?.value;
    const csrf = csrfToken();
    if (!aliasId || !csrf) throw new Error("Missing alias review context");

    const payload = new FormData();
    payload.append("csrf_token", csrf);
    payload.append("ignored", "true");
    const response = await fetch(`/aliases/${encodeURIComponent(aliasId)}/unexpected-monitoring`, {
      method: "POST",
      body: payload,
      credentials: "same-origin",
    });
    if (handleAuthenticationLoss(response)) return false;
    if (!response.ok) {
      throw new Error(`Unexpected monitoring update failed with HTTP ${response.status}`);
    }
    return true;
  };

  const buildUnexpectedSetting = (sourceRow) => {
    const wrapper = document.createElement("div");
    wrapper.className = "sender-review-settings";
    const label = document.createElement("label");
    label.className = "check-row";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    const labelText = document.createElement("span");
    labelText.textContent = text.ignoreUnexpected;
    label.append(checkbox, labelText);
    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = text.ignoreUnexpectedHint;

    checkbox.addEventListener("change", async () => {
      if (!checkbox.checked) return;
      checkbox.disabled = true;
      try {
        if (await saveUnexpectedIgnored(sourceRow)) {
          markForReopen();
          window.location.reload();
        }
      } catch (error) {
        console.error("Could not save unexpected sender setting", error);
        checkbox.checked = false;
        checkbox.disabled = false;
        await window.MooliasDialog.error(text.ignoreUnexpectedFailed);
      }
    });
    wrapper.append(label, hint);
    return wrapper;
  };

  const prepareReviewForm = (form) => {
    const returnTo = form.querySelector('input[name="return_to"]');
    if (returnTo) returnTo.value = "/aliases";
    form.addEventListener("submit", markForReopen);
  };

  const openReplacementFromReview = (select) => {
    if (typeof window.showReplacementDialog !== "function") return;
    const existingDialogs = new Set(document.querySelectorAll("dialog"));
    window.showReplacementDialog(select, null);
    const replacementDialog = [...document.querySelectorAll("dialog")].find(
      (dialog) => !existingDialogs.has(dialog),
    );
    if (!replacementDialog) return;

    replacementDialog.querySelector(".button.primary")?.addEventListener("click", markForReopen);
    replacementDialog.addEventListener(
      "close",
      () => {
        window.setTimeout(() => {
          if (!document.querySelector("dialog.assign-dialog-single[open]")) clearReopen();
        }, 0);
      },
      { once: true },
    );
  };

  const buildAliasReview = (sourceRow) => {
    const select = sourceRow.querySelector("[data-alias-select]");
    const address = select?.dataset.address?.trim() || "";
    const description = select?.dataset.description?.trim() || "";
    const senderDetails = sourceRow.querySelector("details.sender-stats");
    const sourceList = senderDetails?.querySelector(".sender-stats-list");
    if (!address || select?.dataset.active === "0" || !sourceList) return null;

    const unexpectedCount = sourceList.querySelectorAll(".sender-stats-row.unexpected").length;
    const block = document.createElement("section");
    block.className = "unexpected-review-alias";
    const header = document.createElement("div");
    header.className = "unexpected-review-alias-head";
    const identity = document.createElement("div");
    identity.className = "unexpected-review-identity";
    if (description) {
      const strong = document.createElement("strong");
      strong.textContent = description;
      identity.append(strong);
    }
    const code = document.createElement("code");
    code.textContent = address;
    identity.append(code);

    const actions = document.createElement("div");
    actions.className = "action-required-alias-actions";
    const alert = document.createElement("span");
    alert.className = "sender-stats-alert";
    alert.textContent = text.unexpected(unexpectedCount);
    actions.append(alert);

    if (typeof window.showReplacementDialog === "function") {
      const replace = document.createElement("button");
      replace.className = "button compact";
      replace.type = "button";
      replace.dataset.reviewReplaceAlias = select.value;
      replace.textContent = text.replace;
      replace.addEventListener("click", () => openReplacementFromReview(select));
      actions.append(replace);
    }
    header.append(identity, actions);

    const setting = buildUnexpectedSetting(sourceRow);
    const senderList = document.importNode(sourceList, true);
    senderList.querySelectorAll(".sender-review-form").forEach(prepareReviewForm);
    block.append(header, setting, senderList);
    const footnote = senderDetails.querySelector(".sender-stats-footnote")?.cloneNode(true);
    if (footnote) block.append(footnote);
    return block;
  };

  const buildUnexpectedSection = (rows) => {
    if (!rows.length) return null;
    const section = makeSection(text.unexpectedTitle, rows.length);
    const intro = document.createElement("p");
    intro.className = "muted";
    intro.textContent = text.unexpectedIntro(rows.length);
    const list = document.createElement("div");
    list.className = "unexpected-review-list";
    rows.forEach((row) => {
      const block = buildAliasReview(row);
      if (block) list.append(block);
    });
    if (!list.children.length) return null;
    section.append(intro, list);
    return section;
  };

  const buildHealthSection = (payload) => {
    const health = actionableHealth(payload);
    if (!health) return null;
    const section = makeSection(text.healthTitle, 1);
    section.classList.add("action-required-health");
    const warning = document.createElement("div");
    warning.className = `action-required-health-warning state-${health.state}`;
    const strong = document.createElement("strong");
    strong.textContent = text.healthStates[health.state] || text.healthTitle;
    const hint = document.createElement("p");
    hint.textContent = text.healthHints[health.state] || text.healthDetails;
    const details = document.createElement("p");
    details.className = "hint";
    details.textContent = text.healthDetails;
    warning.append(strong, hint, details);
    section.append(warning);
    return section;
  };

  const renderActionDialog = async () => {
    ensureActionDialog();
    actionContent.replaceChildren();
    const loading = document.createElement("p");
    loading.className = "muted";
    loading.textContent = "…";
    actionContent.append(loading);

    try {
      const [rows, health] = await Promise.all([
        loadUnexpectedRows(),
        loadCollectorHealth({ fresh: true }),
      ]);
      const sections = [
        buildOfflineSection(usedPoolItems()),
        buildUnexpectedSection(rows),
        buildHealthSection(health),
      ].filter(Boolean);
      actionContent.replaceChildren();
      sections.forEach((section) => actionContent.append(section));
      if (!sections.length) {
        const empty = document.createElement("p");
        empty.className = "empty action-required-empty";
        empty.textContent = text.empty;
        actionContent.append(empty);
      }
      actionDialog.dispatchEvent(new CustomEvent("moolias:action-required-rendered"));
      return sections.length;
    } catch (error) {
      console.error("Could not render action required", error);
      actionContent.replaceChildren();
      const failed = document.createElement("p");
      failed.className = "empty";
      failed.textContent = text.loadFailed;
      actionContent.append(failed);
      return 0;
    }
  };

  const openActionDialog = async () => {
    const dialog = ensureActionDialog();
    await renderActionDialog();
    if (!dialog.open) dialog.showModal();
  };

  const buildPoolSenderDialog = (trigger) => {
    const item = trigger.closest(".pool-item");
    const assignButton = item?.querySelector("[data-open-assign-dialog]");
    const aliasId = assignButton?.dataset.openAssignDialog;
    const address = item?.querySelector("[data-pool-address]")?.textContent.trim();
    if (!aliasId || !address) return null;

    let dialog = document.querySelector(`[data-review-pool-dialog="${CSS.escape(aliasId)}"]`);
    if (dialog) return dialog;
    const sourceDialog = document.querySelector(`[data-assign-dialog="${CSS.escape(aliasId)}"]`);
    const sourceList = sourceDialog?.querySelector(".pool-assignment-usage .sender-stats-list");
    if (!sourceList) return null;

    dialog = document.createElement("dialog");
    dialog.className = "assign-dialog sender-stats-dialog";
    dialog.dataset.reviewPoolDialog = aliasId;
    const head = document.createElement("div");
    head.className = "dialog-head";
    const heading = document.createElement("h2");
    heading.textContent = text.senderTitle;
    const close = document.createElement("button");
    close.className = "dialog-close";
    close.type = "button";
    close.textContent = "×";
    close.setAttribute("aria-label", text.close);
    head.append(heading, close);

    const content = document.createElement("div");
    content.className = "sender-stats-dialog-content";
    const context = document.createElement("div");
    context.className = "sender-review-settings";
    const code = document.createElement("code");
    code.textContent = address;
    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = text.poolHint;
    context.append(code, hint);

    const list = document.importNode(sourceList, true);
    list.classList.remove("pool-sender-list");
    list.querySelectorAll(".sender-stats-row").forEach((row) => {
      row.classList.add("unexpected");
      if (row.querySelector(".sender-review-state")) return;
      const state = document.createElement("span");
      state.className = "sender-review-state";
      state.textContent = text.pendingReview;
      const count = row.querySelector(".sender-message-count");
      if (count) row.insertBefore(state, count);
      else row.append(state);
    });

    content.append(context, list);
    dialog.append(head, content);
    document.body.append(dialog);
    bindDialogClose(dialog, close);
    return dialog;
  };

  const installPoolSenderCapture = () => {
    document.addEventListener(
      "click",
      (event) => {
        const trigger = event.target.closest?.(".pool-item .sender-stats-trigger");
        if (!trigger) return;
        const dialog = buildPoolSenderDialog(trigger);
        if (!dialog) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        dialog.showModal();
      },
      true,
    );
  };

  window.MooliasActionRequired = {
    open: openActionDialog,
    summary: getSummary,
    markForReopen,
  };

  const start = () => {
    if (!document.querySelector(".status-filters")) return;
    installPoolSenderCapture();
    try {
      if (sessionStorage.getItem(REOPEN_KEY) === "1") {
        sessionStorage.removeItem(REOPEN_KEY);
        openActionDialog();
      }
    } catch (error) {
      console.debug("sessionStorage is unavailable", error);
    }
    document.dispatchEvent(new CustomEvent("moolias:action-required-ready"));
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();