(() => {
  "use strict";

  const user = (document.body.dataset.tourUser || "").trim().toLowerCase();
  if (!user) return;

  const language = document.documentElement.lang?.toLowerCase().startsWith("de") ? "de" : "en";
  const userKey = encodeURIComponent(user);
  const completedKey = `moolias:onboarding:v1:${userKey}`;
  const inviteKey = `moolias:onboarding-invite:v1:${userKey}`;
  const activeKey = `moolias:onboarding-active:v1:${userKey}`;

  const copy = {
    de: {
      inviteTitle: "Neu bei Moolias?",
      inviteBody: "In etwa zwei Minuten zeigen wir dir, warum Aliase sinnvoll sind und wo du die wichtigsten Funktionen findest.",
      start: "Tour starten",
      later: "Nicht jetzt",
      next: "Weiter",
      back: "Zurück",
      skip: "Überspringen",
      finish: "Fertig",
      step: "Schritt",
      steps: [
        {
          path: "/overview",
          title: "Warum Moolias?",
          body: "Deine echte Mailbox-Adresse bleibt privat. Stattdessen bekommt jeder Shop, Dienst oder Newsletter eine eigene Alias-Adresse. Alle Nachrichten landen trotzdem in deinem normalen Postfach.",
        },
        {
          path: "/overview",
          target: ".overview-metrics",
          title: "Deine Übersicht",
          body: "Hier siehst du auf einen Blick deine Aliase, den Offline-Vorrat und den Schutz deiner Hauptadresse. Die Karten führen direkt zu den jeweiligen Bereichen.",
        },
        {
          path: "/overview",
          target: "[data-primary-protection-card]",
          title: "Hauptadresse schützen",
          body: "Ist der Schutz aktiv, kann deine echte Mailbox-Adresse nicht versehentlich als Absender verwendet werden. Empfangen kannst du darüber weiterhin ganz normal.",
        },
        {
          path: "/aliases",
          target: "[data-open-create-alias]",
          title: "Für jeden Dienst ein Alias",
          body: "Erstelle zum Beispiel für Amazon, ein Hotel oder einen Newsletter jeweils eine eigene Adresse. So erkennst du später sofort, woher eine unerwünschte Nachricht kommt.",
        },
        {
          path: "/aliases",
          target: "[data-open-create-alias]",
          title: "Neuen Alias erstellen",
          body: "Du gibst einen Zweck an und Moolias erzeugt auf Wunsch eine lesbare Adresse. Alternativ kannst du eine zufällige oder eigene Adresse wählen und sie optional in SOGo als Absender freigeben.",
        },
        {
          path: "/aliases",
          target: ".alias-management-card",
          title: "Aliase verwalten",
          body: "Hier kannst du Adressen kopieren, suchen, deaktivieren oder ersetzen und Zweck, Symbol sowie SOGo-Sichtbarkeit ändern. Wird ein Alias problematisch, musst du nicht deine echte Adresse ändern.",
        },
        {
          path: "/offline-pool",
          target: "[data-pool-create-menu]",
          title: "Offline-Pool",
          body: "Der Offline-Pool ist dein Vorrat für Situationen, in denen du schnell eine neue Adresse brauchst, ohne Moolias zu öffnen. Du kannst mehrere zufällige Aliase vorab erzeugen.",
        },
        {
          path: "/offline-pool",
          target: ".pool-card",
          title: "Später den Zweck zuordnen",
          body: "Nimm unterwegs einfach eine vorbereitete Adresse. Wenn sie benutzt wurde, ordnest du später nur noch den Zweck zu. Die Adresse selbst bleibt dabei unverändert.",
        },
        {
          path: "/statistics",
          target: ".statistics-metrics, .statistics-disabled-state",
          title: "Optionale Nutzungsstatistiken",
          body: "Wenn dein Administrator Statistiken aktiviert hat, kann Moolias Nutzung zählen und – je nach Datenschutzmodus – Absender-Domains oder einzelne Absender anzeigen. Du bestimmst den Modus in den Einstellungen.",
        },
        {
          path: "/statistics",
          target: ".statistics-metrics, .statistics-disabled-state",
          title: "Nicht erkannte Absender",
          body: "Passt ein Absender nicht eindeutig zum bekannten Alias-Zweck, kann Moolias ihn zur Prüfung markieren. Das ist ein Hinweis für dich und ausdrücklich kein automatisches Spam-Urteil.",
        },
        {
          path: "/overview",
          target: "[data-action-rail]",
          title: "Handlungsbedarf",
          body: "Hier sammelt Moolias Dinge, die deine Aufmerksamkeit verdienen: etwa eine ungeschützte Hauptadresse, benutzte Offline-Aliase oder Absender, die du prüfen solltest.",
        },
        {
          path: "/overview",
          target: "[data-open-settings]",
          title: "Einstellungen",
          body: "Über das Zahnrad änderst du Darstellung, Statistikmodus und – falls installiert – den Schutz deiner Hauptadresse. Änderungen werden dort direkt erklärt.",
        },
        {
          path: "/overview",
          target: "[data-open-help-dialog]",
          title: "Hilfe ist immer erreichbar",
          body: "Unter dem Fragezeichen findest du Moolias noch einmal in einfacher Sprache erklärt. Von dort kannst du diese Tour jederzeit erneut starten.",
        },
      ],
    },
    en: {
      inviteTitle: "New to Moolias?",
      inviteBody: "In about two minutes, we’ll show you why aliases are useful and where to find the most important features.",
      start: "Start tour",
      later: "Not now",
      next: "Next",
      back: "Back",
      skip: "Skip",
      finish: "Done",
      step: "Step",
      steps: [
        {
          path: "/overview",
          title: "Why Moolias?",
          body: "Your real mailbox address stays private. Instead, each shop, service or newsletter gets its own alias address. All messages still arrive in your normal mailbox.",
        },
        {
          path: "/overview",
          target: ".overview-metrics",
          title: "Your overview",
          body: "See your aliases, offline pool and primary-address protection at a glance. The cards take you directly to the corresponding areas.",
        },
        {
          path: "/overview",
          target: "[data-primary-protection-card]",
          title: "Protect your primary address",
          body: "When protection is enabled, your real mailbox address cannot accidentally be used as a sender. Receiving mail through it continues to work normally.",
        },
        {
          path: "/aliases",
          target: "[data-open-create-alias]",
          title: "One alias for every service",
          body: "Create a separate address for Amazon, a hotel, a newsletter or any other service. If unwanted mail appears later, you immediately know which address was involved.",
        },
        {
          path: "/aliases",
          target: "[data-open-create-alias]",
          title: "Create a new alias",
          body: "Add a purpose and let Moolias generate a readable address, choose a random one or enter your own. You can also make the alias available as a sender in SOGo.",
        },
        {
          path: "/aliases",
          target: ".alias-management-card",
          title: "Manage aliases",
          body: "Copy, search, disable or replace addresses and change their purpose, icon and SOGo visibility. If one alias becomes a problem, your real address does not need to change.",
        },
        {
          path: "/offline-pool",
          target: "[data-pool-create-menu]",
          title: "Offline pool",
          body: "The offline pool keeps spare addresses ready for moments when you need a new address without opening Moolias. You can prepare several random aliases in advance.",
        },
        {
          path: "/offline-pool",
          target: ".pool-card",
          title: "Assign the purpose later",
          body: "Use a prepared address while you are away. Once it has been used, simply assign its purpose later. The address itself stays unchanged.",
        },
        {
          path: "/statistics",
          target: ".statistics-metrics, .statistics-disabled-state",
          title: "Optional usage statistics",
          body: "If your administrator enables statistics, Moolias can count usage and – depending on the privacy mode – show sender domains or individual senders. You choose the mode in Settings.",
        },
        {
          path: "/statistics",
          target: ".statistics-metrics, .statistics-disabled-state",
          title: "Unrecognized senders",
          body: "If a sender does not clearly match an alias purpose, Moolias can flag it for your review. This is a hint for you, not an automatic spam verdict.",
        },
        {
          path: "/overview",
          target: "[data-action-rail]",
          title: "Action required",
          body: "Moolias collects items that deserve your attention here, such as an unprotected primary address, used offline aliases or senders that should be reviewed.",
        },
        {
          path: "/overview",
          target: "[data-open-settings]",
          title: "Settings",
          body: "Use the gear to change appearance, statistics mode and – when installed – primary-address protection. The settings explain what each option changes.",
        },
        {
          path: "/overview",
          target: "[data-open-help-dialog]",
          title: "Help is always available",
          body: "The question mark explains Moolias again in plain language. You can also restart this tour from there whenever you want.",
        },
      ],
    },
  }[language];

  let overlay = null;
  let highlight = null;
  let popover = null;
  let activeIndex = null;
  let target = null;

  const currentPath = () => window.location.pathname.replace(/\/+$/, "") || "/";

  const clamp = (value, min, max) => Math.max(min, Math.min(value, max));

  const removeTourUi = () => {
    overlay?.remove();
    highlight?.remove();
    popover?.remove();
    overlay = null;
    highlight = null;
    popover = null;
    target = null;
    document.documentElement.classList.remove("tour-open");
  };

  const completeTour = () => {
    localStorage.setItem(completedKey, "1");
    localStorage.setItem(inviteKey, "1");
    sessionStorage.removeItem(activeKey);
    activeIndex = null;
    removeTourUi();
  };

  const setShadeRect = (element, top, left, width, height) => {
    element.style.top = `${Math.max(0, top)}px`;
    element.style.left = `${Math.max(0, left)}px`;
    element.style.width = `${Math.max(0, width)}px`;
    element.style.height = `${Math.max(0, height)}px`;
  };

  const positionUi = () => {
    if (!popover) return;

    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const margin = 14;

    if (!target) {
      overlay?.classList.add("tour-overlay-full");
      highlight?.setAttribute("hidden", "");
      popover.classList.add("tour-popover-centered");
      popover.style.left = `${Math.max(margin, (viewportWidth - popover.offsetWidth) / 2)}px`;
      popover.style.top = `${Math.max(margin, (viewportHeight - popover.offsetHeight) / 2)}px`;
      return;
    }

    overlay?.classList.remove("tour-overlay-full");
    popover.classList.remove("tour-popover-centered");
    highlight?.removeAttribute("hidden");

    const rect = target.getBoundingClientRect();
    const padding = 7;
    const hole = {
      top: clamp(rect.top - padding, 0, viewportHeight),
      left: clamp(rect.left - padding, 0, viewportWidth),
      right: clamp(rect.right + padding, 0, viewportWidth),
      bottom: clamp(rect.bottom + padding, 0, viewportHeight),
    };

    const shades = overlay ? [...overlay.querySelectorAll(".tour-shade")] : [];
    if (shades.length === 4) {
      setShadeRect(shades[0], 0, 0, viewportWidth, hole.top);
      setShadeRect(shades[1], hole.top, 0, hole.left, hole.bottom - hole.top);
      setShadeRect(shades[2], hole.top, hole.right, viewportWidth - hole.right, hole.bottom - hole.top);
      setShadeRect(shades[3], hole.bottom, 0, viewportWidth, viewportHeight - hole.bottom);
    }

    if (highlight) {
      highlight.style.top = `${hole.top}px`;
      highlight.style.left = `${hole.left}px`;
      highlight.style.width = `${hole.right - hole.left}px`;
      highlight.style.height = `${hole.bottom - hole.top}px`;
    }

    const popoverWidth = popover.offsetWidth;
    const popoverHeight = popover.offsetHeight;
    const gap = 14;
    let left;
    let top;

    if (hole.right + gap + popoverWidth <= viewportWidth - margin) {
      left = hole.right + gap;
      top = hole.top + (hole.bottom - hole.top - popoverHeight) / 2;
    } else if (hole.left - gap - popoverWidth >= margin) {
      left = hole.left - gap - popoverWidth;
      top = hole.top + (hole.bottom - hole.top - popoverHeight) / 2;
    } else if (hole.bottom + gap + popoverHeight <= viewportHeight - margin) {
      left = hole.left + (hole.right - hole.left - popoverWidth) / 2;
      top = hole.bottom + gap;
    } else {
      left = hole.left + (hole.right - hole.left - popoverWidth) / 2;
      top = hole.top - gap - popoverHeight;
    }

    popover.style.left = `${clamp(left, margin, viewportWidth - popoverWidth - margin)}px`;
    popover.style.top = `${clamp(top, margin, viewportHeight - popoverHeight - margin)}px`;
  };

  const renderStep = (index) => {
    if (index < 0 || index >= copy.steps.length) {
      completeTour();
      return;
    }

    const step = copy.steps[index];
    if (currentPath() !== step.path) {
      sessionStorage.setItem(activeKey, String(index));
      window.location.assign(step.path);
      return;
    }

    activeIndex = index;
    sessionStorage.setItem(activeKey, String(index));
    removeTourUi();
    document.documentElement.classList.add("tour-open");

    target = step.target ? document.querySelector(step.target) : null;
    if (target) {
      target.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" });
    }

    overlay = document.createElement("div");
    overlay.className = "tour-overlay";
    overlay.setAttribute("aria-hidden", "true");
    for (let i = 0; i < 4; i += 1) {
      const shade = document.createElement("div");
      shade.className = "tour-shade";
      overlay.append(shade);
    }

    highlight = document.createElement("div");
    highlight.className = "tour-highlight";
    highlight.setAttribute("aria-hidden", "true");

    popover = document.createElement("section");
    popover.className = "tour-popover";
    popover.setAttribute("role", "dialog");
    popover.setAttribute("aria-modal", "true");
    popover.setAttribute("aria-label", step.title);

    const progress = document.createElement("div");
    progress.className = "tour-progress";
    progress.textContent = `${copy.step} ${index + 1} / ${copy.steps.length}`;

    const title = document.createElement("h2");
    title.textContent = step.title;

    const body = document.createElement("p");
    body.textContent = step.body;

    const actions = document.createElement("div");
    actions.className = "tour-actions";

    const skip = document.createElement("button");
    skip.className = "tour-skip";
    skip.type = "button";
    skip.textContent = copy.skip;
    skip.addEventListener("click", completeTour);

    const navigation = document.createElement("div");
    navigation.className = "tour-navigation";

    if (index > 0) {
      const back = document.createElement("button");
      back.className = "button compact ghost";
      back.type = "button";
      back.textContent = copy.back;
      back.addEventListener("click", () => renderStep(index - 1));
      navigation.append(back);
    }

    const next = document.createElement("button");
    next.className = "button compact primary";
    next.type = "button";
    next.textContent = index === copy.steps.length - 1 ? copy.finish : copy.next;
    next.addEventListener("click", () => {
      if (index === copy.steps.length - 1) completeTour();
      else renderStep(index + 1);
    });
    navigation.append(next);

    actions.append(skip, navigation);
    popover.append(progress, title, body, actions);
    document.body.append(overlay, highlight, popover);

    window.requestAnimationFrame(() => {
      positionUi();
      next.focus();
    });
  };

  const startTour = () => {
    document.querySelector("[data-help-dialog]")?.close?.();
    document.querySelector("[data-tour-invite]")?.remove();
    localStorage.setItem(inviteKey, "1");
    sessionStorage.setItem(activeKey, "0");
    renderStep(0);
  };

  const showInvite = () => {
    if (currentPath() !== "/overview") return;
    if (localStorage.getItem(completedKey) || localStorage.getItem(inviteKey)) return;

    const invite = document.createElement("aside");
    invite.className = "tour-invite";
    invite.dataset.tourInvite = "";
    invite.setAttribute("aria-label", copy.inviteTitle);

    const title = document.createElement("strong");
    title.textContent = copy.inviteTitle;
    const body = document.createElement("p");
    body.textContent = copy.inviteBody;
    const actions = document.createElement("div");
    actions.className = "tour-invite-actions";

    const later = document.createElement("button");
    later.className = "button compact ghost";
    later.type = "button";
    later.textContent = copy.later;
    later.addEventListener("click", () => {
      localStorage.setItem(inviteKey, "1");
      invite.remove();
    });

    const start = document.createElement("button");
    start.className = "button compact primary";
    start.type = "button";
    start.textContent = copy.start;
    start.dataset.startTourInvite = "";
    start.addEventListener("click", startTour);

    actions.append(later, start);
    invite.append(title, body, actions);
    document.body.append(invite);
  };

  document.querySelectorAll("[data-start-tour]").forEach((button) => {
    button.addEventListener("click", startTour);
  });

  window.addEventListener("resize", positionUi);
  window.addEventListener("scroll", positionUi, true);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && activeIndex !== null) completeTour();
  });

  const savedIndex = Number.parseInt(sessionStorage.getItem(activeKey) || "", 10);
  if (Number.isInteger(savedIndex) && savedIndex >= 0 && savedIndex < copy.steps.length) {
    renderStep(savedIndex);
  } else {
    showInvite();
  }
})();
