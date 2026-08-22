(() => {
  "use strict";

  const selects = [...document.querySelectorAll("[data-alias-icon-select]")];
  if (!selects.length) return;

  const serviceLogoKeys = new Set([
    "apple",
    "booking",
    "discord",
    "dropbox",
    "ebay",
    "facebook",
    "github",
    "gitlab",
    "google",
    "instagram",
    "netflix",
    "notion",
    "paypal",
    "reddit",
    "signal",
    "spotify",
    "steam",
    "stripe",
    "telegram",
    "tiktok",
    "twitch",
    "x",
    "zalando",
    "zoom",
  ]);

  const fallbackGlyphs = new Map([
    ["generic", "?"],
    ["amazon", "A"],
    ["linkedin", "in"],
    ["microsoft", "M"],
    ["openai", "O"],
    ["slack", "S"],
  ]);

  const german = (document.documentElement.lang || "").toLowerCase().startsWith("de");
  const text = german
    ? {
        title: "Dienstsymbol auswählen",
        search: "Logo suchen…",
        close: "Schließen",
        automatic: "Automatisch erkannt",
        manual: "Manuell ausgewählt",
        noResults: "Keine passenden Logos gefunden.",
        results: (count) => `${count} ${count === 1 ? "Treffer" : "Treffer"}`,
      }
    : {
        title: "Choose service icon",
        search: "Search logos…",
        close: "Close",
        automatic: "Detected automatically",
        manual: "Selected manually",
        noResults: "No matching logos found.",
        results: (count) => `${count} ${count === 1 ? "result" : "results"}`,
      };

  const optionSource = selects[0];
  const iconOptions = [...optionSource.options].map((option) => ({
    key: option.value,
    label: option.textContent.trim(),
  }));

  const createLogo = (key, label, className = "") => {
    const mark = document.createElement("span");
    mark.className = `service-icon-picker-mark ${className}`.trim();

    if (key === "auto") {
      mark.classList.add("automatic");
      mark.textContent = "↻";
      return mark;
    }

    if (!serviceLogoKeys.has(key)) {
      mark.textContent = fallbackGlyphs.get(key) || label.slice(0, 1) || "?";
      return mark;
    }

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.classList.add("service-logo");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `/static/service-icons.svg#service-${key}`);
    svg.append(use);
    mark.append(svg);
    return mark;
  };

  const dialog = document.createElement("dialog");
  dialog.className = "service-icon-picker-dialog";
  dialog.dataset.serviceIconPickerDialog = "";
  dialog.innerHTML = `
    <div class="service-icon-picker-shell">
      <header class="service-icon-picker-head">
        <div>
          <h2>${text.title}</h2>
          <p class="muted" data-icon-picker-result-count></p>
        </div>
        <button class="dialog-close" type="button" aria-label="${text.close}" data-icon-picker-close>×</button>
      </header>
      <div class="service-icon-picker-search">
        <span aria-hidden="true">⌕</span>
        <input type="search" autocomplete="off" placeholder="${text.search}" aria-label="${text.search}" data-icon-picker-search>
      </div>
      <div class="service-icon-picker-grid" data-icon-picker-grid></div>
      <p class="empty service-icon-picker-empty" data-icon-picker-empty hidden>${text.noResults}</p>
    </div>
  `;
  document.body.append(dialog);

  const grid = dialog.querySelector("[data-icon-picker-grid]");
  const search = dialog.querySelector("[data-icon-picker-search]");
  const empty = dialog.querySelector("[data-icon-picker-empty]");
  const resultCount = dialog.querySelector("[data-icon-picker-result-count]");
  const optionButtons = [];

  iconOptions.forEach(({ key, label }) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "service-icon-picker-option";
    button.dataset.iconPickerOption = key;
    button.dataset.searchText = `${label} ${key}`.toLowerCase();
    button.setAttribute("aria-label", label);
    button.append(createLogo(key, label));

    const name = document.createElement("span");
    name.className = "service-icon-picker-name";
    name.textContent = label;
    button.append(name);

    grid.append(button);
    optionButtons.push(button);
  });

  let activeSelect = null;

  const filterOptions = () => {
    const query = search.value.trim().toLowerCase();
    let visible = 0;
    optionButtons.forEach((button) => {
      const matches = !query || button.dataset.searchText.includes(query);
      button.hidden = !matches;
      if (matches) visible += 1;
    });
    empty.hidden = visible !== 0;
    resultCount.textContent = text.results(visible);
  };

  const syncSelectedOption = () => {
    if (!activeSelect) return;
    optionButtons.forEach((button) => {
      const selected = button.dataset.iconPickerOption === activeSelect.value;
      button.classList.toggle("selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
  };

  const setBusy = (busy) => {
    dialog.classList.toggle("saving", busy);
    search.disabled = busy;
    optionButtons.forEach((button) => {
      button.disabled = busy;
    });
  };

  const badgeFor = (select) => {
    const aliasId = select.dataset.aliasId;
    if (!aliasId) return null;
    return document.querySelector(
      `[data-service-icon-for="${CSS.escape(String(aliasId))}"]`,
    );
  };

  const syncTrigger = (select) => {
    const trigger = select._serviceIconPickerTrigger;
    if (!trigger) return;
    const badge = badgeFor(select);
    const preview = trigger.querySelector("[data-icon-picker-preview]");
    const name = trigger.querySelector("[data-icon-picker-current-name]");
    const mode = trigger.querySelector("[data-icon-picker-current-mode]");
    if (!preview || !name || !mode) return;

    preview.replaceChildren();
    preview.className = "service-badge service-icon-picker-current-mark";

    if (badge) {
      [...badge.classList]
        .filter((className) => className.startsWith("tone-"))
        .forEach((className) => preview.classList.add(className));
      [...badge.childNodes].forEach((node) => preview.append(node.cloneNode(true)));
      name.textContent = badge.title || select.selectedOptions[0]?.textContent || "";
    } else {
      const selected = iconOptions.find((option) => option.key === select.value);
      preview.append(createLogo(select.value, selected?.label || "?"));
      name.textContent = selected?.label || "";
    }

    mode.textContent = select.value === "auto" ? text.automatic : text.manual;
  };

  const waitForSave = (select) => {
    const started = Date.now();
    const poll = () => {
      if (select.disabled && Date.now() - started < 10000) {
        window.setTimeout(poll, 40);
        return;
      }
      setBusy(false);
      syncTrigger(select);
      if (dialog.open) dialog.close();
    };
    window.setTimeout(poll, 0);
  };

  optionButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (!activeSelect || activeSelect.disabled) return;
      const key = button.dataset.iconPickerOption;
      if (!key) return;

      if (activeSelect.value === key) {
        dialog.close();
        return;
      }

      activeSelect.value = key;
      setBusy(true);
      activeSelect.dispatchEvent(new Event("change", { bubbles: true }));
      waitForSave(activeSelect);
    });
  });

  const openPicker = (select) => {
    activeSelect = select;
    search.value = "";
    setBusy(false);
    filterOptions();
    syncSelectedOption();
    dialog.showModal();
    window.requestAnimationFrame(() => search.focus());
  };

  selects.forEach((select) => {
    select.hidden = true;
    const label = select.closest("label");
    label?.classList.add("service-icon-picker-label");

    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "service-icon-picker-trigger";
    trigger.dataset.iconPickerTrigger = "";
    trigger.dataset.aliasId = select.dataset.aliasId || "";
    trigger.innerHTML = `
      <span class="service-badge service-icon-picker-current-mark" data-icon-picker-preview></span>
      <span class="service-icon-picker-current-copy">
        <strong data-icon-picker-current-name></strong>
        <small data-icon-picker-current-mode></small>
      </span>
      <span class="service-icon-picker-chevron" aria-hidden="true">⌄</span>
    `;
    select._serviceIconPickerTrigger = trigger;
    label?.insertAdjacentElement("afterend", trigger);
    syncTrigger(select);

    trigger.addEventListener("click", () => openPicker(select));

    const badge = badgeFor(select);
    if (badge) {
      new MutationObserver(() => syncTrigger(select)).observe(badge, {
        attributes: true,
        childList: true,
        subtree: true,
        attributeFilter: ["class", "title"],
      });
    }
  });

  search.addEventListener("input", filterOptions);
  dialog.querySelector("[data-icon-picker-close]")?.addEventListener("click", () => {
    dialog.close();
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener("close", () => {
    setBusy(false);
    activeSelect = null;
  });
})();
