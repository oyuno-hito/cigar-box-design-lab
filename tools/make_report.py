#!/usr/bin/env python3
"""実験 run のレポート（静的 HTML 1 枚）を runs/<run-id>/report.html に作る。標準ライブラリのみ。

    python3 tools/make_report.py runs/<run-id>
    python3 tools/make_report.py runs/<run-id> --serve    # 作ってから、runs/ 一覧サーバー（serve_runs.py）で開く

入力: spec.json / scores.json / images/*.json / scorers/metrics.json
レポートの内容:
  - 条件ごとの比較表（機械の通過率、p の平均・中央値）
  - 条件ごとの画像グリッド（p の高い順。足切り線で通過 / 不通過を分ける）
  - 人間レビュー: 機械の判定に同意しない画像をクリックして印を付ける
    tools/serve_runs.py（--serve も同じ）で開くと、保存ボタンが report.html と同じディレクトリの review.json に書く。
    印はブラウザの localStorage にも残る。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

HTML = r"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  :root { color-scheme: dark; --pass:#3fb950; --rej:#f85149; --flag:#f0b72f; --bg:#0d1117; --panel:#161b22; --line:#30363d; --mute:#8b949e; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:#e6edf3; font:14px/1.6 -apple-system,BlinkMacSystemFont,"Hiragino Sans",sans-serif; }
  main { max-width:1280px; margin:0 auto; padding:24px 20px 80px; }
  h1 { font-size:20px; margin:0 0 4px; } h2 { font-size:16px; margin:32px 0 8px; } h3 { font-size:14px; margin:0 0 4px; }
  .mute { color:var(--mute); } .small { font-size:12px; }
  .panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:12px 16px; margin:12px 0; }
  table { border-collapse:collapse; width:100%; } th,td { text-align:left; padding:6px 10px; border-bottom:1px solid var(--line); } th { color:var(--mute); font-weight:500; }
  td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
  .warn { border-color:#6e5a1a; background:#241e0c; }
  .bar { position:sticky; top:0; z-index:5; background:rgba(13,17,23,.96); border-bottom:1px solid var(--line); padding:8px 20px; display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
  .tabs { display:flex; gap:4px; margin-top:16px; border-bottom:1px solid var(--line); overflow-x:auto; }
  .tab { background:transparent; color:var(--mute); border:1px solid transparent; border-bottom:none; border-radius:6px 6px 0 0; padding:6px 14px; cursor:pointer; white-space:nowrap; font:inherit; }
  .tab:hover { background:#21262d; }
  .tab.active { background:var(--bg); color:#e6edf3; border-color:var(--line); margin-bottom:-1px; border-bottom:1px solid var(--bg); }
  .tab .st { font-weight:700; margin-left:6px; } .tab .st.ok { color:var(--pass); } .tab .st.todo { color:var(--flag); }
  .tab .cnt { margin-left:6px; font-size:12px; color:var(--mute); }
  button, label.btn { background:#21262d; color:#e6edf3; border:1px solid var(--line); border-radius:6px; padding:4px 10px; cursor:pointer; font:inherit; }
  button:hover, label.btn:hover { background:#30363d; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); gap:10px; }
  .card { position:relative; background:var(--panel); border:3px solid var(--line); border-radius:8px; overflow:hidden; cursor:pointer; }
  .card.pass { border-color:var(--pass); } .card.rej { border-color:var(--rej); }
  .card img { display:block; width:100%; aspect-ratio:3/2; object-fit:cover; background:#000; }
  .card .meta { padding:6px 8px; font-size:12px; }
  .card .p { position:absolute; top:6px; left:6px; background:rgba(0,0,0,.75); border-radius:4px; padding:1px 6px; font-weight:600; font-variant-numeric:tabular-nums; }
  .card .flag { display:none; position:absolute; top:6px; right:6px; background:var(--flag); color:#000; border-radius:4px; padding:1px 6px; font-weight:700; font-size:12px; }
  .card.flagged { outline:4px solid var(--flag); outline-offset:-4px; } .card.flagged .flag { display:block; }
  .divider { grid-column:1/-1; border-top:2px dashed var(--mute); margin:6px 0; color:var(--mute); font-size:12px; padding-top:4px; }
  .legend span { display:inline-block; margin-right:14px; } .dot { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px; vertical-align:middle; }
  .lbl { color:#79c0ff; font-weight:600; }
  code { background:#21262d; padding:1px 5px; border-radius:4px; }
</style>
</head>
<body>
<div class="bar">
  <a id="backlink" href="/" hidden>← runs 一覧</a>
  <strong>人間レビュー</strong>
  <span id="flagcount" class="mute"></span>
  <span id="unreviewed" style="color:var(--flag)"></span>
  <button id="download">review.json に保存</button>
  <span id="savestatus" class="mute"></span>
  <label class="btn">読み込む<input type="file" id="load" accept=".json" hidden></label>
  <button id="clear">印をすべて外す</button>
</div>
<main>
  <h1 id="title"></h1>
  <div class="mute" id="concept"></div>

  <div class="panel warn small" id="warnings"></div>

  <div id="analysisWrap" class="panel" hidden><h3>考察</h3><div id="analysis" style="white-space:pre-wrap"></div></div>

  <h2>条件ごとの比較</h2>
  <div class="panel"><table id="summary"></table></div>
  <div class="tabs" id="tabs"></div>

  <div class="panel small">
    <div class="legend">
      <span><i class="dot" style="background:var(--pass)"></i>機械: 通過（p ≥ 足切り）</span>
      <span><i class="dot" style="background:var(--rej)"></i>機械: 不通過</span>
      <span><i class="dot" style="background:var(--flag)"></i>人間: 機械の判定に同意しない（クリックで印を付け外し）</span>
    </div>
    <div class="mute">レビューのしかた: 全体を眺め、<b>機械の判定に同意できない画像だけ</b>クリックする。通過なのに NG なものと、不通過なのに OK なものの両方に印を付ける。印のない画像は「同意」として数える。<b>条件（モデルや型）は、比較表の下のタブで切り替える。各タブを最後まで見て、条件ごとの「最後まで見た」にチェックする（タブの ✔ / 未 が目印）。</b>見終わったら「review.json に保存」を押す。<code>python3 tools/serve_runs.py</code> で開いたページなら、この HTML と同じディレクトリに書き込まれる。</div>
  </div>

  <div id="conditions"></div>
</main>
<script>
const DATA = __DATA__;
const KEY = "review:" + DATA.run_id;
let state = JSON.parse(localStorage.getItem(KEY) || '{"flags":[]}');
const flags = new Set(state.flags || []);
// 旧形式（reviewed: true だけ）は、条件が 1 つの run のときだけ「その条件を見た」とみなす。複数条件の run では未確認に戻す
const reviewedConds = new Set(state.reviewed_conditions || (state.reviewed && DATA.conditions.length === 1 ? [DATA.conditions[0].name] : []));
const $ = (s) => document.querySelector(s);
// 表示中の条件タブ。URL のハッシュ（#cond=名前）に残す。なければ、最初の未確認の条件
let active = (() => {
  const h = decodeURIComponent((location.hash.match(/^#cond=(.*)$/) || [])[1] || "");
  if (DATA.conditions.some(c => c.name === h)) return h;
  const firstTodo = DATA.conditions.find(c => !reviewedConds.has(c.name));
  return (firstTodo || DATA.conditions[0]).name;
})();
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const pct = (a, b) => b ? (100 * a / b).toFixed(0) + "%" : "-";
const median = (xs) => { const s = [...xs].sort((a,b)=>a-b), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m-1] + s[m]) / 2; };

$("#title").textContent = DATA.title;
$("#concept").textContent = DATA.concept;
if (DATA.analysis) { $("#analysisWrap").hidden = false; $("#analysis").textContent = DATA.analysis; }
$("#warnings").innerHTML = DATA.warnings.map(w => "・" + esc(w)).join("<br>");

function save() {
  state = { reviewed_conditions: [...reviewedConds], flags: [...flags] };
  localStorage.setItem(KEY, JSON.stringify(state));
}

function renderTabs() {
  const box = $("#tabs");
  box.innerHTML = "";
  for (const c of DATA.conditions) {
    const done = reviewedConds.has(c.name);
    const nflag = c.items.filter(i => flags.has(i.id)).length;
    const b = document.createElement("button");
    b.className = "tab" + (c.name === active ? " active" : "");
    b.innerHTML = `${esc(c.name)}<span class="st ${done ? "ok" : "todo"}">${done ? "✔" : "未"}</span><span class="cnt">${c.items.length} 枚 / 印 ${nflag}</span>`;
    b.addEventListener("click", () => {
      active = c.name;
      history.replaceState(null, "", "#cond=" + encodeURIComponent(active));
      render(); renderTabs();
    });
    box.appendChild(b);
  }
}

function summarize() {
  let html = "<tr><th>条件</th><th class='num'>枚数</th><th class='num'>機械 通過</th><th class='num'>通過率</th><th>参考（LLM 側の仕分け）</th><th class='num'>p 平均</th><th class='num'>p 中央値</th><th class='num' title='条件内の画像どうしの CLIP 類似度の平均。高いほど似た絵が並んでいる'>類似度</th>"
    + "<th class='num'>印 通過→NG</th><th class='num'>印 不通過→OK</th><th class='num'>人間 OK 率</th><th class='num'>一致率</th><th>確認</th></tr>";
  for (const c of DATA.conditions) {
    const n = c.items.length, passed = c.items.filter(i => i.pass).length;
    const fp = c.items.filter(i => i.pass && flags.has(i.id)).length;
    const fr = c.items.filter(i => !i.pass && flags.has(i.id)).length;
    const humanOk = passed - fp + fr;
    const reviewed = reviewedConds.has(c.name);
    html += `<tr><td>${esc(c.name)}</td><td class="num">${n}</td><td class="num">${passed}</td><td class="num">${pct(passed, n)}</td>`
      + `<td class="small mute">${esc(c.reference || "")}</td><td class="num">${(c.items.reduce((a,i)=>a+i.p,0)/n).toFixed(3)}</td><td class="num">${median(c.items.map(i=>i.p)).toFixed(3)}</td><td class="num">${c.diversity == null ? "-" : c.diversity.toFixed(2)}</td>`
      + `<td class="num">${fp}</td><td class="num">${fr}</td>`
      + `<td class="num">${reviewed ? pct(humanOk, n) : "未確認"}</td><td class="num">${reviewed ? pct(n - fp - fr, n) : "未確認"}</td><td>${reviewed ? "✔" : "<span style='color:var(--flag)'>未</span>"}</td></tr>`;
  }
  $("#summary").innerHTML = html;
  $("#flagcount").textContent = `印: ${flags.size} 件`;
  const left = DATA.conditions.filter(c => !reviewedConds.has(c.name)).map(c => c.name);
  const total = DATA.conditions.length;
  $("#unreviewed").textContent = left.length ? `確認済み ${total - left.length} / ${total} 条件（未: ${left.join("、")}）` : `全 ${total} 条件を確認済み`;
  $("#unreviewed").style.color = left.length ? "var(--flag)" : "var(--pass)";
  renderTabs();
}

function render() {
  const root = $("#conditions");
  root.innerHTML = "";
  for (const c of DATA.conditions.filter(x => x.name === active)) {
    const sec = document.createElement("section");
    const sorted = [...c.items].sort((a, b) => b.p - a.p);
    const p = c.params;
    sec.innerHTML = `<h2>${esc(c.name)} <label class="btn small" style="font-weight:400"><input type="checkbox" class="rc"${reviewedConds.has(c.name) ? " checked" : ""}> この条件を最後まで見た</label></h2>`
      + `<div class="small mute">model: ${esc(c.model)}<br>prefix: ${esc(p.prompt_prefix || "(なし)")}<br>suffix: ${esc(p.prompt_suffix || "(なし)")}<br>negative: ${esc(p.negative_prompt || "(なし)")}</div>`;
    sec.querySelector(".rc").addEventListener("change", (e) => {
      e.target.checked ? reviewedConds.add(c.name) : reviewedConds.delete(c.name);
      save(); summarize();
    });
    const grid = document.createElement("div");
    grid.className = "grid";
    let dividerDone = false;
    for (const it of sorted) {
      if (!it.pass && !dividerDone) {
        dividerDone = true;
        const d = document.createElement("div");
        d.className = "divider";
        d.textContent = `足切り線 p = ${DATA.threshold} ── これより下は機械が「不通過」`;
        grid.appendChild(d);
      }
      const card = document.createElement("div");
      card.className = "card " + (it.pass ? "pass" : "rej") + (flags.has(it.id) ? " flagged" : "");
      card.dataset.id = it.id;
      card.title = it.prompt;
      card.innerHTML = `<img loading="lazy" src="images/${esc(it.id)}.png"><span class="p">${it.p.toFixed(3)}</span><span class="flag">不一致</span>`
        + `<div class="meta"><b>${esc(it.id)}</b> ${it.label ? `<span class="lbl">[${esc(it.label)}]</span> ` : ""}<span class="mute">${esc(it.text)}</span></div>`;
      card.addEventListener("click", () => {
        flags.has(it.id) ? flags.delete(it.id) : flags.add(it.id);
        card.classList.toggle("flagged", flags.has(it.id));
        save(); summarize();
      });
      grid.appendChild(card);
    }
    sec.appendChild(grid);
    root.appendChild(sec);
  }
}

function reviewBody() {
  return { run_id: DATA.run_id, reviewed: DATA.conditions.every(c => reviewedConds.has(c.name)), reviewed_conditions: [...reviewedConds].sort(), reviewed_at: new Date().toISOString(),
           meaning: "flags = 機械の判定（scores.json の pass）に同意しない画像。印のない画像は、reviewed_conditions に入っている条件の中でだけ「同意」とみなす", flags: [...flags].sort() };
}
if (location.protocol === "file:") {
  $("#savestatus").textContent = "同じディレクトリへ保存するには、python3 tools/serve_runs.py で開いてください。";
} else {
  $("#backlink").hidden = false;
}
$("#download").addEventListener("click", async () => {
  const status = $("#savestatus");
  const text = JSON.stringify(reviewBody(), null, 2) + "\n";
  try {
    const res = await fetch("review.json", { method: "PUT", headers: { "Content-Type": "application/json" }, body: text });
    if (!res.ok) throw new Error("HTTP " + res.status);
    status.style.color = "var(--pass)";
    status.textContent = "保存しました: review.json（このページと同じ場所）";
  } catch (err) {
    status.style.color = "var(--flag)";
    status.textContent = "保存できません。python3 tools/serve_runs.py で開いてください。";
  }
});
$("#load").addEventListener("change", async (e) => {
  const f = e.target.files[0]; if (!f) return;
  const r = JSON.parse(await f.text());
  flags.clear(); (r.flags || []).forEach(x => flags.add(x));
  reviewedConds.clear(); (r.reviewed_conditions || (r.reviewed && DATA.conditions.length === 1 ? [DATA.conditions[0].name] : [])).forEach(x => reviewedConds.add(x));
  save(); render(); summarize();
});
$("#clear").addEventListener("click", () => { if (confirm("印と「最後まで見た」をすべて外しますか？")) { flags.clear(); reviewedConds.clear(); save(); render(); summarize(); } });

render(); summarize();
if (DATA.review) { /* review.json が run 直下にある場合は初期値として使う（localStorage が空のときだけ） */
  if (!localStorage.getItem(KEY)) {
    DATA.review.flags.forEach(x => flags.add(x));
    (DATA.review.reviewed_conditions || (DATA.review.reviewed && DATA.conditions.length === 1 ? [DATA.conditions[0].name] : [])).forEach(x => reviewedConds.add(x));
    save(); render(); summarize();
  }
}
</script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--serve", action="store_true", help="作ったあと、tools/serve_runs.py の一覧サーバーでこのレポートを開く")
    ap.add_argument("--port", type=int, default=0, help="--serve のポート。0 なら 8765 以降の空きを使う")
    args = ap.parse_args()

    run_dir = args.run_dir.resolve()
    for need in ("spec.json", "scores.json"):
        if not (run_dir / need).exists():
            print(f"{need} がありません。先に生成と採点を実行してください", file=sys.stderr)
            return 1
    spec = json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))
    scores = json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))
    metrics_path = REPO_ROOT / "scorers" / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    review_path = run_dir / "review.json"
    review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else None

    texts = {f"{c['name']}-{it['id']}": it["text"] for c in spec["conditions"] for it in c["items"]}
    labels = {f"{c['name']}-{it['id']}": it.get("label", "") for c in spec["conditions"] for it in c["items"]}
    conditions = []
    for c in spec["conditions"]:
        items = []
        for s in scores["items"]:
            if s["condition"] != c["name"]:
                continue
            meta = json.loads((run_dir / "images" / f"{s['id']}.json").read_text(encoding="utf-8"))
            items.append({"id": s["id"], "p": s["p"], "pass": s["pass"], "text": texts.get(s["id"], ""), "label": labels.get(s["id"], ""), "prompt": meta["prompt"]})
        sm = c.get("sampler", spec["sampler"])
        model = f"{c.get('checkpoint', spec['checkpoint'])} / {c.get('width', spec['width'])}x{c.get('height', spec['height'])} / {sm['sampler_name']} {sm['steps']} steps, cfg {sm['cfg']}"
        conditions.append(
            {
                "name": c["name"],
                "model": model,
                "reference": c.get("reference", ""),
                "diversity": scores.get("conditions", {}).get(c["name"], {}).get("mean_pairwise_cosine"),
                "params": {k: c.get(k, "") for k in ("prompt_prefix", "prompt_suffix", "negative_prompt")},
                "items": items,
            }
        )

    cutoff = scores["scorer"]["cutoff"]
    nested = metrics.get("nested_cv", {}).get("auc")
    color = metrics.get("color_baseline", {}).get("nested_cv", {}).get("auc")
    lob = metrics.get("leave_one_batch", {}).get("auc")
    warnings = [
        f"機械の判定は、人間が仕分けた画像（like {metrics.get('data', {}).get('like', '?')} / dislike {metrics.get('data', {}).get('dislike', '?')}）で学習した分類器のスコアです。"
        f"学習データでの目安: AUC {nested}（色だけの基準 {color}、バッチ外 {lob}）。足切りは like を {cutoff['like_recall']:.0%} 残したとき dislike の {cutoff['dislike_rejected']:.0%} を落とす値です。",
        "学習データは LLM 側（Cursor の GenerateImage）で作った画像です。この run は ComfyUI の別モデルで作っているため、分布がずれています。絶対値（通過率）より、同じ run 内の条件間の比較を見てください。",
        "枚数が少ない run では、通過率の差は偶然でも出ます。条件を比べるときは同じ seed・同じ項目で揃えた差を見てください。",
    ]
    if spec.get("note"):
        warnings.insert(0, "メモ: " + spec["note"])

    data = {
        "run_id": run_dir.name,
        "title": f"実験レポート: {run_dir.name}",
        "concept": spec.get("concept", ""),
        "threshold": cutoff["threshold"],
        "warnings": warnings,
        "conditions": conditions,
        "review": review,
        "analysis": (run_dir / "analysis.md").read_text(encoding="utf-8") if (run_dir / "analysis.md").exists() else "",
    }
    html = HTML.replace("__TITLE__", f"実験レポート {run_dir.name}").replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    out = run_dir / "report.html"
    out.write_text(html, encoding="utf-8")
    print(f"→ {out}")
    if args.serve:
        from serve_runs import RUNS_DIR, serve

        if run_dir.parent != RUNS_DIR.resolve():
            print("--serve は runs/ 直下の run だけ使えます", file=sys.stderr)
            return 1
        return serve(f"/{run_dir.name}/report.html", args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
