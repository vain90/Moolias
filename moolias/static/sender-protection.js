(() => {
  "use strict";

  if (!document.body.classList.contains("app-body")) return;

  const language = document.documentElement.lang === "de" ? "de" : "en";
  const copy = {
    de: {
      protected: "Geschützt",
      unprotected: "Nicht geschützt",
      unavailable: "Nicht verfügbar",
      disabled: "Nicht aktiviert",
      external: "Extern geschützt",
      protectedDetail: "Primäradresse geschützt",
      unprotectedDetail: "Senden ist derzeit erlaubt",
      unavailableDetail: "Status kann nicht geprüft werden",
      disabledDetail: "Funktion ist serverseitig deaktiviert",
      externalDetail: "Durch bestehende Mailcow-Regel geschützt",
      cooldown: (seconds) => `Erneute Änderung in ${seconds} Sekunden möglich.`,
      missing: "Der Moolias Mailcow Agent wurde nicht gefunden.",
      authentication: "Der Mailcow Agent ist erreichbar, aber die Authentifizierung ist fehlgeschlagen.",
      unreachable: "Der Moolias Mailcow Agent ist momentan nicht erreichbar.",
      failed: "Die Änderung konnte nicht gespeichert werden.",
    },
    en: {
      protected: "Protected",
      unprotected: "Not protected",
      unavailable: "Unavailable",
      disabled: "Not enabled",
      external: "Protected externally",
      protectedDetail: "Primary address protected",
      unprotectedDetail: "Sending is currently allowed",
      unavailableDetail: "Status cannot be checked",
      disabledDetail: "Feature is disabled on the server",
      externalDetail: "Protected by an existing Mailcow rule",
      cooldown: (seconds) => `You can change this again in ${seconds} seconds.`,
      missing: "The Moolias Mailcow Agent was not found.",
      authentication: "The Mailcow agent is reachable, but authentication failed.",
      unreachable: "The Moolias Mailcow Agent is currently unreachable.",
      failed: "The change could not be saved.",
    },
  }[language];

  const section = document.querySelector("[data-sender-protection-settings]");
  const toggle = document.querySelector("[data-sender-protection-toggle]");
  const stateLabel = document.querySelector("[data-sender-protection-state]");
  const message = document.querySelector("[data-sender-protection-message]");
  const overviewState = document.querySelector("[data-primary-protection-state]");
  const overviewDetail = document.querySelector("[data-primary-protection-detail]");
  const action = document.querySelector("[data-primary-protection-action]");
  const actionCount = document.querySelector("[data-action-count]");
  const actionEmpty = document.querySelector("[data-action-empty]");

  if (!section || !toggle || !stateLabel || !message) return;

  let currentBlocked = false;
  let externallyManaged = false;
  let baseActionCount = Number.parseInt(actionCount?.textContent?.trim() || "0", 10) || 0;
  let protectionRequiresAction = false;
  let countdownTimer = null;

  const csrfToken = () => document.body.dataset.csrfToken || "";

  const setHidden = (element, hidden) => {
    if (!element) return;
    element.hidden = hidden;
    element.style.display = hidden ? "none" : "";
  };

  const syncActionRequired = (required) => {
    protectionRequiresAction = Boolean(required);
    setHidden(action, !protectionRequiresAction);
    const total = baseActionCount + (protectionRequiresAction ? 1 : 0);
    if (actionCount) actionCount.textContent = String(total);
    setHidden(actionEmpty, total > 0);
  };

  const syncOverview = (state, detail, attention = false) => {
    if (overviewState) overviewState.textContent = state;
    if (overviewDetail) overviewDetail.textContent = detail;
    document.querySelector("[data-primary-protection-card]")?.classList.toggle(
      "needs-attention",
      attention,
    );
  };

  const stopCountdown = () => {
    if (countdownTimer !== null) {
      window.clearInterval(countdownTimer);
      countdownTimer = null;
    }
  };

  const startCountdown = (seconds) => {
    stopCountdown();
    if (externallyManaged) {
      toggle.disabled = true;
      return;
    }
    let remaining = Math.max(0, Number.parseInt(seconds, 10) || 0);
    if (!remaining) {
      toggle.disabled = false;
      message.textContent = "";
      return;
    }
    toggle.disabled = true;
    message.textContent = copy.cooldown(remaining);
    countdownTimer = window.setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        stopCountdown();
        toggle.disabled = false;
        message.textContent = "";
        return;
      }
      message.textContent = copy.cooldown(remaining);
    }, 1000);
  };

  const applyState = ({ blocked, managed = true, retryAfter = 0 }) => {
    currentBlocked = Boolean(blocked);
    externallyManaged = managed === false;
    section.hidden = false;
    toggle.checked = currentBlocked;

    if (externallyManaged) {
      stateLabel.textContent = copy.external;
      syncOverview(copy.external, copy.externalDetail, false);
      syncActionRequired(false);
      message.textContent = copy.externalDetail;
    } else if (currentBlocked) {
      stateLabel.textContent = copy.protected;
      syncOverview(copy.protected, copy.protectedDetail, false);
      syncActionRequired(false);
      message.textContent = "";
    } else {
      stateLabel.textContent = copy.unprotected;
      syncOverview(copy.unprotected, copy.unprotectedDetail, true);
      syncActionRequired(true);
      message.textContent = "";
    }
    startCountdown(retryAfter);
  };

  const applyUnavailable = (reason) => {
    section.hidden = false;
    toggle.checked = false;
    toggle.disabled = true;
    stateLabel.textContent = copy.unavailable;
    syncOverview(copy.unavailable, copy.unavailableDetail, true);
    syncActionRequired(true);
    message.textContent = reason === "not-installed"
      ? copy.missing
      : reason === "authentication"
        ? copy.authentication
        : copy.unreachable;
  };

  const applyDisabled = () => {
    section.hidden = true;
    syncOverview(copy.disabled, copy.disabledDetail, false);
    syncActionRequired(false);
  };

  const load = async () => {
    try {
      const response = await fetch("/aliases/sender-protection", {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) {
        applyUnavailable("unreachable");
        return;
      }
      const data = await response.json();
      if (!data.enabled) {
        applyDisabled();
        return;
      }
      if (!data.available) {
        applyUnavailable(data.reason);
        return;
      }
      applyState({
        blocked: data.blocked,
        managed: data.managed,
        retryAfter: data.retry_after || 0,
      });
    } catch (_error) {
      applyUnavailable("unreachable");
    }
  };

  const save = async () => {
    if (externallyManaged) {
      applyState({ blocked: true, managed: false });
      return;
    }

    const requested = toggle.checked;
    toggle.disabled = true;
    message.textContent = "";
    try {
      const response = await fetch("/aliases/sender-protection", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken(),
        },
        credentials: "same-origin",
        body: JSON.stringify({ blocked: requested }),
      });

      if (response.status === 409) {
        applyState({ blocked: true, managed: false });
        return;
      }
      if (response.status === 429) {
        toggle.checked = currentBlocked;
        startCountdown(response.headers.get("Retry-After") || "1");
        return;
      }
      if (!response.ok) throw new Error(`Protection update failed with HTTP ${response.status}`);

      const data = await response.json();
      applyState({
        blocked: data.blocked,
        managed: data.managed,
        retryAfter: data.retry_after || 0,
      });
    } catch (error) {
      console.error("Sender protection update failed", error);
      toggle.checked = currentBlocked;
      toggle.disabled = false;
      message.textContent = copy.failed;
    }
  };

  toggle.addEventListener("change", save);
  void load();
})();
