document.addEventListener("DOMContentLoaded", () => {
  
  const sb = document.querySelector(".tw-sidebar");
  const overlay = document.querySelector(".tw-overlay");
  document.querySelectorAll("[data-tw-sidebar]").forEach(btn => {
    btn.addEventListener("click", () => {
      sb?.classList.toggle("-translate-x-full");
      overlay?.classList.toggle("hidden");
    });
  });
  overlay?.addEventListener("click", () => {
    sb?.classList.add("-translate-x-full");
    overlay?.classList.add("hidden");
  });

  document.body.addEventListener("click", (e) => {
    const el = e.target.closest("[data-confirm]");
    if (!el) return;
    const msg = el.getAttribute("data-confirm") || "Are you sure?";
    if (!window.confirm(msg)) {
      e.preventDefault();
      e.stopPropagation();
    }
  });

  document.addEventListener("click", (e) => {
    const toggle = e.target.closest("[data-menu-toggle]");
    if (toggle) {
      const menu = toggle.parentElement.querySelector("[data-menu]");
      const open = document.querySelectorAll("[data-menu].open");
      open.forEach(m => {
        m.classList.remove("open");
        m.classList.add("hidden");
      });
      if (menu) {
        menu.classList.add("open");
        menu.classList.remove("hidden");
      }
      e.preventDefault();
    } else if (!e.target.closest("[data-menu]")) {
      document.querySelectorAll("[data-menu].open").forEach(m => {
        m.classList.remove("open");
        m.classList.add("hidden");
      });
    }
  });

  const todayCell = document.querySelector("[data-today='1']");
  if (todayCell) {
    todayCell.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
  }
});