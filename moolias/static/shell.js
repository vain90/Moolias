(() => {
  "use strict";

  const drawer = document.querySelector("[data-settings-drawer]");
  const backdrop = document.querySelector("[data-drawer-backdrop]");
  const accountButton = document.querySelector("[data-account-button]");
  const accountPopover = document.querySelector("[data-account-popover]");
  const sidebar = document.querySelector("[data-app-sidebar]");

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
  const serviceLogoKeysByLabel = new Map([
    ["Apple", "apple"],
    ["Booking.com", "booking"],
    ["Discord", "discord"],
    ["Dropbox", "dropbox"],
    ["eBay", "ebay"],
    ["Facebook", "facebook"],
    ["GitHub", "github"],
    ["GitLab", "gitlab"],
    ["Google", "google"],
    ["Instagram", "instagram"],
    ["Netflix", "netflix"],
    ["Notion", "notion"],
    ["PayPal", "paypal"],
    ["Reddit", "reddit"],
    ["Signal", "signal"],
    ["Spotify", "spotify"],
    ["Steam", "steam"],
    ["Stripe", "stripe"],
    ["Telegram", "telegram"],
    ["TikTok", "tiktok"],
    ["Twitch", "twitch"],
    ["X / Twitter", "x"],
    ["Zalando", "zalando"],
    ["Zoom", "zoom"],
  ]);
  const serviceLogoHints = [
    ["apple", ["apple", "icloud", "appstore"]],
    ["booking", ["booking", "booking.com"]],
    ["discord", ["discord"]],
    ["dropbox", ["dropbox"]],
    ["ebay", ["ebay"]],
    ["facebook", ["facebook", "meta"]],
    ["github", ["github"]],
    ["gitlab", ["gitlab"]],
    ["google", ["google", "gmail", "youtube"]],
    ["instagram", ["instagram"]],
    ["netflix", ["netflix"]],
    ["notion", ["notion"]],
    ["paypal", ["paypal"]],
    ["reddit", ["reddit"]],
    ["signal", ["signal"]],
    ["spotify", ["spotify"]],
    ["steam", ["steam"]],
    ["stripe", ["stripe"]],
    ["telegram", ["telegram"]],
    ["tiktok", ["tiktok"]],
    ["twitch", ["twitch"]],
    ["x", ["twitter", "x.com", "xcom"]],
    ["zalando", ["zalando"]],
    ["zoom", ["zoom"]],
  ];

  const inferServiceLogoKey = (badge) => {
    const explicit = badge.dataset.serviceIconKey || serviceLogoKeysByLabel.get(badge.title);
    if (explicit) return explicit;
    const row = badge.closest(".recent-alias-row");
    const haystack = row?.textContent?.toLowerCase() || "";
    for (const [key, hints] of serviceLogoHints) {
      if (hints.some((hint) => haystack.includes(hint))) return key;
    }
    return null;
  };

  const renderServiceBadge = (badge, key, glyph) => {
    if (!badge) return;
    const fallback = glyph || badge.dataset.serviceIconGlyph || badge.textContent.trim() || "?";
    badge.dataset.serviceIconGlyph = fallback;
    badge.dataset.serviceIconKey = key || "generic";
    badge.replaceChildren();

    if (!key || !serviceLogoKeys.has(key)) {
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
    use.setAttribute("href", `/static/service-icons.svg#service-${key}`);
    svg.append(use);
    badge.append(svg);
  };

  document.querySelectorAll(".service-badge").forEach((badge) => {
    renderServiceBadge(badge, inferServiceLogoKey(badge), badge.textContent.trim());
  });

  const openDrawer = (section = null) => {
    if (!drawer) return;
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
    renderServiceBadge(badge, icon.key, icon.glyph || "?");
  };

  document.querySelectorAll("[data-alias-icon-select]").forEach((select) => {
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

  const installServiceIconPicker = () => {
    if (!document.querySelector("[data-alias-icon-select]")) return;

    if (!document.querySelector("link[data-service-icon-picker-styles]")) {
      const stylesheet = document.createElement("link");
      stylesheet.rel = "stylesheet";
      stylesheet.href = "/static/service-icon-picker.css?v=20260822-1";
      stylesheet.dataset.serviceIconPickerStyles = "";
      document.head.append(stylesheet);
    }

    if (!document.querySelector("script[data-service-icon-picker-script]")) {
      const script = document.createElement("script");
      script.src = "/static/service-icon-picker.js?v=20260822-1";
      script.dataset.serviceIconPickerScript = "";
      document.body.append(script);
    }
  };

  installServiceIconPicker();
})();
