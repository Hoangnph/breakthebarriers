// ── Date ──────────────────────────────────────────────────────────────────
document.getElementById("report-date").textContent =
  new Date().toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });

// ── KPI counter animation ──────────────────────────────────────────────────
function animateCounter(el) {
  const target = parseInt(el.dataset.count, 10);
  const duration = 900;
  const start = performance.now();
  function tick(now) {
    const elapsed = Math.min(now - start, duration);
    const eased = 1 - Math.pow(1 - elapsed / duration, 3);
    el.textContent = Math.round(eased * target);
    if (elapsed < duration) requestAnimationFrame(tick);
    else el.textContent = target;
  }
  requestAnimationFrame(tick);
}

// ── Progress bars ──────────────────────────────────────────────────────────
function animateBars() {
  document.querySelectorAll(".progress-fill").forEach(bar => {
    const width = bar.style.width;
    bar.style.width = "0";
    requestAnimationFrame(() => {
      requestAnimationFrame(() => { bar.style.width = width; });
    });
  });
}

// ── IntersectionObserver ───────────────────────────────────────────────────
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (!entry.isIntersecting) return;
    const el = entry.target;
    if (el.classList.contains("kpi-value")) animateCounter(el);
    if (el.classList.contains("progress-bar")) {
      el.querySelectorAll(".progress-fill").forEach(bar => {
        const width = bar.style.width;
        bar.style.width = "0";
        requestAnimationFrame(() => requestAnimationFrame(() => { bar.style.width = width; }));
      });
    }
    observer.unobserve(el);
  });
}, { threshold: 0.3 });

document.querySelectorAll(".kpi-value, .progress-bar").forEach(el => observer.observe(el));

// ── Tooltip on commit SHA hover ────────────────────────────────────────────
document.querySelectorAll(".commit-sha").forEach(el => {
  el.title = "Commit " + el.textContent;
  el.style.cursor = "default";
});
