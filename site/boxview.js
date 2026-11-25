"use strict";

/* 箱に貼ったイメージの描画（サイトの拡大表示と、tools/serve_session.py の仕上がりチェックで共有する）。
   DEFAULT_BOX: 箱の既定の色。colorOr: 色として使えるか確かめる。
   drawBox / rotationSvg / rowSvg / stackSvg: 箱の SVG を作る */
const DEFAULT_BOX = { sideColorLR: "#000000", sideColorTB: "#ffffff", frame: true, frameColor: "#ffffff" };
const colorOr = (v, fallback) => (typeof v === "string" && CSS.supports("color", v) ? v : fallback);

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
