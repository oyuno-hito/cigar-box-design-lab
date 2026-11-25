#!/usr/bin/env python3
"""人間のレビュー（review.json）と分類器のスコア（scores.json）を比べる。標準ライブラリのみ。

    uv run tools/compare_review.py runs/<run-id>

人間の判定は、印のない画像を「機械に同意」として導く（レポートの「明確なものだけ印を付ける」運用）。
  機械が通過 → 印なし = OK / 印あり = NG
  機械が不通過 → 印なし = NG / 印あり = OK
「明確に違うものだけ印を付けた」判定なので、精度の厳密な値ではなく、閾値や並べ替えが使えるかの目安として読む。

出力:
  - 全体と条件ごとの AUC（スコアの高い画像ほど人間 OK か）
  - 足切り（学習時の閾値）での 適合率 / 再現率
  - 人間 OK を 8 割残せる閾値と、その閾値での 適合率 / 通過率
  - 上位 25% / 50% の 適合率（スコアの絶対値がずれていても使える、順位ベースの選び方）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def auc(pairs: list[tuple[float, int]]) -> float | None:
    pos = [p for p, y in pairs if y]
    neg = [p for p, y in pairs if not y]
    if not pos or not neg:
        return None
    wins = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
    return wins / (len(pos) * len(neg))


def stats(rows: list[dict], cutoff: float) -> dict:
    pairs = [(r["p"], r["human_ok"]) for r in rows]
    n, ok = len(rows), sum(r["human_ok"] for r in rows)
    passed = [r for r in rows if r["p"] >= cutoff]
    tp = sum(r["human_ok"] for r in passed)
    out = {
        "n": n,
        "human_ok": ok,
        "auc": auc(pairs),
        "at_cutoff": {
            "pass": len(passed),
            "precision": tp / len(passed) if passed else None,
            "recall": tp / ok if ok else None,
        },
    }
    ranked = sorted(rows, key=lambda r: -r["p"])
    for frac in (0.25, 0.5):
        k = max(1, round(n * frac))
        out[f"top{int(frac * 100)}%_precision"] = sum(r["human_ok"] for r in ranked[:k]) / k
    # 人間 OK を 8 割残せる最も高い閾値
    if ok:
        need = -(-ok * 8 // 10)
        got = 0
        thr = None
        for r in ranked:
            got += r["human_ok"]
            if got >= need:
                thr = r["p"]
                break
        sel = [r for r in rows if thr is not None and r["p"] >= thr]
        out["recall80"] = {
            "threshold": thr,
            "pass_rate": len(sel) / n,
            "precision": sum(r["human_ok"] for r in sel) / len(sel) if sel else None,
        }
    return out


def fmt(x: float | None, pct: bool = False) -> str:
    if x is None:
        return "-"
    return f"{x:.0%}" if pct else f"{x:.3f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    args = ap.parse_args()
    run = args.run_dir.resolve()
    scores = json.loads((run / "scores.json").read_text(encoding="utf-8"))
    review_path = run / "review.json"
    if not review_path.exists():
        print("review.json がありません。レポートで印を付けて書き出し、run のディレクトリに置いてください", file=sys.stderr)
        return 1
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if not review.get("reviewed"):
        print("警告: review.json の reviewed が false です（最後まで見ていない）。結果は参考にとどめてください", file=sys.stderr)
    flags = set(review.get("flags", []))
    # 確認済みの条件だけ使う。旧形式（reviewed だけ）は、条件が 1 つの run のときだけ全体を確認済みとみなす
    conds = {it["condition"] for it in scores["items"]}
    reviewed = set(review.get("reviewed_conditions") or (conds if review.get("reviewed") and len(conds) == 1 else []))
    skipped = sorted(conds - reviewed)
    if skipped:
        print(f"確認済みでない条件は集計から除きます: {', '.join(skipped)}", file=sys.stderr)
    scores["items"] = [it for it in scores["items"] if it["condition"] in reviewed]
    if not scores["items"]:
        print("確認済みの条件がありません", file=sys.stderr)
        return 1
    cutoff = scores["scorer"]["cutoff"]["threshold"]

    rows = []
    for it in scores["items"]:
        flagged = it["id"] in flags
        rows.append({**it, "human_ok": int(it["pass"] != flagged)})

    groups: dict[str, list[dict]] = {"(全体)": rows}
    for r in rows:
        groups.setdefault(r["condition"], []).append(r)

    print(f"足切り p >= {cutoff}（学習時）")
    print(f"{'条件':<24}{'n':>4}{'人間OK':>7}{'AUC':>7}{'通過':>5}{'適合率':>7}{'再現率':>7}{'上位25%':>8}{'上位50%':>8}  人間OKを8割残す閾値（通過率 / 適合率）")
    result = {}
    for name, rs in groups.items():
        s = stats(rs, cutoff)
        result[name] = s
        c = s["at_cutoff"]
        r80 = s.get("recall80", {})
        print(
            f"{name:<24}{s['n']:>4}{s['human_ok']:>7}{fmt(s['auc']):>7}{c['pass']:>5}{fmt(c['precision'], True):>7}{fmt(c['recall'], True):>7}"
            f"{fmt(s['top25%_precision'], True):>8}{fmt(s['top50%_precision'], True):>8}  "
            f"{fmt(r80.get('threshold'))}（{fmt(r80.get('pass_rate'), True)} / {fmt(r80.get('precision'), True)}）"
        )
    (run / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"→ {run / 'comparison.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
