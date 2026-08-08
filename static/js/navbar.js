document.addEventListener("DOMContentLoaded", function () {

  /* ===============================
     SCROLL EFFECT (navbar shadow)
  =============================== */
  const navbar = document.getElementById("siteNavbar");

  window.addEventListener("scroll", function () {
    if (window.scrollY > 10) {
      navbar.classList.add("scrolled");
    } else {
      navbar.classList.remove("scrolled");
    }
  });


  /* ===============================
     USER DROPDOWN TOGGLE
  =============================== */
  const userDropdown = document.getElementById("userDropdown");
  const userBtn = document.getElementById("userDropdownBtn");

  if (userDropdown && userBtn) {
    userBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      userDropdown.toggleAttribute("data-open");
    });

    document.addEventListener("click", function () {
      userDropdown.removeAttribute("data-open");
    });
  }


  /* ===============================
     MOBILE DRAWER OPEN/CLOSE
  =============================== */
  const hamburger = document.getElementById("hamburgerBtn");
  const drawer = document.getElementById("mobileDrawer");
  const overlay = document.getElementById("drawerOverlay");
  const closeBtn = document.getElementById("drawerClose");

  function openDrawer() {
    drawer.classList.add("is-open");
    overlay.classList.add("is-open");
    hamburger.classList.add("is-active");
    document.body.classList.add("drawer-open");
    hamburger.setAttribute("aria-expanded", "true");
  }

  function closeDrawer() {
    drawer.classList.remove("is-open");
    overlay.classList.remove("is-open");
    hamburger.classList.remove("is-active");
    document.body.classList.remove("drawer-open");
    hamburger.setAttribute("aria-expanded", "false");
  }

  if (hamburger) hamburger.addEventListener("click", openDrawer);
  if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
  if (overlay) overlay.addEventListener("click", closeDrawer);

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      closeDrawer();
    }
  });


  /* ===============================
     AUTO CLOSE DRAWER ON LINK CLICK
  =============================== */
  const drawerLinks = document.querySelectorAll(".drawer-link");

  drawerLinks.forEach(link => {
    link.addEventListener("click", closeDrawer);
  });

});