"use strict";

const KIND_LABEL = { song: "曲", mood: "ムード" };
const $ = (sel) => document.querySelector(sel);

let themes = [];
let theme = null; // 選択中のテーマ（常に 1 つ。初期値は先頭）
let index = 0; // 拡大表示中の画像（theme.images の添字）
let pushed = false; // 拡大表示を開くときに履歴を積んだか

const imageUrl = (t, image, thumb) => `artifacts/${t.id}/${image.id}${thumb ? ".thumb" : ""}.webp`;

/* 箱に貼ったイメージ。色などは manifest.json の box（全体）→ テーマの box → 画像の box の順に上書きする。
   sideColorLR: 左右の側面の色 / sideColorTB: 上下の側面の色 / frame: 枠線の有無 / frameColor: 枠線の色。
   左右・上下は、箱を横長（180×120mm）に置いたときの向き。箱を回すと、見える側面の色も入れ替わる */
const DEFAULT_BOX = { sideColorLR: "#000000", sideColorTB: "#ffffff", frame: true, frameColor: "#ffffff" };
let boxDefaults = {};
const colorOr = (v, fallback) => (typeof v === "string" && CSS.supports("color", v) ? v : fallback);

function boxSpec(t, image) {
  const m = { ...DEFAULT_BOX, ...boxDefaults, ...(t.box || {}), ...(image.box || {}) };
  return {
    sideColorLR: colorOr(m.sideColorLR, DEFAULT_BOX.sideColorLR),
    sideColorTB: colorOr(m.sideColorTB, DEFAULT_BOX.sideColorTB),
    frame: m.frame !== false,
    frameColor: colorOr(m.frameColor, DEFAULT_BOX.frameColor),
  };
}

/* きぞはこ（180×120×60mm）を、右の側面と上面が見える角度で描く（cigar-box-design-simulator の立体と同じ向き）。
   どんな向きでも、カメラから見える側面は右と上。箱を回すと、そこに見える面（左右 / 上下）が入れ替わる。
   面の比率は 3:2 なので、画像は切らずに貼れる。枠線ありのときは、画像を内側に縮めて余白を枠線にする */
const SVG_NS = "http://www.w3.org/2000/svg";
const BOX = { w: 180, h: 120, d: 60, frameX: 9, frameY: 6 };
const DX = BOX.d * 0.62 * Math.cos((40 * Math.PI) / 180);
const DY = BOX.d * 0.62 * Math.sin((40 * Math.PI) / 180);
const MARGIN = 4;
const n2 = (n) => Number(n.toFixed(2));

function svgEl(parent, name, attrs) {
  const el = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  parent.append(el);
  return el;
}

