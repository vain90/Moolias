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
      name: "Name",
      description: "Beschreibung",
      descriptionPlaceholder: "Optionaler Kontext, z. B. Rechnungen, Marketplace oder AWS",
      hint: "Optional. Die Beschreibung bleibt im privaten Mailcow-Kommentar und hilft Moolias vorsichtig bei der Absendererkennung.",
      column: "Name / Alias-Adresse",
    },
    en: {
      name: "Name",
      description: "Description",
      descriptionPlaceholder: "Optional context, for example invoices, Marketplace or AWS",
      hint: "Optional. The description stays in Mailcow's private comment and is used conservatively for sender recognition.",
      column: "Name / alias address",
    },
  };

  const replaceLabelText = (label, text) => {
    const textNode = [...label.childNodes].find((node) => node.nodeType === Node.TEXT_NODE);
    if (textNode) {
      textNode.textContent = text;
    } else {
      label.prepend(document.createTextNode(text));
    }
  };

  const ensurePrivateDescriptionField = (form, value, copy) => {
    if (form.querySelector('[name="private_description"]')) return;
    const nameInput = form.querySelector('input[name="description"]');
    const nameLabel = nameInput?.closest("label");
    if (!nameInput || !nameLabel) return;

    replaceLabelText(nameLabel, copy.name);

    const label = document.createElement("label");
    label.dataset.aliasPrivateDescriptionField = "1";
    label.append(document.createTextNode(copy.description));

    const textarea = document.createElement("textarea");
    textarea.name = "private_description";
    textarea.maxLength = 160;
    textarea.rows = 3;
    textarea.placeholder = copy.descriptionPlaceholder;
    textarea.value = value || "";
    label.append(textarea);

    const hint = document.createElement("p");
    hint.className = "hint";
    hint.dataset.aliasPrivateDescriptionHint = "1";
    hint.textContent = copy.hint;

    nameLabel.after(label, hint);
  };

  const addDescriptionPreview = (container, value) => {
    if (!container || !value || container.querySelector("[data-alias-private-description-preview]")) return;
    const preview = document.createElement("small");
    preview.className = "muted";
    preview.dataset.aliasPrivateDescriptionPreview = "1";
    preview.textContent = value;
    const address = container.querySelector("code");
    if (address) {
      container.insertBefore(preview, address);
    } else {
      container.append(preview);
    }
  };

  const enhanceAliasDescriptions = async () => {
    if (!document.body.classList.contains("app-body")) return;
    if (!document.querySelector("[data-create-alias-dialog], [data-assign-dialog], .alias-row")) return;

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

    const aliasColumn = document.querySelector(".alias-table-head span:nth-child(2)");
    if (aliasColumn) aliasColumn.textContent = copy.column;

    document.querySelectorAll('.alias-row [data-alias-select]').forEach((checkbox) => {
      const id = checkbox.value;
      const value = descriptions[id] || "";
      const row = checkbox.closest(".alias-row");
      addDescriptionPreview(row?.querySelector(".alias-info"), value);

      const form = row?.querySelector('form[action$="/metadata"]');
      if (form) ensurePrivateDescriptionField(form, value, copy);
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
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    document.querySelectorAll("details[data-language-dropdown][open]").forEach((details) => {
      details.removeAttribute("open");
      details.querySelector("summary")?.focus();
    });
  });
})();