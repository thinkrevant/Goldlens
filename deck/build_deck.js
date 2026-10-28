// GoldLens pitch deck: 7 slides built from the project's own data (site.json) and real product screenshots.
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const RDS = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");

const site = JSON.parse(fs.readFileSync(path.join(__dirname, "site.json"), "utf8"));
const OUT = path.join(__dirname, "GoldLens-Pitch.pptx");

const THEME = {
  name: "GoldLens",
  headFontFace: "Arial",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "0B0F17", lt1: "E9EBF0", dk2: "151C29", lt2: "8A93A6",
    accent1: "E0B04A", accent2: "5B8DEF", accent3: "F07A8C", accent4: "3CC9A7",
    accent5: "26C281", accent6: "F0566A", hlink: "F6D98B", folHlink: "B8862B",
  },
};
const HEX = { bg: "0B0F17", panel: "151C29", border: "222B3A", text: "E9EBF0", muted: "8A93A6", gold: "E0B04A",
  blue: "5B8DEF", rose: "F07A8C", teal: "3CC9A7", green: "26C281", red: "F0566A" };
const SYM = ["GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"];
const SYM_HEX = [HEX.gold, HEX.blue, HEX.rose, HEX.teal];

async function icon(Comp, color, size = 256) {
  const svg = RDS.renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
  pres.title = "GoldLens: Honest intelligence for MCX gold futures";
  pres.author = "Team TechFast";
  pres.subject = "Hack in Hills '26 · PS 03 Commodity Derivatives Intelligence";
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;

  // ---------------------------------------------------------------- layouts
  pres.defineSlideMaster({
    title: "GL_TITLE",
    background: { color: C.text1 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.7, y: 2.45, w: 6.4, h: 1.25, fontSize: 72, bold: true,
        color: C.accent1, valign: "middle", align: "left", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "subtitle", type: "body", x: 0.7, y: 3.7, w: 6.4, h: 0.6, fontSize: 26,
        color: C.background1, valign: "top", align: "left", margin: 0 }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "GL_CONTENT",
    background: { color: C.text1 },
    margin: [0.5, 0.6, 0.6, 0.6],
    objects: [
      { placeholder: { options: { name: "eyebrow", type: "body", x: 0.6, y: 0.4, w: 9, h: 0.35, fontSize: 13, bold: true,
        color: C.accent1, charSpacing: 3, valign: "middle", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.78, w: 12.13, h: 0.8, fontSize: 32, bold: true,
        color: C.background1, valign: "top", align: "left", margin: 0 }, text: "" } },
      { text: { text: "GoldLens  ·  Hack in Hills '26, powered by TinyFish  ·  PS 03",
        options: { x: 0.6, y: 7.0, w: 8, h: 0.3, fontSize: 10, color: C.background2, margin: 0 } } },
    ],
    slideNumber: { x: 12.23, y: 7.0, w: 0.5, h: 0.3, fontSize: 10, color: C.background2, align: "right" },
  });

  // ---------------------------------------------------------------- shared assets
  const logo = "image/png;base64," + (await sharp(fs.readFileSync(path.join(__dirname, "logo.svg"))).resize(512, 512).png().toBuffer()).toString("base64");
  const ic = {
    scale: await icon(fa.FaBalanceScale, HEX.bg), chart: await icon(fa.FaChartLine, HEX.bg), horn: await icon(fa.FaBullhorn, HEX.bg),
    db: await icon(fa.FaDatabase, HEX.bg), model: await icon(fa.FaProjectDiagram, HEX.bg), filter: await icon(fa.FaFilter, HEX.bg),
    send: await icon(fa.FaPaperPlane, HEX.bg), chev: await icon(fa.FaChevronRight, HEX.gold), down: await icon(fa.FaArrowDown, HEX.muted),
    check: await icon(fa.FaCheck, HEX.bg), search: await icon(fa.FaSearchDollar, HEX.bg), tg: await icon(fa.FaTelegramPlane, HEX.bg),
    robot: await icon(fa.FaRobot, HEX.bg), coins: await icon(fa.FaCoins, HEX.gold),
    cross: await icon(fa.FaTimes, HEX.bg), clock: await icon(fa.FaClock, HEX.bg), trophy: await icon(fa.FaTrophy, HEX.gold),
  };

  const card = (s, x, y, w, h, name, fill = C.text2) =>
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { color: HEX.border, width: 1 }, objectName: name });
  const circleIcon = (s, data, x, y, d, color, name) => {
    s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color }, line: { type: "none" }, objectName: name + " circle" });
    const pad = d * 0.24;
    s.addImage({ data, x: x + pad, y: y + pad, w: d - 2 * pad, h: d - 2 * pad, objectName: name + " icon" });
  };
  const text = (s, t, o) => s.addText(t, { isTextBox: true, margin: 0, valign: "top", ...o });

  // real series: front-contract px10, carried forward over any gaps
  const S = site.series;
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const labels = S.dates.map((d) => { const [y, m] = d.split("-"); return `${MONTHS[+m - 1]} ${y.slice(2)}`; });
  const fill = (arr) => { let last = arr.find((v) => v != null); return arr.map((v) => (v == null ? last : (last = v))); };
  const px10Data = SYM.map((s) => ({ name: s, labels, values: fill(S[s].px10) }));
  const axis = { catAxisLabelColor: HEX.muted, valAxisLabelColor: HEX.muted, catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
    catAxisLabelFontSize: 11, valAxisLabelFontSize: 11, catAxisLineShow: false, valAxisLineShow: false, catGridLine: { style: "none" } };

  const fmtLakh = (v) => `₹${(v / 1e5).toFixed(2)} lakh`;
  const lad = site.ladder;
  const ladNet = (needle) => lad.find((r) => r.name === needle || r.label === needle);

  // ================================================================ 1. Title
  pres.addSection({ title: "Opening" });
  let s = pres.addSlide({ masterName: "GL_TITLE", sectionTitle: "Opening" });
  s.addImage({ data: logo, x: 0.7, y: 0.85, w: 0.95, h: 0.95, objectName: "GoldLens logo" });
  text(s, "HACK IN HILLS, POWERED BY TINYFISH  ·  PS 03", { x: 0.7, y: 2.05, w: 6.4, h: 0.4, fontSize: 14, bold: true, color: C.accent1, charSpacing: 2 });
  s.addText("GoldLens", { placeholder: "title" });
  s.addText("Honest intelligence for MCX gold futures", { placeholder: "subtitle" });
  text(s, "Four gold contracts on one scale, alerts only when a trade pays after real costs, and a lie detector for trading tips.",
    { x: 0.7, y: 4.4, w: 6.2, h: 0.9, fontSize: 16, color: C.background2 });
  [[String(site.meta.trading_days), "trading days of real MCX data"], [String(site.meta.contracts), "contracts tracked and rolled"], ["61", "automated tests passing"]]
    .forEach(([n, l], i) => {
      const x = 0.7 + i * 2.2;
      card(s, x, 5.45, 1.95, 0.95, `Stat ${i + 1}`);
      text(s, n, { x: x + 0.18, y: 5.52, w: 1.6, h: 0.45, fontSize: 24, bold: true, color: C.accent1, fontFace: "Arial" });
      text(s, l, { x: x + 0.18, y: 5.95, w: 1.65, h: 0.4, fontSize: 11, color: C.background2 });
    });
  text(s, "Team TechFast  ·  Revant Raj", { x: 0.7, y: 6.75, w: 6.4, h: 0.35, fontSize: 14, color: C.background1 });
  card(s, 7.45, 0.85, 5.3, 5.85, "Chart panel");
  text(s, "Four contracts, one honest line", { x: 7.7, y: 1.05, w: 4.8, h: 0.35, fontSize: 14, bold: true, color: C.background1 });
  s.addChart(pres.charts.LINE, px10Data, { x: 7.6, y: 1.45, w: 5.0, h: 4.6, chartColors: SYM_HEX, lineSize: 2, lineDataSymbol: "none",
    ...axis, valAxisHidden: true, catAxisHidden: true, valGridLine: { style: "none" }, showLegend: true, legendPos: "b",
    legendColor: HEX.text, legendFontFace: "+mn-lt", legendFontSize: 11, valAxisMinVal: 110000, objectName: "Normalised price lines" });
  text(s, "₹ per 10 g of 999 gold  ·  Oct 2025 to Oct 2026", { x: 7.7, y: 6.15, w: 4.8, h: 0.35, fontSize: 12, color: C.background2 });
  s.addNotes(`Hack in Hills, powered by TinyFish. We're Team TechFast, and this is GoldLens: honest intelligence for MCX gold futures.
In one line: we put all four MCX gold contracts on one scale, we only raise an alert when a trade would still pay after real Indian trading costs, and we built a lie detector for trading tips.
Everything you'll see runs on ${site.meta.trading_days} trading days of real MCX settlement data, ${site.meta.contracts} contracts, with 61 automated tests.`);

  const arrow = (s, x1, y1, x2, y2, name) =>
    s.addShape(pres.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1) || 0.001, h: Math.abs(y2 - y1) || 0.001,
      flipV: y2 < y1, line: { color: HEX.gold, width: 1.75, endArrowType: "triangle" }, objectName: name });
  const label = (s, t, x, y, w, color = C.accent1) => text(s, t, { x, y, w, h: 0.3, fontSize: 12, bold: true, color, charSpacing: 2 });

  // ================================================================ 2. Problem
  pres.addSection({ title: "Problem and solution" });
  s = pres.addSlide({ masterName: "GL_CONTENT", sectionTitle: "Problem and solution" });
  s.addText("THE PROBLEM", { placeholder: "eyebrow" });
  s.addText("Same gold, four prices, and false confidence", { placeholder: "title" });
  const specs = { GOLDM: "100 g lot · per 10 g · 995", GOLDTEN: "10 g lot · per 10 g · 999", GOLDGUINEA: "8 g lot · per 8 g · 916", GOLDPETAL: "1 g lot · per 1 g · 999" };
  const q = { GOLDM: ["146,425", "05 NOV 26"], GOLDTEN: ["146,819", "30 OCT 26"], GOLDGUINEA: ["118,009", "30 OCT 26"], GOLDPETAL: ["14,755", "30 OCT 26"] };
  SYM.forEach((sym, i) => {
    const x = 0.6 + (i % 2) * 3.2, y = 1.85 + Math.floor(i / 2) * 1.8;
    card(s, x, y, 2.95, 1.55, `${sym} card`);
    s.addShape(pres.shapes.OVAL, { x: x + 0.22, y: y + 0.27, w: 0.16, h: 0.16, fill: { color: SYM_HEX[i] }, line: { type: "none" }, objectName: `${sym} colour` });
    text(s, sym, { x: x + 0.48, y: y + 0.17, w: 2.3, h: 0.35, fontSize: 17, bold: true, color: C.background1 });
    text(s, specs[sym], { x: x + 0.22, y: y + 0.55, w: 2.6, h: 0.3, fontSize: 12, color: C.background2 });
    text(s, [{ text: `₹${q[sym][0]}`, options: { fontSize: 24, bold: true, color: C.background1, fontFace: "Arial" } },
      { text: `  ${q[sym][1]}`, options: { fontSize: 10, color: C.background2 } }], { x: x + 0.22, y: y + 0.92, w: 2.65, h: 0.5 });
  });
  text(s, [{ text: "Same metal, prices 10× apart. ", options: { color: C.background1 } },
    { text: "Which one is actually cheap?", options: { color: C.accent1, bold: true } }], { x: 0.6, y: 5.6, w: 6.15, h: 0.5, fontSize: 18 });
  [[ic.scale, HEX.gold, "Prices can't be compared", "Different lots, quote units, purity and expiry"],
    [ic.chart, HEX.blue, "Backtests overstate profit", "Look-ahead and missing costs fake an edge"],
    [ic.horn, HEX.red, "Tips promise the impossible", "\"40% a year, guaranteed\" floods Telegram"]]
    .forEach(([img, col, h, d], i) => {
      const y = 1.9 + i * 1.18;
      circleIcon(s, img, 7.2, y, 0.66, col, h);
      text(s, h, { x: 8.1, y: y - 0.02, w: 4.6, h: 0.4, fontSize: 18, bold: true, color: C.background1 });
      text(s, d, { x: 8.1, y: y + 0.38, w: 4.6, h: 0.4, fontSize: 14, color: C.background2 });
    });
  card(s, 7.2, 5.5, 5.53, 1.25, "Why it matters");
  text(s, "93%", { x: 7.42, y: 5.62, w: 1.6, h: 0.75, fontSize: 40, bold: true, color: C.accent6, fontFace: "Arial", valign: "middle" });
  text(s, [{ text: "WHY IT MATTERS", options: { bold: true, color: C.accent1, fontSize: 11, charSpacing: 2, breakLine: true } },
    { text: "of individual F&O traders lost money, FY22–FY24 (SEBI study, 2024)", options: { color: C.background1, fontSize: 14 } }],
    { x: 9.05, y: 5.65, w: 3.55, h: 1.0 });
  s.addNotes(`MCX sells the same gold four ways. GOLDM, GOLDTEN, GOLDGUINEA and GOLDPETAL have different lot sizes, quote units, purity and expiry dates. GOLDPETAL quotes about fourteen thousand rupees and GOLDM about one lakh forty-six thousand, for the same metal. Nobody can tell at a glance which one is cheap.
Two things make it worse. Most backtests quietly cheat with look-ahead and no costs, and Telegram is full of tips promising forty percent a year, guaranteed.
Why it matters: SEBI's 2024 study found 93 percent of individual F&O traders lost money over three years. Retail traders need honest tools, not more hype.`);

  // ================================================================ 3. Solution
  s = pres.addSlide({ masterName: "GL_CONTENT", sectionTitle: "Problem and solution" });
  s.addText("OUR SOLUTION", { placeholder: "eyebrow" });
  s.addText("GoldLens puts every contract on one honest scale", { placeholder: "title" });
  card(s, 0.6, 1.8, 7.4, 4.95, "Chart panel");
  s.addChart(pres.charts.LINE, px10Data, { x: 0.75, y: 1.95, w: 7.1, h: 4.65, chartColors: SYM_HEX, lineSize: 1.75, lineDataSymbol: "none",
    ...axis, valGridLine: { color: HEX.border, size: 0.75 }, valAxisLabelFormatCode: "₹#,##0", valAxisMinVal: 110000,
    catAxisLabelFrequency: 21, showLegend: true, legendPos: "b", legendColor: HEX.text, legendFontFace: "+mn-lt", legendFontSize: 11,
    showTitle: true, title: "₹ per 10 g of 999 gold: four contracts, one line", titleColor: HEX.text, titleFontFace: "+mn-lt", titleFontSize: 14,
    objectName: "Normalised prices chart" });
  label(s, "WHAT MAKES IT DIFFERENT", 8.35, 1.85, 4.3);
  [[ic.scale, HEX.gold, "One scale", "All four contracts in ₹ / 10 g of 999"],
    [ic.filter, HEX.teal, "Cost-aware alerts", "Fires only if it pays after real costs"],
    [ic.check, HEX.blue, "Honest by design", "Every backtest flaw removed, step by step"],
    [ic.search, HEX.red, "Tip lie detector", "Busts \"guaranteed\" tips in seconds"]]
    .forEach(([img, col, h, d], i) => {
      const y = 2.3 + i * 0.92;
      circleIcon(s, img, 8.35, y, 0.56, col, h);
      text(s, h, { x: 9.12, y: y - 0.03, w: 3.6, h: 0.35, fontSize: 17, bold: true, color: C.background1 });
      text(s, d, { x: 9.12, y: y + 0.3, w: 3.6, h: 0.32, fontSize: 13, color: C.background2 });
    });
  card(s, 8.35, 6.05, 4.38, 0.7, "Formula strip");
  text(s, "px10 = price · 10/g · 999/purity", { x: 8.55, y: 6.05, w: 4.1, h: 0.7, fontSize: 14, color: C.accent1, fontFace: "Courier New", valign: "middle" });
  s.addNotes(`GoldLens converts every contract to rupees per ten grams of 999 gold: price times ten over its quote grams, times 999 over its purity. On this chart the four lines that looked unrelated collapse onto one.
What makes it different: one scale for all four contracts; alerts that fire only when a trade would pay after real Indian costs; a backtest that's honest by design; and a lie detector for trading tips.`);

  // ================================================================ 4. Workflow
  pres.addSection({ title: "Prototype" });
  s = pres.addSlide({ masterName: "GL_CONTENT", sectionTitle: "Prototype" });
  s.addText("HOW THE PROTOTYPE WORKS", { placeholder: "eyebrow" });
  s.addText("From raw MCX files to one honest decision", { placeholder: "title" });
  const steps = [[ic.db, HEX.gold, "Ingest", "Daily MCX files, validated"],
    [ic.scale, HEX.blue, "Normalise", "₹ per 10 g of 999 gold"],
    [ic.model, HEX.rose, "Model", "Carry curve + past-only z-scores"],
    [ic.filter, HEX.teal, "Gate", "Unusual, liquid, pays after costs"],
    [ic.send, HEX.green, "Deliver", "Web, AI analyst, Telegram"]];
  steps.forEach(([img, col, h, d], i) => {
    const x = 0.6 + i * 2.5;
    card(s, x, 1.85, 2.13, 2.35, `Step ${i + 1}`);
    circleIcon(s, img, x + 0.22, 2.05, 0.7, col, h);
    text(s, `${i + 1}  ${h}`, { x: x + 0.22, y: 2.92, w: 1.8, h: 0.4, fontSize: 17, bold: true, color: C.background1 });
    text(s, d, { x: x + 0.22, y: 3.35, w: 1.8, h: 0.7, fontSize: 14, color: C.background2 });
    if (i < steps.length - 1) s.addImage({ data: ic.chev, x: x + 2.19, y: 2.88, w: 0.25, h: 0.25, objectName: `Arrow ${i + 1}` });
  });
  label(s, "LIVE EXAMPLE  ·  TODAY'S BEST CANDIDATE, GOLDM / GOLDPETAL (16 OCT 2026)", 0.6, 4.55, 10);
  const gates = [["Unusual gap?", "z = −1.88, needs ±2", false], ["Liquid legs?", "37k and 162k lots traded", true], ["Pays after costs?", "Edge ₹9,885 vs cost ₹1,985", true]];
  gates.forEach(([qq, v, ok], i) => {
    const x = 0.6 + i * 3.0;
    card(s, x, 5.0, 2.7, 1.6, `Gate ${i + 1}`);
    circleIcon(s, ok ? ic.check : ic.cross, x + 2.1, 5.17, 0.42, ok ? HEX.green : HEX.red, `Gate ${i + 1} result`);
    text(s, qq, { x: x + 0.22, y: 5.2, w: 1.85, h: 0.4, fontSize: 17, bold: true, color: C.background1 });
    text(s, v, { x: x + 0.22, y: 5.72, w: 2.3, h: 0.75, fontSize: 14, color: C.background2 });
    s.addImage({ data: ic.chev, x: x + 2.73, y: 5.68, w: 0.24, h: 0.24, objectName: `Gate arrow ${i + 1}` });
  });
  card(s, 9.6, 5.0, 3.13, 1.6, "Gate outcome");
  text(s, [{ text: "No alert today", options: { bold: true, color: C.accent4, fontSize: 20, breakLine: true } },
    { text: "Quiet by design: one gate failed, so no trade.", options: { color: C.background1, fontSize: 14 } }],
    { x: 9.82, y: 5.2, w: 2.75, h: 1.3, paraSpaceAfter: 6 });
  s.addNotes(`Here's the prototype's workflow. We pull MCX's public Bhavcopy every day and validate it. We normalise every contract, fit the futures curve for carry and premium, and score each pair's gap with z-scores built only from past data.
The gate needs three yeses: an unusual gap, liquid legs, and an expected reversion worth at least one and a half times the round-trip cost. Today's best candidate, GOLDM against GOLDPETAL, is liquid and would pay, but at z minus 1.88 it isn't unusual enough. So GoldLens stays quiet. Most days the honest answer is "do nothing".`);

  // ================================================================ 5. Architecture
  s = pres.addSlide({ masterName: "GL_CONTENT", sectionTitle: "Prototype" });
  s.addText("ARCHITECTURE AND TECHNOLOGY", { placeholder: "eyebrow" });
  s.addText("One Python core powers web, AI and Telegram", { placeholder: "title" });
  label(s, "DATA", 0.6, 1.8, 2.3); label(s, "INGEST", 3.35, 1.8, 2.3); label(s, "ANALYTICS CORE", 6.1, 1.8, 3.1); label(s, "DELIVERY", 10.0, 1.8, 2.7);
  card(s, 0.6, 2.25, 2.3, 1.4, "MCX Bhavcopy");
  text(s, [{ text: "MCX Bhavcopy", options: { bold: true, color: C.background1, fontSize: 16, breakLine: true } },
    { text: "Public daily settlements since 2023", options: { color: C.background2, fontSize: 13 } }], { x: 0.8, y: 2.4, w: 1.95, h: 1.15 });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 4.0, w: 2.3, h: 1.4, rectRadius: 0.12, fill: { color: C.text1 }, line: { color: HEX.muted, width: 1, dashType: "dash" }, objectName: "Upstox box" });
  text(s, [{ text: "Upstox API", options: { bold: true, color: C.background1, fontSize: 16, breakLine: true } },
    { text: "Live quotes, ready for the finale", options: { color: C.background2, fontSize: 13 } }], { x: 0.8, y: 4.15, w: 1.95, h: 1.15 });
  card(s, 3.35, 2.25, 2.3, 3.15, "Ingest box");
  text(s, [{ text: "Fetch & validate", options: { bold: true, color: C.background1, fontSize: 16, breakLine: true } },
    { text: "Browser-grade fetch", options: { bullet: true, color: C.background2, fontSize: 13, breakLine: true } },
    { text: "Date & holiday checks", options: { bullet: true, color: C.background2, fontSize: 13, breakLine: true } },
    { text: "Parquet cache, resumable", options: { bullet: true, color: C.background2, fontSize: 13 } }],
    { x: 3.55, y: 2.4, w: 2.0, h: 2.9, paraSpaceAfter: 6 });
  card(s, 6.1, 2.25, 3.1, 3.15, "Core container");
  ["Normalise", "Curve & carry", "Signals + cost gate", "Walk-forward backtest", "Tip Checker"].forEach((m, i) => {
    const y = 2.42 + i * 0.58;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 6.28, y, w: 2.74, h: 0.46, rectRadius: 0.08, fill: { color: C.text1 }, line: { color: SYM_HEX[i % 4], width: 1 }, objectName: `Module ${m}` });
    text(s, m, { x: 6.45, y, w: 2.5, h: 0.46, fontSize: 14, color: C.background1, valign: "middle" });
  });
  card(s, 6.1, 5.75, 3.1, 0.95, "AI box");
  text(s, [{ text: "AI analyst", options: { bold: true, color: C.background1, fontSize: 15, breakLine: true } },
    { text: "Claude → Grok → OpenRouter", options: { color: C.background2, fontSize: 13 } }], { x: 6.3, y: 5.85, w: 2.8, h: 0.8 });
  [["Website", "FastAPI · htmx · Plotly"], ["Telegram bot", "Morning brief + alerts"], ["Landing page", "GSAP animations"]].forEach(([h, d], i) => {
    const y = 2.25 + i * 1.12;
    card(s, 10.0, y, 2.73, 0.95, `Delivery ${h}`);
    text(s, [{ text: h, options: { bold: true, color: C.background1, fontSize: 15, breakLine: true } }, { text: d, options: { color: C.background2, fontSize: 13 } }],
      { x: 10.2, y: y + 0.1, w: 2.45, h: 0.8 });
    arrow(s, 9.25, y + 0.47, 9.95, y + 0.47, `Core to ${h}`);
  });
  arrow(s, 2.95, 2.95, 3.3, 2.95, "Bhavcopy to ingest");
  arrow(s, 2.95, 4.7, 3.3, 4.7, "Upstox to ingest");
  arrow(s, 5.7, 3.82, 6.05, 3.82, "Ingest to core");
  arrow(s, 7.65, 5.72, 7.65, 5.45, "AI reads core facts");
  card(s, 10.0, 5.75, 2.73, 0.95, "Tests box");
  text(s, [{ text: "61 tests", options: { bold: true, color: C.accent1, fontSize: 15, breakLine: true } }, { text: "incl. no-look-ahead proof", options: { color: C.background2, fontSize: 13 } }],
    { x: 10.2, y: 5.85, w: 2.45, h: 0.8 });
  s.addNotes(`The architecture is one Python core. Data comes from MCX's public Bhavcopy, with the Upstox live feed already coded for the finale. The ingest layer fetches each day, checks dates and holidays and caches everything as parquet, so the app runs offline.
The analytics core has five modules: normalisation, the carry curve, signals with the cost gate, the walk-forward backtester and the Tip Checker. The AI analyst reads only the core's fact sheet and falls back from Claude to Grok to free OpenRouter models.
The same core feeds the FastAPI website, the Telegram bot and the landing page. 61 automated tests run against it, including one that proves there's no look-ahead.`);

  // ================================================================ 6. Honesty ladder (results)
  pres.addSection({ title: "Results and progress" });
  s = pres.addSlide({ masterName: "GL_CONTENT", sectionTitle: "Results and progress" });
  s.addText("PROOF ON REAL DATA", { placeholder: "eyebrow" });
  s.addText("Most backtests lie. Ours removes each lie", { placeholder: "title" });
  const ladderRows = [["Naive", 121168], ["Gram-matched", 2095080], ["Next-day fill", 885945], ["Past-only z", 2574955],
    ["Real contracts", 253600], ["+ Costs", -3493.16], ["+ Liquidity", -3493.16]];
  label(s, "PAPER PROFIT", 0.6, 1.95, 4, C.background2);
  text(s, "₹25.75 lakh", { x: 0.6, y: 2.25, w: 4.1, h: 0.75, fontSize: 40, bold: true, color: C.accent1, fontFace: "Arial" });
  text(s, "Stitched prices, look-ahead, no costs", { x: 0.6, y: 3.0, w: 4.0, h: 0.35, fontSize: 14, color: C.background2 });
  s.addImage({ data: ic.down, x: 0.62, y: 3.6, w: 0.4, h: 0.4, objectName: "Down arrow" });
  label(s, "HONEST RESULT", 0.6, 4.25, 4, C.background2);
  text(s, "−₹3,493", { x: 0.6, y: 4.55, w: 4.1, h: 0.95, fontSize: 54, bold: true, color: C.accent6, fontFace: "Arial" });
  text(s, "181 trades · ₹2.57 lakh in real costs", { x: 0.6, y: 5.55, w: 4.0, h: 0.35, fontSize: 14, color: C.background2 });
  card(s, 5.0, 1.8, 7.73, 4.1, "Ladder panel");
  s.addChart(pres.charts.BAR, [{ name: "Net profit (₹ lakh)", labels: ladderRows.map((r) => r[0]), values: ladderRows.map((r) => +(r[1] / 1e5).toFixed(2)) }],
    { x: 5.15, y: 1.9, w: 7.45, h: 3.9, barDir: "col", barGapWidthPct: 45,
      chartColors: [HEX.muted, HEX.muted, HEX.muted, HEX.gold, HEX.blue, HEX.red, HEX.red],
      showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.00", dataLabelColor: HEX.text, dataLabelFontSize: 11, dataLabelFontFace: "+mn-lt",
      ...axis, valAxisHidden: true, valGridLine: { style: "none" }, showLegend: false,
      showTitle: true, title: "Net profit after each fix, ₹ lakh (6 pairs, 973 days)", titleColor: HEX.text, titleFontFace: "+mn-lt", titleFontSize: 14,
      objectName: "Honesty ladder chart" });
  card(s, 0.6, 6.05, 5.95, 0.72, "Attribution strip");
  s.addImage({ data: ic.coins, x: 0.8, y: 6.24, w: 0.34, h: 0.34, objectName: "Gold exposure icon" });
  text(s, [{ text: "Hidden gold bet: ", options: { bold: true, color: C.background1 } },
    { text: `${site.attribution.naive_g} g → ${site.attribution.honest_g} g of gold exposure`, options: { color: C.background2 } }],
    { x: 1.3, y: 6.05, w: 5.15, h: 0.72, fontSize: 14, valign: "middle" });
  card(s, 6.78, 6.05, 5.95, 0.72, "Best pair strip");
  s.addImage({ data: ic.trophy, x: 6.98, y: 6.24, w: 0.34, h: 0.34, objectName: "Best pair icon" });
  text(s, [{ text: "Real edge found: ", options: { bold: true, color: C.background1 } },
    { text: `GOLDTEN/GUINEA +₹1.39 lakh, ${site.best_pair.win_rate}% wins`, options: { color: C.background2 } }],
    { x: 7.48, y: 6.05, w: 5.15, h: 0.72, fontSize: 14, valign: "middle" });
  s.addNotes(`This is our proof, on real data. Most backtests lie, so ours removes each lie one step at a time, on the same six pairs and ${site.meta.trading_days} days.
The typical backtest shows twenty-five point seven five lakh rupees of profit. Mark P&L on the real contracts with rolls and carry and it falls to two and a half lakh. Add brokerage, exchange fees, CTT, stamp duty, GST and slippage, and it becomes a loss of three thousand four hundred rupees over 181 trades.
The naive version was also secretly a 186-gram bet on gold; the honest version carries 13 grams. And the honest test still finds where a real edge exists: GOLDTEN against GOLDGUINEA made 1.39 lakh with a 74 percent win rate.`);

  // ================================================================ 7. Features + progress
  s = pres.addSlide({ masterName: "GL_CONTENT", sectionTitle: "Results and progress" });
  s.addText("FEATURES AND PROGRESS", { placeholder: "eyebrow" });
  s.addText("Working today, end to end, on real MCX data", { placeholder: "title" });
  s.addImage({ path: path.join(__dirname, "tipcheck.png"), x: 0.6, y: 1.85, w: 4.75, h: 3.54, objectName: "Tip Checker screenshot",
    altText: "Tip Checker result: a 40% guaranteed tip tested honestly returns -1.7% a year and is marked busted" });
  s.addImage({ path: path.join(__dirname, "phone.png"), x: 5.55, y: 1.85, w: 2.1, h: 3.54, objectName: "Telegram morning brief screenshot",
    altText: "GoldLens Telegram morning brief on a phone" });
  text(s, [{ text: "Tip Checker  ", options: { bold: true, color: C.background1 } }, { text: "\"40% guaranteed\" → honest −1.7%", options: { color: C.background2 } }],
    { x: 0.6, y: 5.5, w: 4.75, h: 0.35, fontSize: 14 });
  text(s, [{ text: "Morning brief  ", options: { bold: true, color: C.background1 } }, { text: "English · हिंदी", options: { color: C.background2 } }],
    { x: 5.55, y: 5.5, w: 2.4, h: 0.35, fontSize: 14 });
  text(s, "GoldLens. Honest intelligence for gold traders.", { x: 0.6, y: 6.25, w: 7.1, h: 0.45, fontSize: 20, bold: true, color: C.accent1 });
  card(s, 8.0, 1.85, 4.73, 4.9, "Progress panel");
  label(s, "PROGRESS", 8.22, 2.0, 2);
  text(s, "8 / 9 shipped", { x: 10.4, y: 2.0, w: 2.15, h: 0.3, fontSize: 12, bold: true, color: C.accent4, align: "right" });
  s.addShape(pres.shapes.RECTANGLE, { x: 8.22, y: 2.42, w: 4.33, h: 0.08, fill: { color: HEX.border }, line: { type: "none" }, objectName: "Progress track" });
  s.addShape(pres.shapes.RECTANGLE, { x: 8.22, y: 2.42, w: 4.33 * 8 / 9, h: 0.08, fill: { color: HEX.teal }, line: { type: "none" }, objectName: "Progress fill" });
  [["Data pipeline", "973 days", true], ["One-scale normalisation", "4 contracts", true], ["Scanner + cost gate", "6 pairs", true],
    ["Honest backtest", "7-step ladder", true], ["Tip Checker", "incl. Hinglish", true], ["AI analyst", "3 providers", true],
    ["Telegram brief", "daily", true], ["Website", "10 pages", true], ["Upstox live quotes", "coded, for finale", false]]
    .forEach(([h, d, done], i) => {
      const y = 2.68 + i * 0.44;
      circleIcon(s, done ? ic.check : ic.clock, 8.22, y + 0.04, 0.3, done ? HEX.teal : HEX.gold, `Progress ${i + 1}`);
      text(s, h, { x: 8.65, y, w: 2.5, h: 0.38, fontSize: 14, bold: true, color: C.background1, valign: "middle" });
      text(s, d, { x: 11.05, y, w: 1.5, h: 0.38, fontSize: 12, color: C.background2, valign: "middle", align: "right" });
    });
  s.addNotes(`Everything here is working today, end to end, on real MCX data.
The Tip Checker turns any tip, even in Hinglish, into a precise rule and replays it through the same honest test. This real tip promised forty percent a year, guaranteed; tested honestly it lost 1.7 percent a year, and GoldLens flags the guaranteed-returns and paid-group patterns SEBI warns about.
Every morning, one Telegram message brings the gold price, carry, signals, premiums and expiries, in English or Hindi.
Eight of nine pieces are shipped: the data pipeline, normalisation, scanner, honest backtest, Tip Checker, AI analyst, Telegram brief and the website. Live Upstox quotes are coded and ready for the grand finale.
GoldLens: honest intelligence for gold traders. Thank you.`);

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})().catch((e) => { console.error(e); process.exit(1); });