function newSvg(vw, vh) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${n2(vw)} ${n2(vh)}`);
  svg.setAttribute("aria-hidden", "true");
  return svg;
}

/* 箱 1 つ。(x, y) は正面の左上。turn は箱を面の中で時計回りに回した角度（0 / 90 / 180 / 270） */
function drawBox(parent, x, y, turn, url, spec) {
  const flat = turn % 180 === 0; // 横長のまま（0 / 180）か、縦長（90 / 270）か
  const w = flat ? BOX.w : BOX.h;
  const h = flat ? BOX.h : BOX.w;
  const right = flat ? spec.sideColorLR : spec.sideColorTB;
  const top = flat ? spec.sideColorTB : spec.sideColorLR;
  const g = svgEl(parent, "g", { transform: `translate(${n2(x)} ${n2(y)})` });
  const pts = (a) => a.map(([px, py]) => `${n2(px)},${n2(py)}`).join(" ");
  const edge = { stroke: "#8f8a80", "stroke-width": 0.6, "stroke-linejoin": "round" };
  svgEl(g, "polygon", { points: pts([[w, 0], [w + DX, -DY], [w + DX, h - DY], [w, h]]), fill: right, ...edge });
  svgEl(g, "polygon", { points: pts([[0, 0], [DX, -DY], [w + DX, -DY], [w, 0]]), fill: top, ...edge });
  svgEl(g, "rect", { x: 0, y: 0, width: w, height: h, fill: spec.frame ? spec.frameColor : "#ffffff" });
  // 画像は横長のまま、面の中心で回す（90 / 270 のときは縦長の面にちょうど収まる）
  const [dw, dh] = spec.frame ? [BOX.w - 2 * BOX.frameX, BOX.h - 2 * BOX.frameY] : [BOX.w, BOX.h];
  const cx = w / 2;
  const cy = h / 2;
  svgEl(g, "image", {
    href: url, x: n2(cx - dw / 2), y: n2(cy - dh / 2), width: dw, height: dh,
    preserveAspectRatio: "xMidYMid slice", transform: `rotate(${turn} ${n2(cx)} ${n2(cy)})`,
  });
  svgEl(g, "rect", { x: 0, y: 0, width: w, height: h, fill: "none", ...edge });
}

/* 1 つの箱を 90 度ずつ回した 4 枚（2×2）。角度の表記はしない */
function rotationSvg(url, spec) {
  const cell = 216; // 横長 208.5×143.9、縦長 148.5×203.9 の箱がどちらも収まる大きさ
  const svg = newSvg(cell * 2, cell * 2);
  [0, 90, 180, 270].forEach((turn, i) => {
    const flat = turn % 180 === 0;
    const w = (flat ? BOX.w : BOX.h) + DX;
    const h = (flat ? BOX.h : BOX.w) + DY;
    const ox = (i % 2) * cell;
    const oy = Math.floor(i / 2) * cell;
    drawBox(svg, ox + (cell - w) / 2, oy + (cell - h) / 2 + DY, turn, url, spec);
  });
  return svg;
}

/* 箱を隙間なく横に並べる。turns は箱ごとの回転。横長なら短辺どうし、縦長なら長辺どうしがくっつく */
function rowSvg(url, spec, turns) {
  const flat = turns[0] % 180 === 0;
  const w = flat ? BOX.w : BOX.h;
  const h = flat ? BOX.h : BOX.w;
  const svg = newSvg(w * turns.length + DX + 2 * MARGIN, h + DY + 2 * MARGIN);
  turns.forEach((turn, i) => drawBox(svg, MARGIN + i * w, MARGIN + DY, turn, url, spec));
  return svg;
}

/* 箱を隙間なく上に積む。turns は上から順の回転。長辺（180mm）どうしがくっつく。
   下の箱から先に描き、上の箱が下の箱の上面を隠す（積んだときと同じ） */
function stackSvg(url, spec, turns) {
  const svg = newSvg(BOX.w + DX + 2 * MARGIN, BOX.h * turns.length + DY + 2 * MARGIN);
  for (let i = turns.length - 1; i >= 0; i--) {
    drawBox(svg, MARGIN, MARGIN + DY + i * BOX.h, turns[i], url, spec);
  }
  return svg;
}

/* 拡大表示の見せ方: one = 一箱を 90 度ずつ回した 4 枚 / stack = 縦に並べる（上に積む）/ row = 横に並べる */
const MODES = ["one", "stack", "row"];
let viewMode = "one";
try {
  const saved = localStorage.getItem("viewMode");
  if (MODES.includes(saved)) viewMode = saved;
} catch { /* 保存できなくても動く */ }

function applyMode() {
  document.querySelectorAll(".viewer-modes button").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.mode === viewMode));
  });
}

function renderStage() {
  const image = theme.images[index];
  const url = imageUrl(theme, image, false);
  const spec = boxSpec(theme, image);
  const stage = $("#viewer-stage");
  stage.textContent = "";
  stage.setAttribute("aria-label", image.title || "");
  const add = (svg, caption) => {
    const fig = document.createElement("figure");
    fig.append(svg);
    if (caption) {
      const cap = document.createElement("figcaption");
      cap.textContent = caption;
      fig.append(cap);
    }
    stage.append(fig);
  };
  stage.classList.toggle("cols", viewMode === "stack"); // 積んだ箱は縦長なので、2 つを左右に並べる
  if (viewMode === "one") {
    add(rotationSvg(url, spec));
  } else if (viewMode === "stack") {
    add(stackSvg(url, spec, [0, 0, 0]), "全部同じ向き");
    add(stackSvg(url, spec, [0, 180, 0]), "真ん中の一つを 180 度逆に");
  } else {
    add(rowSvg(url, spec, [0, 0, 0]), "全部同じ向き");
    add(rowSvg(url, spec, [0, 180, 0]), "真ん中の一つを 180 度逆に");
  }
}

/* URL の形: #<テーマ> または #<テーマ>/<番号>（拡大中） */
function parseHash() {
  const [themeId, imageId] = decodeURIComponent(location.hash.slice(1)).split("/");
  return { themeId, imageId };
}

function renderTabs() {
  const tabs = $("#tabs");
  tabs.textContent = "";
  for (const t of themes) {
    const b = document.createElement("button");
    b.type = "button";
    b.role = "tab";
    b.textContent = t.title;
    b.setAttribute("aria-selected", String(t === theme));
    b.addEventListener("click", () => selectTheme(t, true));
    tabs.append(b);
  }
  const active = tabs.querySelector('[aria-selected="true"]');
  if (active) active.scrollIntoView({ inline: "center", block: "nearest" });
}

function renderTheme() {
  $("#theme-title").textContent = theme.title;
  $("#theme-kind").textContent = KIND_LABEL[theme.kind] || "";
  $("#theme-count").textContent = `${theme.images.length} 枚`;
  const grid = $("#grid");
  grid.textContent = "";
  theme.images.forEach((image, i) => {
    const fig = document.createElement("button");
    fig.type = "button";
    fig.className = "card";
    fig.setAttribute("aria-label", `${image.title || i + 1} を拡大`);
    const img = document.createElement("img");
    img.src = imageUrl(theme, image, true);
    img.loading = "lazy";
    img.decoding = "async";
    img.alt = "";
    fig.append(img);
    if (image.title) {
      const cap = document.createElement("span");
      cap.className = "cap";
      cap.textContent = image.title;
      fig.append(cap);
    }
    fig.addEventListener("click", () => openViewer(i, true));
    grid.append(fig);
  });
}

function selectTheme(t, scroll) {
  theme = t;
  renderTabs();
  renderTheme();
  history.replaceState(null, "", `#${t.id}`);
  if (scroll && $("#grid").getBoundingClientRect().top < 0) {
    $("#grid").scrollIntoView({ block: "start" });
  }
}

