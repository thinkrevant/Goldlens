/* GoldLens landing site. Every number comes from data.js, exported by scripts/export_site_data.py. */
(() => {
  // Edit these once the repo, deployed app and video exist.
  const LINKS = {
    github: "https://github.com/",
    // Served by `python -m goldlens.web`, the dashboard lives on the same site at /app.
    app: location.protocol.startsWith("http") ? "/app" : "http://127.0.0.1:8000/app",
    video: "#",
  };

  const D = window.GOLDLENS;
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const get = (path) => path.split(".").reduce((o, k) => (o == null ? o : o[k]), D);
  const SYMS = ["GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"];
  const COLOR = { GOLDM: "#E0B04A", GOLDTEN: "#5B8DEF", GOLDGUINEA: "#F07A8C", GOLDPETAL: "#3CC9A7" };
  const num = (v, d = 0) => Number(v).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
  const inr = (v) => {
    const s = v < 0 ? "−" : "";
    const a = Math.abs(v);
    return a >= 1e5 ? `${s}₹${(a / 1e5).toFixed(2)} lakh` : `${s}₹${num(a)}`;
  };
  const pct = (v) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}%`;

  $$(".js-link-github").forEach((a) => (a.href = LINKS.github));
  $$(".js-link-app").forEach((a) => (a.href = LINKS.app));
  $$(".js-link-video").forEach((a) => (a.href = LINKS.video));
  if (!D) return;

  // ---------------------------------------------------------------- static fills
  $$("[data-text]").forEach((el) => {
    const v = get(el.dataset.text);
    el.textContent = typeof v === "number" ? (Number.isInteger(v) ? num(v) : v.toFixed(2)) : v ?? "";
  });

  const S = D.series;
  const last = (arr) => arr[arr.length - 1];
  const tickerItems = SYMS.map((s) => {
    const a = S[s].px10, chg = S[s].day_chg ?? 0;
    return `<span class="it"><b>${s}</b><span>₹/10 g</span>₹${num(last(a))} <em class="${chg >= 0 ? "up" : "down"}">${chg >= 0 ? "▲" : "▼"} ${Math.abs(chg).toFixed(2)}%</em></span>`;
  });
  tickerItems.push(`<span class="it"><b>SPOT</b><span>implied · 999</span>₹${num(D.market.spot_implied)}</span>`,
    `<span class="it"><b>CARRY</b><span>annualised</span>${D.market.carry_pct.toFixed(2)}%</span>`,
    ...Object.entries(D.premiums_now).map(([k, v]) => `<span class="it"><b>${k}</b><span>vs GOLDM</span>${v > 0 ? "+" : ""}${v.toFixed(0)} bps</span>`),
    `<span class="it"><b>HONEST P&amp;L</b><span>after costs</span><em class="${last(D.ladder).net >= 0 ? "up" : "down"}">${inr(last(D.ladder).net)}</em></span>`);
  const track = $(".ticker .track");
  track.innerHTML = tickerItems.join("") + tickerItems.join("");
  $$(".ticker em").forEach((e) => (e.style.fontStyle = "normal"));

  // ---------------------------------------------------------------- morph chart
  const svg = $(".morph"), NS = "http://www.w3.org/2000/svg";
  const W = 800, H = 420, P = { l: 58, r: 12, t: 16, b: 28 };
  const all = (k) => SYMS.flatMap((s) => S[s][k]).filter((v) => v != null);
  const range = (vals, padFrac) => {
    const lo = Math.min(...vals), hi = Math.max(...vals), p = (hi - lo) * padFrac;
    return [lo - p, hi + p];
  };
  const qR = range(all("quoted"), 0.04), nR = range(all("px10"), 0.06);
  const n = S.dates.length;
  const X = (i) => P.l + (i * (W - P.l - P.r)) / (n - 1);
  const Y = (v, [lo, hi]) => P.t + (1 - (v - lo) / (hi - lo)) * (H - P.t - P.b);
  const pathFor = (vals, r) => vals.map((v, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(v, r).toFixed(1)}`).join(" ");
  const el = (tag, attrs, parent) => {
    const e = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
    parent && parent.appendChild(e);
    return e;
  };
  const kfmt = (v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : `${Math.round(v)}`);
  const grid = (r, cls) => {
    const g = el("g", { class: `grid ${cls}` }, svg);
    for (let i = 0; i <= 4; i++) {
      const v = r[0] + ((r[1] - r[0]) * i) / 4, y = Y(v, r);
      el("line", { x1: P.l, x2: W - P.r, y1: y, y2: y }, g);
      const t = el("text", { x: P.l - 8, y: y + 4, "text-anchor": "end" }, g);
      t.textContent = "₹" + kfmt(v);
    }
    return g;
  };
  const gQ = grid(qR, "gq"), gN = grid(nR, "gn");
  gN.style.opacity = 0;
  const [dFirst, dLast] = [S.dates[0], last(S.dates)];
  [[P.l, "start", dFirst], [W - P.r, "end", dLast]].forEach(([x, anchor, d]) => {
    const t = el("text", { x, y: H - 6, "text-anchor": anchor, class: "xl" }, svg);
    t.textContent = new Date(d).toLocaleDateString("en-IN", { month: "short", year: "numeric" });
    t.setAttribute("fill", "#5E6678");
    t.setAttribute("font-size", "14");
    t.setAttribute("font-family", "JetBrains Mono, monospace");
  });
  const paths = SYMS.map((s) => {
    const p = el("path", { class: "series", d: pathFor(S[s].quoted, qR), stroke: COLOR[s] }, svg);
    p.dataset.norm = pathFor(S[s].px10, nR);
    p.dataset.quoted = p.getAttribute("d");
    return p;
  });
  $(".legend").innerHTML = SYMS.map((s) => `<span><i style="background:${COLOR[s]}"></i>${s}</span>`).join("");

  // ---------------------------------------------------------------- honesty ladder list
  const NOTES = {
    "Naive": "1 lot vs 1 lot, stitched prices, same-day fills, no costs",
    "+ gram-matched sizing": "a spread, not a gold bet",
    "+ fill next day": "you can't trade at the price that made the signal",
    "+ past-only z-score": "no peeking at the future average",
    "+ real contracts & carry": "no fake jumps at expiry",
    "+ costs": "brokerage, fees, CTT, stamp duty, GST, slippage",
    "+ liquidity filter (honest)": "no trading on stale prices",
  };
  const ladderEl = $(".ladder");
  ladderEl.innerHTML = D.ladder.map((s, i) =>
    `<li class="${i === D.ladder.length - 1 ? "last" : ""}"><span><b>${s.name.replace(" (honest)", "")}</b><br><small class="muted">${NOTES[s.name] || ""}</small></span><span class="v">${inr(s.net)}</span></li>`).join("");
  const lis = $$("li", ladderEl);
  const maxNet = Math.max(...D.ladder.map((s) => s.net));
  const bigNum = $(".big-num"), meterStep = $(".meter-step"), barFill = $(".bar-fill");
  const renderLadder = (v, step) => {
    bigNum.textContent = inr(v);
    bigNum.classList.toggle("neg", v < 0);
    const k = Math.max(0, Math.min(D.ladder.length - 1, Math.round(step)));
    lis.forEach((li, i) => li.classList.toggle("on", i <= k));
    meterStep.textContent = k === D.ladder.length - 1 ? "Honest result, after real costs" : D.ladder[k].name.replace(/^\+ /, "+ ");
    barFill.style.transform = `scaleX(${Math.max(v, 0) / maxNet || 0.004})`;
  };

  // ---------------------------------------------------------------- tip checker content
  const T = D.tip;
  $(".tip-rule p").textContent = T.rule.charAt(0).toUpperCase() + T.rule.slice(1);
  $(".verdict h3").textContent = T.verdict;
  $(".flags").innerHTML = T.flags.map((f) => `<div>🚩 ${f}</div>`).join("");
  const setTipNumbers = (c, nv, h) => {
    $(".vs3 .claimed").textContent = `${Math.round(c)}%`;
    $(".vs3 .naive").textContent = pct(nv);
    $(".vs3 .honest").textContent = pct(h);
    $(".vs3 .naive").className = `naive ${nv >= 0 ? "up" : "down"}`;
    $(".vs3 .honest").className = `honest ${h >= 0 ? "up" : "down"}`;
  };

  // ---------------------------------------------------------------- phone message
  $(".phone .msg").innerHTML = D.morning_html.split("\n").map((l) => `<div class="ln">${l || "&nbsp;"}</div>`).join("");

  // ---------------------------------------------------------------- premium bars
  const pSvg = $(".premium-chart svg"), PW = 900, PH = 260, PP = { l: 44, r: 8, t: 14, b: 26 };
  const months = D.premiums.months, gV = D.premiums.GOLDGUINEA, pV = D.premiums.GOLDPETAL;
  const vals = [...gV, ...pV].filter((v) => v != null);
  const pLo = Math.min(0, ...vals), pHi = Math.max(...vals);
  const PY = (v) => PP.t + (1 - (v - pLo) / (pHi - pLo)) * (PH - PP.t - PP.b);
  const slot = (PW - PP.l - PP.r) / months.length, bw = Math.max(2, slot * 0.36);
  [0, 100, 200, 300].filter((v) => v <= pHi).concat(pLo < -100 ? [-100, -200] : []).forEach((v) => {
    el("line", { x1: PP.l, x2: PW - PP.r, y1: PY(v), y2: PY(v), stroke: v === 0 ? "#3A4458" : "#1B2332" }, pSvg);
    const t = el("text", { x: PP.l - 6, y: PY(v) + 3, "text-anchor": "end" }, pSvg);
    t.textContent = `${v > 0 ? "+" : ""}${v}`;
  });
  const bars = el("g", { class: "bar-g" }, pSvg);
  months.forEach((m, i) => {
    [[gV[i], COLOR.GOLDGUINEA, 0], [pV[i], COLOR.GOLDPETAL, 1]].forEach(([v, c, j]) => {
      if (v == null) return;
      const x = PP.l + i * slot + slot * 0.12 + j * bw, y0 = PY(0), y1 = PY(v);
      el("rect", { x, y: Math.min(y0, y1), width: bw - 1, height: Math.max(1, Math.abs(y1 - y0)), fill: c, opacity: .9 }, bars);
    });
    if (i % 6 === 0 || i === months.length - 1) {
      const t = el("text", { x: PP.l + i * slot + slot / 2, y: PH - 8, "text-anchor": "middle" }, pSvg);
      t.textContent = m;
    }
  });

  // ---------------------------------------------------------------- final states (no motion)
  const finalStates = () => {
    $(".steps").classList.add("static");
    paths.forEach((p) => p.setAttribute("d", p.dataset.norm));
    gQ.style.opacity = 0; gN.style.opacity = 1;
    $(".cap-mode").textContent = "Normalised by GoldLens";
    $$("[data-count]").forEach((e) => (e.textContent = num(get(e.dataset.count))));
    $$("[data-count-fixed]").forEach((e) => (e.textContent = e.dataset.countFixed));
    renderLadder(last(D.ladder).net, D.ladder.length - 1);
    $$("[data-bet]").forEach((e) => (e.textContent = `${D.attribution[e.dataset.bet] > 0 ? "+" : ""}${D.attribution[e.dataset.bet]} g`));
    const big = Math.max(Math.abs(D.attribution.naive_g), Math.abs(D.attribution.honest_g));
    $(".bet.bad i").style.transform = `scaleX(${Math.abs(D.attribution.naive_g) / big})`;
    $(".bet.good i").style.transform = `scaleX(${Math.abs(D.attribution.honest_g) / big})`;
    $(".tip-input .typed").textContent = T.text;
    setTipNumbers(T.claimed || 0, T.naive_ann, T.honest_ann);
  };

  if (!window.gsap || !window.ScrollTrigger) { finalStates(); return; }
  gsap.registerPlugin(ScrollTrigger);

  // Progress bar (always on, it's not motion-heavy)
  gsap.to(".progress", { scaleX: 1, ease: "none", scrollTrigger: { start: 0, end: "max", scrub: 0.3 } });

  const mm = gsap.matchMedia();
  mm.add({ reduce: "(prefers-reduced-motion: reduce)", motion: "(prefers-reduced-motion: no-preference)" }, (ctx) => {
    if (ctx.conditions.reduce) { finalStates(); return; }

    // ---- hero
    const hl = $$(".hero-lines .hl");
    hl.forEach((p) => { const L = p.getTotalLength(); gsap.set(p, { strokeDasharray: L, strokeDashoffset: L }); });
    const intro = gsap.timeline({ defaults: { ease: "power3.out" } });
    intro.from(".nav", { y: -30, autoAlpha: 0, duration: .6 })
      .from(".hero .eyebrow", { y: 16, autoAlpha: 0, duration: .5 }, "-=.2")
      .from(".headline .w", { yPercent: 60, autoAlpha: 0, duration: .9, stagger: .14 }, "-=.2")
      .to(hl, { strokeDashoffset: 0, duration: 2.2, stagger: .12, ease: "power2.inOut" }, "<")
      .from(".lede", { y: 18, autoAlpha: 0, duration: .6 }, "-=1.6")
      .from(".hero .cta .btn", { y: 14, autoAlpha: 0, duration: .5, stagger: .1 }, "-=1.2")
      .from(".stats > div", { y: 20, autoAlpha: 0, duration: .5, stagger: .08 }, "-=1")
      .from(".ticker", { autoAlpha: 0, duration: .6 }, "-=.6");
    $$("[data-count], [data-count-fixed]").forEach((e) => {
      const target = e.dataset.count ? get(e.dataset.count) : Number(e.dataset.countFixed);
      const o = { v: 0 };
      intro.to(o, { v: target, duration: 1.6, ease: "power2.out", onUpdate: () => (e.textContent = num(o.v)) }, 1.1);
    });
    gsap.to(".ticker .track", { xPercent: -50, ease: "none", duration: 60, repeat: -1 });
    gsap.to(".hero-lines", { yPercent: 18, ease: "none", scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: true } });

    // ---- problem: pinned morph
    const steps = $$(".step");
    gsap.set(steps.slice(1), { autoAlpha: 0, y: 30 });
    const mt = gsap.timeline({
      scrollTrigger: { trigger: ".problem", start: "top top", end: "+=1800", pin: true, scrub: 1, anticipatePin: 1 },
    });
    mt.to({}, { duration: .35 })
      .to(steps[0], { autoAlpha: 0, y: -30, duration: .25 })
      .to(steps[1], { autoAlpha: 1, y: 0, duration: .25 }, "<.1")
      .add(() => ($(".cap-mode").textContent = mt.scrollTrigger.direction > 0 ? "Normalised by GoldLens" : "As quoted on MCX"))
      .to(paths, { attr: { d: (i, t) => t.dataset.norm }, duration: 1, ease: "power2.inOut", stagger: .06 }, "<")
      .to(gQ, { opacity: 0, duration: .4 }, "<")
      .to(gN, { opacity: 1, duration: .4 }, "<.4")
      .to({}, { duration: .3 })
      .to(steps[1], { autoAlpha: 0, y: -30, duration: .25 })
      .to(steps[2], { autoAlpha: 1, y: 0, duration: .25 }, "<.1")
      .to(paths, { attr: { "stroke-width": 2.6 }, duration: .3 }, "<")
      .to({}, { duration: .3 });

    // ---- how cards
    gsap.set(".card", { y: 40, autoAlpha: 0 });
    ScrollTrigger.batch(".card", {
      start: "top 85%", once: true,
      onEnter: (b) => gsap.to(b, { y: 0, autoAlpha: 1, duration: .7, stagger: .12, ease: "power3.out" }),
    });
    $$(".section-title, .eyebrow:not(.hero .eyebrow)").forEach((e) =>
      gsap.from(e, { y: 24, autoAlpha: 0, duration: .7, ease: "power3.out", scrollTrigger: { trigger: e, start: "top 88%", once: true } }));

    // ---- honesty: pinned counter
    const proxy = { v: D.ladder[0].net, step: 0 };
    renderLadder(proxy.v, 0);
    const ht = gsap.timeline({
      scrollTrigger: { trigger: ".honesty", start: "top top", end: `+=${D.ladder.length * 420}`, pin: true, scrub: 1, anticipatePin: 1 },
    });
    D.ladder.slice(1).forEach((s, i) => {
      ht.to(proxy, { v: s.net, step: i + 1, duration: 1, ease: "power1.inOut", onUpdate: () => renderLadder(proxy.v, proxy.step) })
        .to({}, { duration: .25 });
    });

    // ---- gold bet
    const big = Math.max(Math.abs(D.attribution.naive_g), Math.abs(D.attribution.honest_g));
    const bt = gsap.timeline({ scrollTrigger: { trigger: ".goldbet", start: "top 70%", once: true } });
    [["naive_g", ".bet.bad"], ["honest_g", ".bet.good"]].forEach(([k, sel], j) => {
      const o = { v: 0 }, t = D.attribution[k], numEl = $(`${sel} .bet-num`);
      bt.from(sel, { y: 30, autoAlpha: 0, duration: .6, ease: "power3.out" }, j * .2)
        .to(o, { v: t, duration: 1.4, ease: "power2.out", onUpdate: () => (numEl.textContent = `${o.v > 0 ? "+" : ""}${Math.round(o.v)} g`) }, j * .2 + .3)
        .to(`${sel} i`, { scaleX: Math.abs(t) / big, duration: 1.4, ease: "power2.out" }, "<");
    });

    // ---- tip checker
    const typed = $(".tip-input .typed"), stamp = $(".stamp");
    typed.textContent = "";
    gsap.set([".tip-rule", ".verdict"], { autoAlpha: 0, y: 24 });
    gsap.set(stamp, { autoAlpha: 0, scale: 3, rotation: -30 });
    gsap.set(".flags div", { autoAlpha: 0, x: 20 });
    setTipNumbers(0, 0, 0);
    const chars = { n: 0 }, nums = { c: 0, nv: 0, h: 0 };
    const tt = gsap.timeline({ scrollTrigger: { trigger: ".tips", start: "top 60%", once: true } });
    tt.to(chars, { n: T.text.length, duration: Math.min(3.2, T.text.length / 38), ease: "none",
        onUpdate: () => (typed.textContent = T.text.slice(0, Math.round(chars.n))) })
      .to(".tip-rule", { autoAlpha: 1, y: 0, duration: .5, ease: "power3.out" }, "+=.2")
      .to(".verdict", { autoAlpha: 1, y: 0, duration: .5, ease: "power3.out" }, "+=.2")
      .to(nums, { c: T.claimed || 0, nv: T.naive_ann, h: T.honest_ann, duration: 1.2, ease: "power2.out",
        onUpdate: () => setTipNumbers(nums.c, nums.nv, nums.h) }, "<")
      .to(stamp, { autoAlpha: 1, scale: 1, rotation: -8, duration: .45, ease: "back.out(2.2)" }, "-=.4")
      .fromTo(".verdict", { x: -6 }, { x: 0, duration: .4, ease: "elastic.out(1, .3)", immediateRender: false }, "<.3")
      .to(".flags div", { autoAlpha: 1, x: 0, duration: .45, stagger: .15, ease: "power3.out" }, "-=.1");

    // ---- phone
    gsap.from(".phone", { y: 60, rotation: -3, autoAlpha: 0, duration: 1, ease: "power3.out",
      scrollTrigger: { trigger: ".brief", start: "top 70%", once: true } });
    gsap.from(".phone .ln", { autoAlpha: 0, y: 8, duration: .35, stagger: .07, ease: "power2.out",
      scrollTrigger: { trigger: ".brief", start: "top 55%", once: true } });
    gsap.from(".chips span", { autoAlpha: 0, y: 12, stagger: .08, duration: .4,
      scrollTrigger: { trigger: ".chips", start: "top 90%", once: true } });

    // ---- premium bars
    gsap.from(".premium-chart rect", { scaleY: 0, transformOrigin: "50% 100%", duration: .6, stagger: .015, ease: "power2.out",
      scrollTrigger: { trigger: ".premium-chart", start: "top 75%", once: true } });

    // ---- rigor + final
    gsap.set(".checks div", { y: 26, autoAlpha: 0 });
    ScrollTrigger.batch(".checks div", { start: "top 88%", once: true,
      onEnter: (b) => gsap.to(b, { y: 0, autoAlpha: 1, stagger: .08, duration: .6, ease: "power3.out" }) });
    gsap.from(".stack span", { autoAlpha: 0, scale: .8, stagger: .04, duration: .4, ease: "back.out(2)",
      scrollTrigger: { trigger: ".stack", start: "top 92%", once: true } });
    gsap.from(".final .headline", { y: 40, autoAlpha: 0, duration: 1, ease: "power3.out",
      scrollTrigger: { trigger: ".final", start: "top 70%", once: true } });

    return () => { gsap.set(paths, { attr: { d: (i, t) => t.dataset.quoted } }); };
  });

  window.addEventListener("load", () => ScrollTrigger.refresh());
})();
