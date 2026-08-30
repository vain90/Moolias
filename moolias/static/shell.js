(() => {
  "use strict";

  const drawer = document.querySelector("[data-settings-drawer]");
  const backdrop = document.querySelector("[data-drawer-backdrop]");
  const accountButton = document.querySelector("[data-account-button]");
  const accountPopover = document.querySelector("[data-account-popover]");
  const sidebar = document.querySelector("[data-app-sidebar]");

  if (!document.querySelector("link[data-navigation-loading-styles]")) {
    const stylesheet = document.createElement("link");
    stylesheet.rel = "stylesheet";
    stylesheet.href = "/static/navigation-loading.css?v=20260830-1";
    stylesheet.dataset.navigationLoadingStyles = "";
    document.head.append(stylesheet);
  }

  const loadAccountDisplayName = async () => {
    if (!accountButton) return;
    const label = accountButton.querySelector(".account-email");
    const avatar = accountButton.querySelector(".account-avatar");
    if (!label) return;
    const mailbox = label.textContent.trim();
    try {
      const response = await fetch("/account/profile", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return;
      const payload = await response.json();
      const displayName = String(payload.display_name || "").trim();
      if (!displayName || displayName === mailbox) return;
      label.textContent = displayName;
      accountButton.title = mailbox;
      if (avatar) avatar.textContent = displayName.slice(0, 1).toUpperCase();
    } catch (error) {
      console.debug("Could not load mailbox display name", error);
    }
  };

  loadAccountDisplayName();

  const bundledLogoKeys = new Set([
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

  const generatedLogoKeys = new Set([
    "airbnb",
    "adidas",
    "aliexpress",
    "alipay",
    "americanexpress",
    "bitwarden",
    "buhl",
    "cloudflare",
    "cursor",
    "deezer",
    "deutschebahn",
    "dhl",
    "digitalocean",
    "dji",
    "dm",
    "docker",
    "duolingo",
    "etsy",
    "fedex",
    "figma",
    "fiverr",
    "freelancer",
    "galaxus",
    "gitea",
    "glassdoor",
    "hellofresh",
    "iberia",
    "ikea",
    "kickstarter",
    "kleinanzeigen",
    "komoot",
    "lastpass",
    "line",
    "linktree",
    "lufthansa",
    "mailchimp",
    "mastodon",
    "medium",
    "messenger",
    "meta",
    "nextcloud",
    "nordvpn",
    "otto",
    "patreon",
    "payback",
    "philipshue",
    "pinterest",
    "plex",
    "protonmail",
    "quora",
    "revolut",
    "samsung",
    "shazam",
    "shopify",
    "snapchat",
    "sonos",
    "soundcloud",
    "squarespace",
    "stackoverflow",
    "strava",
    "teamviewer",
    "threads",
    "trello",
    "tripadvisor",
    "tripcom",
    "tumblr",
    "uber",
    "unraid",
    "ups",
    "vimeo",
    "vinted",
    "vodafone",
    "volkswagen",
    "westernunion",
    "whatsapp",
    "wise",
    "wordpress",
    "yelp",
    "youtube",
  ]);

  const serviceLogoKeys = new Set([...bundledLogoKeys, ...generatedLogoKeys]);
  const labelKeyOverrides = new Map([
    ["bookingcom", "booking"],
    ["xtwitter", "x"],
    ["generisch", "generic"],
    ["generic", "generic"],
  ]);
  const specialLogoHints = new Map([
    ["dm", ["dm", "drogeriemarkt"]],
    ["dhl", ["dhl"]],
    ["line", ["line"]],
    ["x", ["twitter", "x.com", "xcom"]],
  ]);

  const logoHref = (key) => {
    if (generatedLogoKeys.has(key)) {
      return `/static/service-icons.generated.svg#service-${key}`;
    }
    if (bundledLogoKeys.has(key)) {
      return `/static/service-icons.svg#service-${key}`;
    }
    return null;
  };

  window.MooliasServiceLogos = {
    has: (key) => serviceLogoKeys.has(key),
    href: logoHref,
  };

  const keyFromLabel = (label) => {
    const normalized = (label || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
    return labelKeyOverrides.get(normalized) || (serviceLogoKeys.has(normalized) ? normalized : null);
  };

  const inferServiceLogoKey = (badge) => {
    const explicit = badge.dataset.serviceIconKey || keyFromLabel(badge.title);
    if (explicit) return explicit;

    const row = badge.closest(".recent-alias-row");
    const haystack = row?.textContent?.toLowerCase() || "";
    const normalized = haystack.replace(/[^a-z0-9]+/g, "");
    const tokens = new Set(haystack.split(/[^a-z0-9]+/).filter(Boolean));

    for (const [key, hints] of specialLogoHints) {
      if (hints.some((hint) => tokens.has(hint) || haystack.includes(hint))) return key;
    }
    for (const key of [...serviceLogoKeys].sort((left, right) => right.length - left.length)) {
      if (key.length >= 4 && normalized.includes(key)) return key;
      if (tokens.has(key)) return key;
    }
    return null;
  };

  const renderServiceBadge = (badge, key, glyph) => {
    if (!badge) return;
    const fallback = glyph || badge.dataset.serviceIconGlyph || badge.textContent.trim() || "AL";
    badge.dataset.serviceIconGlyph = fallback;
    badge.dataset.serviceIconKey = key || "generic";
    badge.replaceChildren();

    const href = key ? logoHref(key) : null;
    if (!href) {
      badge.textContent = fallback;
      return;
    }

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.classList.add("service-logo");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "18");
    svg.setAttribute("height", "18");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", href);
    svg.append(use);
    badge.append(svg);
  };

  const enhanceServiceBadges = (root = document) => {
    root.querySelectorAll(".service-badge").forEach((badge) => {
      renderServiceBadge(badge, inferServiceLogoKey(badge), badge.textContent.trim());
    });
  };

  enhanceServiceBadges();

  const copiedLabel = document.body.dataset.copiedLabel || "Copied";
  const copyFeedbackObserver = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      const button = mutation.target.nodeType === Node.TEXT_NODE
        ? mutation.target.parentElement?.closest("[data-copy]")
        : mutation.target.closest?.("[data-copy]");
      if (!button || button.textContent.trim() !== copiedLabel) return;
      button.textContent = "✓";
      button.classList.add("copy-success");
      window.setTimeout(() => button.classList.remove("copy-success"), 850);
    });
  });
  copyFeedbackObserver.observe(document.body, {
    subtree: true,
    childList: true,
    characterData: true,
  });

  const installAliasHeaderSorting = () => {
    const head = document.querySelector(".alias-table-head");
    if (!head) return;

    const cells = [...head.children];
    if (cells.length < 6) return;

    const params = new URLSearchParams(window.location.search);
    let activeSort = params.get("sort") || "attention";
    if (activeSort === "most_used") activeSort = "usage";
    const activeDirection = params.get("direction") === "asc" ? "asc" : "desc";
    const definitions = [
      { index: 1, key: "purpose", defaultDirection: "asc" },
      { index: 2, key: "status", defaultDirection: "asc" },
      { index: 3, key: "usage", defaultDirection: "desc" },
      { index: 4, key: "last_used", defaultDirection: "desc" },
    ];

    head.removeAttribute("aria-hidden");
    head.setAttribute("role", "row");
    cells.forEach((cell) => cell.setAttribute("role", "columnheader"));

    definitions.forEach(({ index, key, defaultDirection }) => {
      const cell = cells[index];
      if (!cell) return;
      const label = cell.textContent.trim();
      const isActive = activeSort === key;
      const nextDirection = isActive
        ? (activeDirection === "asc" ? "desc" : "asc")
        : defaultDirection;
      const nextParams = new URLSearchParams(params);
      nextParams.set("sort", key);
      nextParams.set("direction", nextDirection);
      nextParams.delete("page");

      const link = document.createElement("a");
      link.className = `alias-sort-link${isActive ? " current" : ""}`;
      link.href = `${window.location.pathname}?${nextParams.toString()}`;
      link.textContent = label;
      link.setAttribute(
        "aria-label",
        `${label}, ${nextDirection === "asc" ? "ascending" : "descending"}`,
      );

      const arrow = document.createElement("span");
      arrow.className = "alias-sort-arrow";
      arrow.setAttribute("aria-hidden", "true");
      arrow.textContent = isActive ? (activeDirection === "asc" ? "↑" : "↓") : "↕";
      link.append(arrow);
      cell.replaceChildren(link);
      if (isActive) {
        cell.setAttribute("aria-sort", activeDirection === "asc" ? "ascending" : "descending");
      }
    });

    document.querySelector(".sort-controls")?.setAttribute("hidden", "");

    if (!document.querySelector("link[data-alias-enhancements-styles]")) {
      const stylesheet = document.createElement("link");
      stylesheet.rel = "stylesheet";
      stylesheet.href = "/static/alias-enhancements.css?v=20260822-2";
      stylesheet.dataset.aliasEnhancementsStyles = "";
      document.head.append(stylesheet);
    }
  };

  installAliasHeaderSorting();

  const openDrawer = (section = null) => {
    if (!drawer) return;
    sidebar?.classList.remove("open");
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
    if (backdrop) backdrop.hidden = false;
    document.documentElement.classList.add("drawer-open");

    if (section === "protection") {
      window.requestAnimationFrame(() => {
        drawer.querySelector("[data-sender-protection-settings]")?.scrollIntoView({
          block: "nearest",
        });
      });
    }
  };

  const closeDrawer = () => {
    if (!drawer) return;
    drawer.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
    if (backdrop) backdrop.hidden = true;
    document.documentElement.classList.remove("drawer-open");
  };

  document.querySelectorAll("[data-open-settings]").forEach((button) => {
    button.addEventListener("click", () => openDrawer());
  });

  document.querySelectorAll("[data-open-settings-section]").forEach((button) => {
    button.addEventListener("click", () => openDrawer(button.dataset.openSettingsSection));
  });

  document.querySelector("[data-close-settings]")?.addEventListener("click", closeDrawer);
  backdrop?.addEventListener("click", () => {
    closeDrawer();
    sidebar?.classList.remove("open");
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeDrawer();
    if (accountPopover && !accountPopover.hidden) {
      accountPopover.hidden = true;
      accountButton?.setAttribute("aria-expanded", "false");
    }
    sidebar?.classList.remove("open");
  });

  accountButton?.addEventListener("click", (event) => {
    event.stopPropagation();
    if (!accountPopover) return;
    const willOpen = accountPopover.hidden;
    accountPopover.hidden = !willOpen;
    accountButton.setAttribute("aria-expanded", String(willOpen));
  });

  accountPopover?.addEventListener("click", (event) => event.stopPropagation());
  document.addEventListener("click", () => {
    if (!accountPopover || accountPopover.hidden) return;
    accountPopover.hidden = true;
    accountButton?.setAttribute("aria-expanded", "false");
  });

  document.querySelector("[data-mobile-nav]")?.addEventListener("click", () => {
    if (!sidebar) return;
    sidebar.classList.toggle("open");
    if (backdrop) backdrop.hidden = !sidebar.classList.contains("open");
  });

  const themeSelect = document.querySelector("[data-theme-select]");
  const themeButtons = [...document.querySelectorAll("[data-theme-choice]")];

  const syncThemeButtons = () => {
    const current = document.documentElement.dataset.themePreference || themeSelect?.value || "system";
    themeButtons.forEach((button) => {
      const selected = button.dataset.themeChoice === current;
      button.classList.toggle("current", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
  };

  themeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (!themeSelect) return;
      themeSelect.value = button.dataset.themeChoice || "system";
      themeSelect.dispatchEvent(new Event("change", { bubbles: true }));
      window.requestAnimationFrame(syncThemeButtons);
    });
  });

  syncThemeButtons();
  window.setTimeout(syncThemeButtons, 0);

  const createAliasDialog = document.querySelector("[data-create-alias-dialog]");
  document.querySelector("[data-open-create-alias]")?.addEventListener("click", () => {
    if (!createAliasDialog) return;
    createAliasDialog.showModal();
    createAliasDialog.querySelector('input[name="description"]')?.focus();
  });
  createAliasDialog?.querySelector("[data-close-create-alias]")?.addEventListener("click", () => {
    createAliasDialog.close();
  });
  createAliasDialog?.addEventListener("click", (event) => {
    if (event.target === createAliasDialog) createAliasDialog.close();
  });

  document.querySelectorAll("[data-auto-submit]").forEach((control) => {
    control.addEventListener("change", () => control.form?.submit());
  });

  const updateServiceBadge = (aliasId, icon) => {
    const badge = document.querySelector(`[data-service-icon-for="${CSS.escape(String(aliasId))}"]`);
    if (!badge || !icon) return;
    [...badge.classList]
      .filter((className) => className.startsWith("tone-"))
      .forEach((className) => badge.classList.remove(className));
    badge.classList.add(`tone-${icon.tone || "neutral"}`);
    badge.title = icon.label || "";
    renderServiceBadge(badge, icon.key, icon.glyph || "AL");
  };

  const bindAliasIconSelects = (root = document) => {
    root.querySelectorAll("[data-alias-icon-select]").forEach((select) => {
      if (select.dataset.iconUpdateBound === "true") return;
      select.dataset.iconUpdateBound = "true";
      select.addEventListener("change", async () => {
        const aliasId = select.dataset.aliasId;
        const csrf = document.body.dataset.csrfToken || "";
        if (!aliasId || !csrf) return;

        const payload = new FormData();
        payload.append("csrf_token", csrf);
        payload.append("icon_key", select.value);
        select.disabled = true;
        try {
          const response = await fetch(`/aliases/${encodeURIComponent(aliasId)}/icon`, {
            method: "POST",
            body: payload,
            credentials: "same-origin",
            headers: { Accept: "application/json" },
          });
          if (!response.ok) throw new Error(`Icon update failed with HTTP ${response.status}`);
          const data = await response.json();
          updateServiceBadge(aliasId, data.icon);
        } catch (error) {
          console.error("Could not update alias icon", error);
        } finally {
          select.disabled = false;
        }
      });
    });
  };

  bindAliasIconSelects();

  const syncAliasQueryControls = () => {
    const search = document.querySelector("[data-live-search]");
    if (!search) return;
    const query = search.value.trim();

    document.querySelectorAll(".status-filters a, .alias-sort-link").forEach((link) => {
      const url = new URL(link.href, window.location.href);
      if (query) url.searchParams.set("q", query);
      else url.searchParams.delete("q");
      url.searchParams.delete("page");
      link.href = `${url.pathname}${url.search}${url.hash}`;
    });

    document.querySelectorAll('.sort-controls input[name="q"]').forEach((input) => {
      input.value = query;
    });
  };

  const aliasResultsRegion = document.querySelector("[data-alias-results-region]");
  if (aliasResultsRegion) {
    new MutationObserver(() => {
      enhanceServiceBadges(aliasResultsRegion);
      bindAliasIconSelects(aliasResultsRegion);
      syncAliasQueryControls();
      document.dispatchEvent(new CustomEvent("moolias:alias-results-updated", {
        detail: { root: aliasResultsRegion },
      }));
    }).observe(aliasResultsRegion, { childList: true });
  }

  const navigationPaths = new Set([
    "/overview",
    "/aliases",
    "/offline-pool",
    "/newsletters",
    "/statistics",
  ]);
  let navigationPendingTimer = null;

  const clearNavigationPending = () => {
    if (navigationPendingTimer !== null) {
      window.clearTimeout(navigationPendingTimer);
      navigationPendingTimer = null;
    }
    document.documentElement.classList.remove("navigation-pending");
    delete document.documentElement.dataset.navigationTarget;
    document.querySelector(".app-main")?.removeAttribute("aria-busy");
  };

  const beginNavigationPending = (url) => {
    if (!navigationPaths.has(url.pathname)) return false;
    const target = url.pathname === "/offline-pool"
      ? "offline-pool"
      : url.pathname.slice(1);
    document.documentElement.dataset.navigationTarget = target;
    document.documentElement.classList.add("navigation-pending");
    document.querySelector(".app-main")?.setAttribute("aria-busy", "true");
    navigationPendingTimer = window.setTimeout(clearNavigationPending, 12000);
    return true;
  };

  window.addEventListener("click", (event) => {
    if (
      event.defaultPrevented
      || event.button !== 0
      || event.metaKey
      || event.ctrlKey
      || event.shiftKey
      || event.altKey
    ) return;

    const link = event.target.closest("a[href]");
    if (!link || link.target || link.hasAttribute("download")) return;

    const url = new URL(link.href, window.location.href);
    if (url.origin !== window.location.origin || !navigationPaths.has(url.pathname)) return;
    if (
      url.pathname === window.location.pathname
      && url.search === window.location.search
      && url.hash === window.location.hash
    ) return;
    if (
      url.pathname === window.location.pathname
      && url.search === window.location.search
      && url.hash
    ) return;

    beginNavigationPending(url);
  });

  window.addEventListener("pageshow", clearNavigationPending);

  const installServiceIconPicker = () => {
    if (!document.querySelector("[data-alias-icon-select]")) return;

    if (!document.querySelector("link[data-service-icon-picker-styles]")) {
      const stylesheet = document.createElement("link");
      stylesheet.rel = "stylesheet";
      stylesheet.href = "/static/service-icon-picker.css?v=20260822-3";
      stylesheet.dataset.serviceIconPickerStyles = "";
      document.head.append(stylesheet);
    }

    if (!document.querySelector("script[data-service-icon-picker-script]")) {
      const script = document.createElement("script");
      script.src = "/static/service-icon-picker.js?v=20260822-3";
      script.dataset.serviceIconPickerScript = "";
      document.body.append(script);
    }
  };

  installServiceIconPicker();
})();