/* 拡大表示。履歴に積むので、スマホの戻る操作で閉じられる */
const viewer = $("#viewer");

function showViewer() {
  const image = theme.images[index];
  renderStage();
  applyMode();
  $("#viewer-title").textContent = image.title || "";
  $("#viewer-sub").textContent = theme.title;
  $("#viewer-count").textContent = `${index + 1} / ${theme.images.length}`;
  history.replaceState(null, "", `#${theme.id}/${image.id}`);
  // 隣の画像を先に読んでおく
  for (const d of [1, -1]) {
    new Image().src = imageUrl(theme, theme.images[(index + d + theme.images.length) % theme.images.length], false);
  }
}

function openViewer(i, push) {
  index = i;
  if (!viewer.open) {
    if (push) history.pushState(null, "", `#${theme.id}/${theme.images[i].id}`);
    pushed = push;
    viewer.showModal();
  }
  showViewer();
}

function step(d) {
  const n = theme.images.length;
  index = (index + d + n) % n;
  showViewer();
}

function closeViewer() {
  if (!viewer.open) return;
  viewer.close();
  // 開くときに積んだ履歴は戻す。URL を直接開いた場合は、画像の指定だけ消す（サイトの外へ戻らない）
  if (pushed) history.back();
  else history.replaceState(null, "", `#${theme.id}`);
  pushed = false;
}

/* 戻る・進む・URL の直接指定に追従する */
function syncFromHash() {
  const { themeId, imageId } = parseHash();
  const t = themes.find((x) => x.id === themeId) || theme || themes[0];
  if (t !== theme) {
    theme = t;
    renderTabs();
    renderTheme();
  }
  const i = imageId ? theme.images.findIndex((x) => x.id === imageId) : -1;
  if (i >= 0) {
    openViewer(i, false);
  } else if (viewer.open) {
    viewer.close();
    pushed = false;
  }
}

document.querySelectorAll(".viewer-modes button").forEach((b) => {
  b.addEventListener("click", () => {
    viewMode = b.dataset.mode;
    try { localStorage.setItem("viewMode", viewMode); } catch { /* 保存できなくても動く */ }
    applyMode();
    if (viewer.open) renderStage();
  });
});
$("#viewer-close").addEventListener("click", closeViewer);
$("#viewer-prev").addEventListener("click", () => step(-1));
$("#viewer-next").addEventListener("click", () => step(1));
viewer.addEventListener("cancel", (e) => { e.preventDefault(); closeViewer(); }); // Esc
viewer.addEventListener("keydown", (e) => {
  if (e.key === "ArrowLeft") step(-1);
  if (e.key === "ArrowRight") step(1);
});
// 画像以外（余白）をタップしたら閉じる
$(".viewer-body").addEventListener("click", (e) => {
  if (e.target === e.currentTarget || e.target.id === "viewer-stage") closeViewer();
});
// 左右スワイプ
let touch = null;
$(".viewer-body").addEventListener("touchstart", (e) => {
  touch = e.touches.length === 1 ? { x: e.touches[0].clientX, y: e.touches[0].clientY } : null;
}, { passive: true });
$(".viewer-body").addEventListener("touchend", (e) => {
  if (!touch) return;
  const dx = e.changedTouches[0].clientX - touch.x;
  const dy = e.changedTouches[0].clientY - touch.y;
  touch = null;
  if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy) * 1.5) step(dx < 0 ? 1 : -1);
}, { passive: true });
window.addEventListener("popstate", syncFromHash);

fetch("artifacts/manifest.json")
  .then((r) => r.json())
  .then((m) => {
    boxDefaults = m.box || {};
    themes = m.themes.filter((t) => t.images.length > 0);
    if (!themes.length) return;
    theme = themes.find((t) => t.id === parseHash().themeId) || themes[0];
    renderTabs();
    renderTheme();
    syncFromHash();
  })
  .catch(() => {
    $("#grid").textContent = "画像の一覧を読み込めませんでした。";
  });
