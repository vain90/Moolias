(() => {
  "use strict";

  const STORAGE_KEY = "moolias-theme";
  const VALID_PREFERENCES = new Set(["system", "light", "dark"]);
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const root = document.documentElement;

  const polishStylesheet = document.createElement("link");
  polishStylesheet.rel = "stylesheet";
  polishStylesheet.href = "/static/ui-polish.css?v=20260822-1";
  polishStylesheet.dataset.uiPolishStyles = "";
  document.head.append(polishStylesheet);

  const storedPreference = () => {
    try {
      const value = window.localStorage.getItem(STORAGE_KEY);
      return VALID_PREFERENCES.has(value) ? value : "system";
    } catch (_error) {
      return "system";
    }
  };

  const resolvedTheme = (preference) => {
    if (preference === "system") {
      return media.matches ? "dark" : "light";
    }
    return preference;
  };

  const updateBrowserChrome = (theme) => {
    const themeColor = document.querySelector('meta[name="theme-color"]');
    if (themeColor) {
      themeColor.setAttribute("content", theme === "dark" ? "#101418" : "#f6f8fa");
    }

    const statusBar = document.querySelector('meta[name="apple-mobile-web-app-status-bar-style"]');
    if (statusBar) {
      statusBar.setAttribute("content", theme === "dark" ? "black-translucent" : "default");
    }
  };

  const applyTheme = (preference, persist = false) => {
    const normalized = VALID_PREFERENCES.has(preference) ? preference : "system";
    const theme = resolvedTheme(normalized);

    root.dataset.themePreference = normalized;
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    updateBrowserChrome(theme);

    const select = document.querySelector("[data-theme-select]");
    if (select && select.value !== normalized) {
      select.value = normalized;
    }

    if (persist) {
      try {
        window.localStorage.setItem(STORAGE_KEY, normalized);
      } catch (_error) {
        // The selected theme still applies for the current page when storage is unavailable.
      }
    }
  };

  let preference = storedPreference();
  applyTheme(preference);

  const bindThemeControl = () => {
    const select = document.querySelector("[data-theme-select]");
    if (!select) return;

    select.value = preference;
    select.addEventListener("change", () => {
      preference = VALID_PREFERENCES.has(select.value) ? select.value : "system";
      applyTheme(preference, true);
    });
  };

  const handleSystemThemeChange = () => {
    if (preference === "system") {
      applyTheme(preference);
    }
  };

  if (typeof media.addEventListener === "function") {
    media.addEventListener("change", handleSystemThemeChange);
  } else if (typeof media.addListener === "function") {
    media.addListener(handleSystemThemeChange);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindThemeControl, { once: true });
  } else {
    bindThemeControl();
  }
})();
