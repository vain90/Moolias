(() => {
  "use strict";

  const menu = document.querySelector("[data-pool-create-menu]");
  const trigger = menu?.querySelector("[data-pool-create-trigger]");
  const popover = menu?.querySelector("[data-pool-create-popover]");
  if (!menu || !trigger || !popover) return;

  const close = () => {
    popover.hidden = true;
    trigger.setAttribute("aria-expanded", "false");
  };

  const open = () => {
    popover.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    popover.querySelector("button")?.focus();
  };

  trigger.addEventListener("click", (event) => {
    event.stopPropagation();
    if (popover.hidden) open();
    else close();
  });

  popover.addEventListener("click", (event) => event.stopPropagation());
  document.addEventListener("click", close);
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || popover.hidden) return;
    close();
    trigger.focus();
  });
})();
