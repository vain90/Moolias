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
    summary.setAttribute("aria-label", nav.getAttribute("aria-label") || "Language");
    summary.append(createFlag(current.code));

    const currentLabel = document.createElement("span");
    currentLabel.className = "language-dropdown-current";
    currentLabel.textContent = current.label;
    summary.append(currentLabel, createUiIcon("chevron-down"));

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
        const selected = createUiIcon("check");
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
    document.querySelectorAll(".brand-mark").forEach((mark) => {
      if (mark.querySelector("img")) return;
      const image = document.createElement("img");
      image.src = "/static/icon-192.png?v=20260823-2";
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
      image.src = "/static/icon-192.png?v=20260823-2";
      image.alt = "";
      image.width = 88;
      image.height = 88;
      image.decoding = "async";
      hero.insertBefore(image, heading);
    }
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
