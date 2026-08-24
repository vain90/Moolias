(() => {
  "use strict";

  const createUiIcon = (name) => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.classList.add("ui-icon");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `/static/ui-icons.svg#icon-${name}`);
    svg.append(use);
    return svg;
  };

  const createFlag = (code) => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.classList.add("language-flag");
    svg.setAttribute("viewBox", "0 0 60 36");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");

    const element = (name, attrs) => {
      const node = document.createElementNS("http://www.w3.org/2000/svg", name);
      Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
      return node;
    };

    if (code === "de") {
      svg.append(
        element("rect", { width: "60", height: "12", fill: "#000" }),
        element("rect", { y: "12", width: "60", height: "12", fill: "#dd0000" }),
        element("rect", { y: "24", width: "60", height: "12", fill: "#ffce00" }),
      );
      return svg;
    }

    svg.append(element("rect", { width: "60", height: "36", fill: "#012169" }));
    svg.append(
      element("path", {
        d: "M0 0 60 36M60 0 0 36",
        stroke: "#fff",
        "stroke-width": "8",
      }),
      element("path", {
        d: "M0 0 60 36M60 0 0 36",
        stroke: "#c8102e",
        "stroke-width": "4",
      }),
      element("path", {
        d: "M30 0v36M0 18h60",
        stroke: "#fff",
        "stroke-width": "12",
      }),
      element("path", {
        d: "M30 0v36M0 18h60",
        stroke: "#c8102e",
        "stroke-width": "7",
      }),
    );
    return svg;
  };

  const languageMetadata = {
    de: { label: "Deutsch" },
    en: { label: "English" },
  };

  const enhanceLanguageSwitch = (nav) => {
    if (nav.dataset.languageDropdownReady === "1") return;

    const links = [...nav.querySelectorAll('a[href*="/language/"]')];
    const options = links
      .map((link) => {
        const match = link.getAttribute("href")?.match(/\/language\/([a-z]{2})(?:\?|$)/i);
        if (!match) return null;
        const code = match[1].toLowerCase();
        const metadata = languageMetadata[code];
        if (!metadata) return null;
        return { code, href: link.href, ...metadata };
      })
      .filter(Boolean);
    if (!options.length) return;

    const currentCode = document.documentElement.lang?.toLowerCase().startsWith("de") ? "de" : "en";
    const current = options.find((option) => option.code === currentCode) || options[0];

    const details = document.createElement("details");
    details.className = "language-dropdown";
    details.dataset.languageDropdown = "1";

    const summary = document.createElement("summary");
    summary.className = "language-dropdown-trigger";
    const languageLabel = nav.getAttribute("aria-label") || "Language";
    summary.setAttribute("aria-label", `${languageLabel}: ${current.label}`);
    summary.title = current.label;
    summary.append(createFlag(current.code));

    const menu = document.createElement("div");
    menu.className = "language-dropdown-menu";
    menu.setAttribute("role", "menu");

    options.forEach((option) => {
      const link = document.createElement("a");
      link.className = `language-dropdown-option${option.code === current.code ? " current" : ""}`;
      link.href = option.href;
      link.lang = option.code;
      link.setAttribute("role", "menuitemradio");
      link.setAttribute("aria-checked", String(option.code === current.code));
      link.append(createFlag(option.code));

      const label = document.createElement("span");
      label.textContent = option.label;
      link.append(label);

      if (option.code === current.code) {
        const selected = createUiIcon("circle-check");
        selected.classList.add("language-selected-icon");
        link.append(selected);
      }
      menu.append(link);
    });

    details.append(summary, menu);
    nav.replaceChildren(details);
    nav.dataset.languageDropdownReady = "1";
  };

  const enhanceBranding = () => {
    const favicon = document.querySelector('link[rel="icon"]');
    if (favicon) {
      favicon.href = "/static/favicon-32.png?v=20260823-3";
      favicon.type = "image/png";
      favicon.sizes = "32x32";
    }

    document.querySelectorAll(".brand-mark").forEach((mark) => {
      if (mark.querySelector("img")) return;
      const image = document.createElement("img");
      image.src = "/static/icon-192.webp?v=20260823-3";
      image.alt = "";
      image.width = 40;
      image.height = 40;
      image.decoding = "async";
      mark.classList.add("brand-mark-logo");
      mark.replaceChildren(image);
    });

    const hero = document.querySelector(".public-shell .hero");
    const heading = hero?.querySelector("h1");
    if (hero && heading && !hero.querySelector(".hero-brand-logo")) {
      const image = document.createElement("img");
      image.className = "hero-brand-logo";
      image.src = "/static/icon-192.webp?v=20260823-3";
      image.alt = "";
      image.width = 88;
      image.height = 88;
      image.decoding = "async";
      hero.insertBefore(image, heading);
    }
  };

  const aliasDescriptionCopy = {
    de: {
      address: "Alias-Adresse",
      name: "Alias Name",
      description: "Beschreibung",
      showDescription: "Beschreibung vollständig anzeigen",
      column: "Alias Name / Alias-Adresse",
    },
    en: {
      address: "Alias address",
      name: "Alias name",
      description: "Description",
      showDescription: "Show full description",
      column: "Alias name / alias address",
    },
  };

  const ensureAliasDescriptionStyles = () => {
    if (document.querySelector('link[data-alias-description-styles]')) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/static/alias-descriptions.css?v=20260824-1";
    link.dataset.aliasDescriptionStyles = "1";
    document.head.append(link);
  };

  const setLabelCaption = (label, text) => {
    [...label.childNodes]
      .filter((node) => node.nodeType === Node.TEXT_NODE)
      .forEach((node) => node.remove());

    let caption = label.querySelector(":scope > [data-field-caption]");
    if (!caption) {
      caption = document.createElement("span");
      caption.dataset.fieldCaption = "1";
      label.prepend(caption);
    }
    caption.textContent = text;
  };

  const replaceLinkText = (link, text) => {
    const textNode = [...link.childNodes].find((node) => node.nodeType === Node.TEXT_NODE);
    if (textNode) textNode.textContent = text;
  };

  const ensureAliasAddress = (form, address, copy) => {
    if (!address || form.querySelector("[data-alias-edit-address]")) return;
    const nameInput = form.querySelector('input[name="description"]');
    const nameLabel = nameInput?.closest("label");
    if (!nameLabel) return;

    const block = document.createElement("div");
    block.className = "alias-edit-address";
    block.dataset.aliasEditAddress = "1";

    const caption = document.createElement("span");
    caption.textContent = copy.address;
    const code = document.createElement("code");
    code.textContent = address;
    block.append(caption, code);
    form.insertBefore(block, nameLabel);
  };

  const ensurePrivateDescriptionField = (form, value, copy) => {
    const nameInput = form.querySelector('input[name="description"]');
    const nameLabel = nameInput?.closest("label");
    if (!nameInput || !nameLabel) return;

    setLabelCaption(nameLabel, copy.name);

    const existing = form.querySelector('[name="private_description"]');
    if (existing) return;

    const label = document.createElement("label");
    label.dataset.aliasPrivateDescriptionField = "1";

    const caption = document.createElement("span");
    caption.dataset.fieldCaption = "1";
    caption.textContent = copy.description;
    label.append(caption);

    const textarea = document.createElement("textarea");
    textarea.name = "private_description";
    textarea.maxLength = 160;
    textarea.rows = 4;
    textarea.value = value || "";
    textarea.setAttribute("aria-label", copy.description);
    label.append(textarea);

    nameLabel.after(label);
  };

  const addDescriptionPreview = (container, value, copy) => {
    if (!container || !value || container.querySelector("[data-alias-private-description-preview]")) return;

    const details = document.createElement("details");
    details.className = "alias-description-details";
    details.dataset.aliasPrivateDescriptionPreview = "1";

    const summary = document.createElement("summary");
    summary.className = "alias-description-summary";
    summary.title = copy.showDescription;
    summary.setAttribute("aria-label", copy.showDescription);

    const preview = document.createElement("span");
    preview.className = "alias-description-preview";
    preview.textContent = value;

    const info = document.createElement("span");
    info.className = "alias-description-info";
    info.setAttribute("aria-hidden", "true");
    info.textContent = "i";

    const full = document.createElement("div");
    full.className = "alias-description-popover";
    full.textContent = value;

    summary.append(preview, info);
    details.append(summary, full);

    const address = container.querySelector("code");
    if (address) {
      container.insertBefore(details, address);
    } else {
      container.append(details);
    }
  };

  const enhanceAliasDescriptions = async () => {
    if (!document.body.classList.contains("app-body")) return;
    if (!document.querySelector("[data-create-alias-dialog], [data-assign-dialog], .alias-row")) return;

    ensureAliasDescriptionStyles();

    const language = document.documentElement.lang?.toLowerCase().startsWith("de") ? "de" : "en";
    const copy = aliasDescriptionCopy[language];
    let descriptions = {};
    try {
      const response = await fetch("/aliases/private-descriptions", { headers: { Accept: "application/json" } });
      if (response.ok) {
        const payload = await response.json();
        descriptions = payload.descriptions || {};
      }
    } catch (error) {
      console.debug("Alias descriptions could not be loaded", error);
    }

    const createForm = document.querySelector("[data-create-alias-dialog] form");
    if (createForm) ensurePrivateDescriptionField(createForm, "", copy);

    const purposeLink = document.querySelector('.alias-table-head .alias-sort-link[href*="sort=purpose"]');
    if (purposeLink) replaceLinkText(purposeLink, copy.column);

    document.querySelectorAll('.alias-row [data-alias-select]').forEach((checkbox) => {
      const id = checkbox.value;
      const value = descriptions[id] || "";
      const row = checkbox.closest(".alias-row");
      addDescriptionPreview(row?.querySelector(".alias-info"), value, copy);

      const form = row?.querySelector('form[action$="/metadata"]');
      if (form) {
        ensureAliasAddress(form, checkbox.dataset.address || "", copy);
        ensurePrivateDescriptionField(form, value, copy);
      }
    });

    document.querySelectorAll("[data-assign-dialog]").forEach((dialog) => {
      const id = dialog.dataset.assignDialog;
      const form = dialog.querySelector("form");
      if (form) ensurePrivateDescriptionField(form, descriptions[id] || "", copy);
    });

    document.querySelectorAll(".offline-pool-row[data-alias-id]").forEach((row) => {
      addDescriptionPreview(
        row.querySelector(".alias-info"),
        descriptions[row.dataset.aliasId] || "",
        copy,
      );
    });
  };

  document.querySelectorAll(".service-badge").forEach((badge) => {
    if (!badge.querySelector(".ui-icon")) return;
    badge.classList.remove("service-badge");
    badge.classList.add("ui-marker-badge");
  });

  const restoreCopyIcon = (button) => {
    if (button.querySelector(".ui-icon") || button.textContent.trim()) return;
    button.append(createUiIcon("copy"));
  };

  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      const button = mutation.target.nodeType === Node.TEXT_NODE
        ? mutation.target.parentElement?.closest("[data-copy].icon-only")
        : mutation.target.closest?.("[data-copy].icon-only");
      if (!button) return;
      window.setTimeout(() => restoreCopyIcon(button), 0);
    });
  });

  document.querySelectorAll("[data-copy].icon-only").forEach((button) => {
    restoreCopyIcon(button);
    observer.observe(button, { childList: true, characterData: true, subtree: true });
  });

  enhanceBranding();
  document.querySelectorAll(".language-switch").forEach(enhanceLanguageSwitch);
  enhanceAliasDescriptions();

  document.addEventListener("click", (event) => {
    document.querySelectorAll("details[data-language-dropdown][open]").forEach((details) => {
      if (!details.contains(event.target)) details.removeAttribute("open");
    });
    document.querySelectorAll("details.alias-description-details[open]").forEach((details) => {
      if (!details.contains(event.target)) details.removeAttribute("open");
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    document.querySelectorAll("details[data-language-dropdown][open]").forEach((details) => {
      details.removeAttribute("open");
      details.querySelector("summary")?.focus();
    });
    document.querySelectorAll("details.alias-description-details[open]").forEach((details) => {
      details.removeAttribute("open");
      details.querySelector("summary")?.focus();
    });
  });
})();