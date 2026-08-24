(() => {
  "use strict";

  const selects = [...document.querySelectorAll("[data-alias-icon-select]")];
  if (!selects.length) return;

  const fallbackGlyphs = new Map([
    ["generic", "AL"],
    ["amazon", "A"],
    ["check24", "C"],
    ["linkedin", "in"],
    ["microsoft", "M"],
    ["openai", "O"],
    ["slack", "S"],
    ["takko", "T"],
    ["tkmaxx", "TK"],
  ]);

  const logoHref = (key) => window.MooliasServiceLogos?.href(key) || null;

  const german = (document.documentElement.lang || "").toLowerCase().startsWith("de");
  const text = german
    ? {
        title: "Alias-Logo auswählen",
        aliasLogo: "Alias-Logo",
        aliasName: "Alias Name",
        search: "Logo suchen…",
        close: "Schließen",
        noResults: "Keine passenden Logos gefunden.",
        results: (count) => `${count} Treffer`,
        replace: "Alias ersetzen",
        disable: "Alias deaktivieren",
        enable: "Alias aktivieren",
      }
    : {
        title: "Choose alias logo",
        aliasLogo: "Alias logo",
        aliasName: "Alias name",
        search: "Search logos…",
        close: "Close",
        noResults: "No matching logos found.",
        results: (count) => `${count} ${count === 1 ? "result" : "results"}`,
        replace: "Replace alias",
        disable: "Disable alias",
        enable: "Enable alias",
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

    const href = logoHref(key);
    if (!href) {
      mark.textContent = fallbackGlyphs.get(key) || label.slice(0, 2).toUpperCase() || "AL";
      return mark;
    }

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.classList.add("service-logo");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", href);
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
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <circle cx="11" cy="11" r="6.5"></circle>
          <path d="m16 16 4 4"></path>
        </svg>
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
    if (!preview) return;

    preview.replaceChildren();
    preview.className = "service-badge service-icon-picker-current-mark";

    let currentName = select.selectedOptions[0]?.textContent?.trim() || text.aliasLogo;
    if (badge) {
      [...badge.classList]
        .filter((className) => className.startsWith("tone-"))
        .forEach((className) => preview.classList.add(className));
      [...badge.childNodes].forEach((node) => preview.append(node.cloneNode(true)));
      currentName = badge.title || currentName;
    } else {
      const selected = iconOptions.find((option) => option.key === select.value);
      preview.append(createLogo(select.value, selected?.label || "AL"));
      currentName = selected?.label || currentName;
    }

    trigger.setAttribute("aria-label", `${text.aliasLogo}: ${currentName}`);
    trigger.title = `${text.aliasLogo}: ${currentName}`;
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

  const replaceLabelText = (label, value) => {
    if (!label) return;
    [...label.childNodes]
      .filter((node) => node.nodeType === Node.TEXT_NODE)
      .forEach((node) => node.remove());

    const captions = [
      ...label.querySelectorAll(
        ":scope > span.alias-field-caption, :scope > [data-field-caption]",
      ),
    ];
    let caption = captions.shift();
    captions.forEach((extra) => extra.remove());
    if (!caption) {
      caption = document.createElement("span");
      label.prepend(caption);
    }
    caption.classList.add("alias-field-caption");
    caption.textContent = value;
  };

  const polishEditPanel = (select) => {
    const panel = select.closest(".edit-panel");
    const iconPreference = select.closest(".icon-preference");
    if (!panel || !iconPreference || panel.querySelector(".alias-edit-purpose-row")) return;

    iconPreference.querySelector(".hint")?.remove();
    const iconLabel = iconPreference.querySelector(".service-icon-picker-label");
    iconLabel?.classList.add("sr-only");

    const aliasRow = panel.closest(".alias-row");
    const aliasCheckbox = aliasRow?.querySelector("[data-alias-select]");
    const metadataForm = panel.querySelector('form[action$="/metadata"]');
    const description = metadataForm?.querySelector('input[name="description"]');
    const nameLabel = description?.closest("label");
    replaceLabelText(nameLabel, text.aliasName);

    if (metadataForm && nameLabel) {
      const nameRow = document.createElement("div");
      nameRow.className = "alias-edit-purpose-row";
      nameLabel.insertAdjacentElement("beforebegin", nameRow);
      nameRow.append(iconPreference, nameLabel);
    }

    const replaceButton = panel.querySelector("[data-replace-alias]");
    const toggleForm = panel.querySelector(".alias-toggle-action");
    const toggleButton = toggleForm?.querySelector("button");
    const active = aliasCheckbox?.dataset.active !== "0";

    if (replaceButton) {
      const previous = replaceButton.previousElementSibling;
      if (previous?.matches(".hint")) previous.remove();
      replaceButton.textContent = text.replace;
      replaceButton.className = "button compact alias-replace-action";
      if (toggleForm) toggleForm.insertAdjacentElement("beforebegin", replaceButton);
    }

    if (toggleButton) {
      toggleButton.textContent = active ? text.disable : text.enable;
      toggleButton.classList.toggle("danger", active);
    }
  };

  selects.forEach((select) => {
    select.hidden = true;
    const label = select.closest("label");
    label?.classList.add("service-icon-picker-label");
    const labelText = label?.querySelector(":scope > span");
    if (labelText) labelText.textContent = text.aliasLogo;

    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "service-icon-picker-trigger";
    trigger.dataset.iconPickerTrigger = "";
    trigger.dataset.aliasId = select.dataset.aliasId || "";
    trigger.innerHTML = `
      <span class="service-badge service-icon-picker-current-mark" data-icon-picker-preview></span>
    `;
    select._serviceIconPickerTrigger = trigger;
    label?.insertAdjacentElement("afterend", trigger);
    syncTrigger(select);
    polishEditPanel(select);

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