#!/usr/bin/env python3
"""runs/ 以下のすべての run を横断して、条件ごとの打率を一覧にする。標準ライブラリのみ。

    uv run tools/summarize_runs.py                  # runs/ 全体
    uv run tools/summarize_runs.py runs/<run-id>…   # 指定した run だけ

打率 = 人間 OK 率（確認済みの条件だけ）。印のない画像は、確認済みの条件の中でだけ「機械に同意」として数える。
  機械が通過 → 印なし = OK / 印あり = NG
  機械が不通過 → 印なし = NG / 印あり = OK
「明確なものだけ印を付けた」判定なので、厳密な精度ではなく、条件どうしの比較の目安として読む。
未確認の条件は、機械の通過率だけを出す（人間 OK 率は「-」）。

列: 類似度 = 条件内の画像どうしの CLIP 類似度の平均（高いほど似た絵が並んでいる。打率が上がっても類似度が急に上がるなら、同じ絵に寄っているだけ）
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / "runs"


def load(run: Path) -> list[dict]:
    if not (run / "scores.json").exists():
        return []
    scores = json.loads((run / "scores.json").read_text(encoding="utf-8"))
    rev = json.loads((run / "review.json").read_text(encoding="utf-8")) if (run / "review.json").exists() else {}
    conds = sorted({it["condition"] for it in scores["items"]})
    reviewed = set(rev.get("reviewed_conditions") or (conds if rev.get("reviewed") and len(conds) == 1 else []))
    flags = set(rev.get("flags", []))
    rows = []
    for c in conds:
        items = [it for it in scores["items"] if it["condition"] == c]
        n = len(items)
        passed = sum(it["pass"] for it in items)
        row = {
            "run": run.name,
            "condition": c,
            "n": n,
            "machine_pass": passed / n,
            "diversity": scores.get("conditions", {}).get(c, {}).get("mean_pairwise_cosine"),
            "human_ok": None,
        }
        if c in reviewed:
            row["human_ok"] = sum(it["pass"] != (it["id"] in flags) for it in items) / n
            row["false_pass"] = sum(it["pass"] and it["id"] in flags for it in items)
            row["false_reject"] = sum((not it["pass"]) and it["id"] in flags for it in items)
        rows.append(row)
    return rows


def pct(x: float | None) -> str:
    return "-" if x is None else f"{x:.0%}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*", type=Path)
    ap.add_argument("--json", action="store_true", help="JSON で出す")
    args = ap.parse_args()
    dirs = [r.resolve() for r in args.runs] if args.runs else sorted(p for p in RUNS.iterdir() if p.is_dir())
    rows = [r for d in dirs for r in load(d)]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print(f"{'run':<32}{'条件':<22}{'n':>3}{'機械通過':>8}{'人間OK(打率)':>13}{'印(通過→NG/不通過→OK)':>22}{'類似度':>7}")
    for r in rows:
        marks = f"{r['false_pass']}/{r['false_reject']}" if r["human_ok"] is not None else "-"
        div = "-" if r["diversity"] is None else f"{r['diversity']:.2f}"
        print(f"{r['run'][16:]:<32}{r['condition']:<22}{r['n']:>3}{pct(r['machine_pass']):>8}{pct(r['human_ok']):>13}{marks:>22}{div:>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
