#!/usr/bin/env python3
"""実験 run の画像を、scorers/ の分類器で採点して runs/<run-id>/scores.json に書く。

    python3 tools/score_run.py runs/<run-id>

p = sigmoid(coef · 埋め込み + intercept)（like らしさ）。足切りは scorers/scorer.json の cutoff.threshold。
画像の前処理・埋め込みは tools/train_scorer.py と同じものを使う（import して再利用）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_scorer import SCORERS, clip_embeddings, git_info, sha256  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    args = ap.parse_args()

    run_dir = args.run_dir.resolve()
    pngs = sorted((run_dir / "images").glob("*.png"))
    if not pngs:
        print("images/ に画像がありません。先に tools/run_generate.py を実行してください", file=sys.stderr)
        return 1

    scorer = json.loads((SCORERS / "scorer.json").read_text(encoding="utf-8"))
    items = [{"id": p.stem, "path": p, "sha256": sha256(p)} for p in pngs]
    X, revision = clip_embeddings(items)
    if revision != scorer["embedding"]["revision"]:
        print(f"警告: 埋め込みモデルの revision が学習時と違います（{revision} / 学習時 {scorer['embedding']['revision']}）", file=sys.stderr)

    z = X @ np.array(scorer["coef"], dtype=np.float64) + scorer["intercept"]
    p = 1.0 / (1.0 + np.exp(-z))
    threshold = scorer["cutoff"]["threshold"]

    result = {
        "scored_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scorer": {
            "embedding": scorer["embedding"],
            "cutoff": scorer["cutoff"],
            "git": git_info(),
        },
        "items": [
            {"id": it["id"], "condition": it["id"].rsplit("-", 1)[0], "p": round(float(pi), 4), "pass": bool(pi >= threshold)}
            for it, pi in zip(items, p)
        ],
    }
    (run_dir / "scores.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    by_cond: dict[str, list[float]] = {}
    for r in result["items"]:
        by_cond.setdefault(r["condition"], []).append(r["p"])
    for c, ps in by_cond.items():
        passed = sum(v >= threshold for v in ps)
        print(f"{c}: {len(ps)} 枚 / 通過 {passed}（{passed / len(ps):.0%}）/ p 平均 {np.mean(ps):.3f}")
    print(f"→ {run_dir / 'scores.json'}（足切り p >= {threshold}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
