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
let boxDefaults = {}; // DEFAULT_BOX と colorOr は boxview.js

function boxSpec(t, image) {
  const m = { ...DEFAULT_BOX, ...boxDefaults, ...(t.box || {}), ...(image.box || {}) };
  return {
    sideColorLR: colorOr(m.sideColorLR, DEFAULT_BOX.sideColorLR),
    sideColorTB: colorOr(m.sideColorTB, DEFAULT_BOX.sideColorTB),
    frame: m.frame !== false,
    frameColor: colorOr(m.frameColor, DEFAULT_BOX.frameColor),
  };
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
    viewer.focus(); // 既定では先頭のボタン（一箱）にフォーカスが当たり、選択中でなくても枠が出る
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
/* ファイルを保存する。スマホ（タッチ端末）では共有メニューを開く。
   iOS の「ダウンロード」は「ファイル」アプリにしか保存できないが、共有メニューなら「画像を保存」で写真に追加できる。
   共有メニューが使えない・失敗したときは、ダウンロードに切り替える（シミュレータの saveFile と同じ方式） */
const isTouch = () => window.matchMedia("(pointer: coarse)").matches;
async function saveFile(blob, filename) {
  if (isTouch() && navigator.canShare && navigator.share) {
    const file = new File([blob], filename, { type: blob.type });
    if (navigator.canShare({ files: [file] })) {
      try {
        await navigator.share({ files: [file] });
        return;
      } catch (e) {
        if (e && e.name === "AbortError") return; // 共有メニューを閉じただけ
        // ボタンを押した直後と見なされなくなった場合などは、ダウンロードに切り替える
      }
    }
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
}
/* 表示中の画像（WebP）を、canvas に描いて PNG で保存する。同じオリジンの画像なので canvas が汚れない */
async function savePng() {
  const btn = $("#viewer-save");
  const image = theme.images[index];
  btn.disabled = true;
  try {
    const img = new Image();
    img.src = imageUrl(theme, image, false);
    await img.decode();
    const canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    canvas.getContext("2d").drawImage(img, 0, 0);
    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("PNG にできませんでした"))), "image/png");
    });
    // ファイル名は「題名-テーマ名」。ファイル名に使えない文字は除く
    const safe = (s) => String(s || "").replace(/[\\/:*?"<>|\u0000-\u001f]/g, "").trim();
    const filename = `${safe(theme.title) || theme.id}-${safe(image.title) || image.id}.png`;
    await saveFile(blob, filename);
  } catch (e) {
    alert("保存できませんでした。");
  } finally {
    btn.disabled = false;
  }
}

$("#viewer-save").addEventListener("click", savePng);
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
