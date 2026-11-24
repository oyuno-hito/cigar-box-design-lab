"use strict";

const KIND_LABEL = { song: "曲", mood: "ムード" };
const $ = (sel) => document.querySelector(sel);

let themes = [];
let theme = null; // 選択中のテーマ（常に 1 つ。初期値は先頭）
let index = 0; // 拡大表示中の画像（theme.images の添字）
let pushed = false; // 拡大表示を開くときに履歴を積んだか

const imageUrl = (t, image, thumb) => `artifacts/${t.id}/${image.id}${thumb ? ".thumb" : ""}.webp`;

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
  $("#viewer-img").src = imageUrl(theme, image, false);
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
  if (e.target === e.currentTarget) closeViewer();
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
