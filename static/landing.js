const dashboardBtn = document.getElementById("lp-dashboard-btn");
const ctaPrimary = document.getElementById("lp-cta-primary");
const ctaFinal = document.getElementById("lp-cta-final");
const signinLink = document.getElementById("lp-signin-link");

fetch("/auth/status")
  .then((r) => r.json())
  .then(({ logged_in }) => {
    if (!logged_in) return;
    dashboardBtn.style.display = "inline-flex";
    [ctaPrimary, ctaFinal].forEach((btn) => {
      btn.href = "/dashboard";
      btn.textContent = "Go to dashboard";
    });
    if (signinLink) signinLink.closest("p").style.display = "none";
  })
  .catch(() => {});
