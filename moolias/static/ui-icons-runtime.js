(() => {
  "use strict";

  document.querySelectorAll(".service-badge").forEach((badge) => {
    if (!badge.querySelector(".ui-icon")) return;
    badge.classList.remove("service-badge");
    badge.classList.add("ui-marker-badge");
  });

  const restoreCopyIcon = (button) => {
    if (button.querySelector(".ui-icon") || button.textContent.trim()) return;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.classList.add("ui-icon");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "/static/ui-icons.svg#icon-copy");
    svg.append(use);
    button.append(svg);
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
})();
