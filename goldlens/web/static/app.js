/* GoldLens app shell: charts, page transitions, settings drawer, small form helpers. */
(() => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const PLOT_CONFIG = { displayModeBar: false, responsive: true, scrollZoom: false };

  // Charts arrive as Plotly JSON inside <div class="plot"><script type="application/json">…</script></div>
  function renderPlots(root) {
    if (!window.Plotly) return;
    root.querySelectorAll(".plot:not([data-done])").forEach((el) => {
      const src = el.querySelector('script[type="application/json"]');
      if (!src) return;
      try {
        const fig = JSON.parse(src.textContent);
        el.dataset.done = "1";
        src.remove();
        Plotly.newPlot(el, fig.data, fig.layout, PLOT_CONFIG);
      } catch (e) { console.error("chart failed", e); }
    });
  }

  function animateIn(root) {
    if (reduce || !window.gsap) return;
    const items = root.querySelectorAll(".gl-sec, .gl-kpi, .gl-card, .gl-panel, .plot, .verdict, .checks .ck, .vs .c, .tbl-wrap, .phone");
    if (items.length) gsap.from(items, { y: 14, autoAlpha: 0, duration: .45, stagger: .035, ease: "power2.out", clearProps: "all" });
    const stamp = root.querySelector(".verdict .stamp");
    if (stamp) gsap.from(stamp, { scale: 2.6, rotation: -25, autoAlpha: 0, duration: .5, delay: .25, ease: "back.out(2.2)" });
  }

  function setActiveNav() {
    const page = location.pathname.split("/")[2] || "overview";
    document.querySelectorAll(".nav-i[data-page]").forEach((a) => a.classList.toggle("on", a.dataset.page === page));
  }

  // Curve-date slider shows the date it points at
  function wireSliders(root) {
    root.querySelectorAll('input[type=range][name="d"]').forEach((r) => {
      const out = r.parentElement.querySelector("output");
      const fmt = () => (out.textContent = `day ${Number(r.value) + 1} of ${Number(r.max) + 1}`);
      r.addEventListener("input", fmt); fmt();
    });
    root.querySelectorAll('input[type=range][name="tau"]').forEach((r) => {
      const out = r.parentElement.querySelector("output");
      const fmt = () => (out.textContent = `${r.value} d`);
      r.addEventListener("input", fmt); fmt();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    renderPlots(document); wireSliders(document); setActiveNav(); animateIn(document.getElementById("main"));
  });
  document.body.addEventListener("htmx:afterSwap", (e) => {
    renderPlots(e.detail.target); wireSliders(e.detail.target);
    if (e.detail.target.id === "main") { window.scrollTo({ top: 0 }); animateIn(e.detail.target); }
    else animateIn(e.detail.target);
  });
  document.body.addEventListener("htmx:afterSettle", setActiveNav);
  // The server names the page in an HX-Trigger header; keep the browser tab title in step
  document.body.addEventListener("pageChanged", (e) => {
    const link = document.querySelector(`.nav-i[data-page="${e.detail.value}"] span:last-child`);
    if (link) document.title = `GoldLens · ${link.textContent}`;
  });
  window.addEventListener("popstate", () => setTimeout(setActiveNav, 50));

  // Segmented buttons: highlight the clicked one
  document.body.addEventListener("click", (e) => {
    const b = e.target.closest(".seg button");
    if (b) b.parentElement.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    const fill = e.target.closest("[data-fill]");
    if (fill) { const t = document.querySelector(fill.dataset.fill); if (t) { t.value = fill.dataset.text; t.focus(); } }
    if (e.target.closest("[data-open]")) document.getElementById(e.target.closest("[data-open]").dataset.open).classList.add("open");
    if (e.target.closest("[data-close]")) e.target.closest(".drawer").classList.remove("open");
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") document.querySelectorAll(".drawer.open").forEach((d) => d.classList.remove("open")); });

  // Settings drawer: live value labels
  document.addEventListener("input", (e) => {
    const r = e.target;
    if (r.matches(".drawer input[type=range]")) {
      const out = document.querySelector(`[data-out="${r.name}"]`);
      if (out) out.textContent = r.value + (out.textContent.match(/[^\d.\-]+$/) || [""])[0];
    }
  });

  // Chat: clear the box after sending; keep the newest answer in view
  document.body.addEventListener("htmx:afterRequest", (e) => {
    const f = e.detail.elt.closest && e.detail.elt.closest("form[data-reset]");
    if (f && e.detail.successful) f.reset();
    if (e.detail.target && e.detail.target.id === "chat") e.detail.target.lastElementChild?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "end" });
  });
})();
