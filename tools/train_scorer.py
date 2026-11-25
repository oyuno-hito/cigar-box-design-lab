#!/usr/bin/env python3
"""generated/ の仕分け結果から分類器（スコアラー）を作り、scorers/ に保存する（上書き。版は Git の履歴で管理）。

    uv run tools/train_scorer.py            # 学習して scorers/ の JSON を上書き
    uv run tools/train_scorer.py --dry-run  # 評価だけ（保存しない）

方針（docs/workflow.md、generated/README.md、scorers/README.md を参照）:
  - like     = 0_like/0_reference + 0_like/1_seed（同じ重みで 1 クラスにまとめる）
  - dislike  = 1_dislike
  - 2_maybe  = 学習に使わない。学習後に採点だけして、metrics.json に分布を残す
  - 画像は CLIP の画像埋め込み（L2 正規化）にして、ロジスティック回帰で like の確率を出す
  - pickle は使わず、係数を JSON で保存する（scorer.json）

評価（metrics.json）:
  - nested_cv:       繰り返し層化 5 分割 CV。C は内側 CV で選ぶ（楽観的にならないように）
  - leave_one_batch: セット（同じ時刻の接頭辞 = 同じシート）ごと丸ごと外す CV。別の方向でも通用するかを見る
  - color_baseline:  色の特徴量だけで同じ評価をしたもの。埋め込みがこれを超えていないなら、配色を学んでいるだけ
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image
from sklearn.linear_model import LogisticRegression, LogisticRegressionCV
from sklearn.metrics import balanced_accuracy_score, roc_auc_score
from sklearn.model_selection import RepeatedStratifiedKFold

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATED = REPO_ROOT / "generated"
SCORERS = REPO_ROOT / "scorers"
CACHE = REPO_ROOT / "generator" / "temp" / "embeddings"

LIKE_DIRS = ["0_like/0_reference", "0_like/1_seed"]
DISLIKE_DIRS = ["1_dislike"]
MAYBE_DIRS = ["2_maybe"]

MODEL_ID = "openai/clip-vit-base-patch32"
CLIP_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
CLIP_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
CS = np.logspace(-2, 2, 9)
SEED = 0


# ---------------------------------------------------------------- データ読み込み
def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_items() -> list[dict]:
    items: list[dict] = []
    for dirs, label in ((LIKE_DIRS, "like"), (DISLIKE_DIRS, "dislike"), (MAYBE_DIRS, "maybe")):
        for d in dirs:
            for png in sorted((GENERATED / d).glob("*.png")):
                items.append(
                    {
                        "id": png.stem,
                        "path": png,
                        "label": label,
                        "dir": d,
                        "batch": png.stem.split("-r")[0],  # 20261124-HHMMSS
                        "sha256": sha256(png),
                    }
                )
    return items


# ---------------------------------------------------------------- 特徴量
def model_revision() -> str:
    """ダウンロード済みモデルの commit hash（HF キャッシュの refs/main）。"""
    from huggingface_hub import constants

    ref = Path(constants.HF_HUB_CACHE) / ("models--" + MODEL_ID.replace("/", "--")) / "refs" / "main"
    return ref.read_text().strip() if ref.exists() else "unknown"


def clip_embeddings(items: list[dict]) -> tuple[np.ndarray, str]:
    """CLIP の画像埋め込み（L2 正規化済み）。ファイルのハッシュでキャッシュする。"""
    import torch
    from transformers import CLIPModel

    model = CLIPModel.from_pretrained(MODEL_ID).eval()
    revision = model_revision()
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / f"clip-b32-{revision[:12]}.npz"
    cached: dict[str, np.ndarray] = {}
    if cache_file.exists():
        z = np.load(cache_file)
        cached = {k: z[k] for k in z.files}

    todo = [it for it in items if it["sha256"] not in cached]
    if todo:
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        model = model.to(device)
        for i in range(0, len(todo), 32):
            chunk = todo[i : i + 32]
            # 切り抜きで端を失わないよう、中央切り抜きではなく 224x224 に縮めて入れる（全画像で同じ扱い）
            arr = np.stack(
                [
                    (np.asarray(Image.open(it["path"]).convert("RGB").resize((224, 224), Image.BICUBIC), dtype=np.float32) / 255.0 - CLIP_MEAN)
                    / CLIP_STD
                    for it in chunk
                ]
            )
            x = torch.from_numpy(arr).permute(0, 3, 1, 2).to(device)
            with torch.no_grad():
                out = model.get_image_features(pixel_values=x)
            feats = out if isinstance(out, torch.Tensor) else out.pooler_output
            feats = torch.nn.functional.normalize(feats, dim=-1).cpu().numpy()
            for it, f in zip(chunk, feats):
                cached[it["sha256"]] = f.astype(np.float32)
        np.savez(cache_file, **cached)
    return np.stack([cached[it["sha256"]] for it in items]), revision


def color_features(items: list[dict]) -> np.ndarray:
    """色だけの特徴量（比較用）。HSV の 4x4x4 ヒストグラムと、平均・標準偏差。"""
    rows = []
    for it in items:
        im = Image.open(it["path"]).convert("RGB").resize((64, 64))
        hsv = np.asarray(im.convert("HSV"), dtype=np.float32) / 255.0
        rgb = np.asarray(im, dtype=np.float32) / 255.0
        idx = np.minimum((hsv * 4).astype(int), 3)
        hist = np.zeros((4, 4, 4), dtype=np.float32)
        np.add.at(hist, (idx[..., 0], idx[..., 1], idx[..., 2]), 1)
        hist = (hist / hist.sum()).ravel()
        rows.append(np.concatenate([hist, rgb.mean((0, 1)), rgb.std((0, 1)), hsv.mean((0, 1)), hsv.std((0, 1))]))
    X = np.stack(rows)
    return (X - X.mean(0)) / (X.std(0) + 1e-6)


# ---------------------------------------------------------------- モデルと評価
def make_cv_model() -> LogisticRegressionCV:
    return LogisticRegressionCV(
        Cs=CS, cv=5, scoring="roc_auc", class_weight="balanced", max_iter=5000, random_state=SEED
    )


def summarize(y: np.ndarray, p: np.ndarray) -> dict:
    return {
        "auc": round(float(roc_auc_score(y, p)), 4),
        "balanced_accuracy@0.5": round(float(balanced_accuracy_score(y, p >= 0.5)), 4),
    }


def nested_cv(X: np.ndarray, y: np.ndarray, repeats: int = 5) -> tuple[dict, np.ndarray]:
    """繰り返し層化 5 分割。1 サンプルあたりの out-of-fold 確率を、繰り返しで平均して返す。"""
    rskf = RepeatedStratifiedKFold(n_splits=5, n_repeats=repeats, random_state=SEED)
    sums, counts = np.zeros(len(y)), np.zeros(len(y))
    aucs = []
    for tr, te in rskf.split(X, y):
        m = make_cv_model().fit(X[tr], y[tr])
        p = m.predict_proba(X[te])[:, 1]
        sums[te] += p
        counts[te] += 1
        aucs.append(roc_auc_score(y[te], p))
    oof = sums / counts
    res = summarize(y, oof)
    res["auc_fold_mean"] = round(float(np.mean(aucs)), 4)
    res["auc_fold_std"] = round(float(np.std(aucs)), 4)
    return res, oof


def leave_one_batch(X: np.ndarray, y: np.ndarray, batches: np.ndarray) -> dict:
    """セット（バッチ）ごと丸ごと外して予測する。別の方向のセットに通用するかを見る。"""
    pred = np.full(len(y), np.nan)
    per_batch = {}
    for b in sorted(set(batches)):
        te = batches == b
        tr = ~te
        if len(set(y[tr])) < 2:
            continue
        m = make_cv_model().fit(X[tr], y[tr])
        pred[te] = m.predict_proba(X[te])[:, 1]
        yb = y[te]
        entry = {"n": int(te.sum()), "n_like": int(yb.sum())}
        if 0 < yb.sum() < len(yb):
            entry["auc"] = round(float(roc_auc_score(yb, pred[te])), 4)
        per_batch[b] = entry
    ok = ~np.isnan(pred)
    res = summarize(y[ok], pred[ok])
    res["per_batch"] = per_batch
    return res


def cutoff_threshold(y: np.ndarray, oof: np.ndarray, like_recall: float = 0.9) -> dict:
    """足切りのしきい値: like の再現率が like_recall 以上になる、最大のしきい値。"""
    like_scores = np.sort(oof[y == 1])
    k = int(np.floor((1 - like_recall) * len(like_scores)))
    thr = float(like_scores[k])
    return {
        "threshold": round(thr, 4),
        "target_like_recall": like_recall,
        "like_recall": round(float((oof[y == 1] >= thr).mean()), 4),
        "dislike_rejected": round(float((oof[y == 0] < thr).mean()), 4),
        "note": "nested CV の out-of-fold 確率で決めた値。like を 9 割残したときに、dislike を何割落とせるか",
    }


# ---------------------------------------------------------------- 保存
def git_info() -> dict:
    def run(*a: str) -> str:
        return subprocess.run(["git", *a], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()

    return {"commit": run("rev-parse", "HEAD") or None, "dirty": bool(run("status", "--porcelain"))}




def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="評価だけして保存しない")
    ap.add_argument("--repeats", type=int, default=5, help="CV の繰り返し回数")
    args = ap.parse_args()
    warnings.filterwarnings("ignore")

    items = load_items()
    train = [it for it in items if it["label"] in ("like", "dislike")]
    maybe = [it for it in items if it["label"] == "maybe"]
    y = np.array([1 if it["label"] == "like" else 0 for it in train])
    batches = np.array([it["batch"] for it in train])
    print(f"学習: like {int(y.sum())} / dislike {int((1 - y).sum())}（maybe {len(maybe)} は学習に使わない）")

    print("埋め込みを計算中（初回はモデルのダウンロードあり）...")
    X_all, revision = clip_embeddings(train + maybe)
    X, X_maybe = X_all[: len(train)], X_all[len(train) :]
    Xc = color_features(train)

    print("評価中...")
    metrics = {
        "data": {"like": int(y.sum()), "dislike": int((1 - y).sum()), "maybe_unused": len(maybe)},
        "baseline_chance": {"auc": 0.5, "balanced_accuracy@0.5": 0.5},
    }
    metrics["nested_cv"], oof = nested_cv(X, y, args.repeats)
    metrics["leave_one_batch"] = leave_one_batch(X, y, batches)
    metrics["color_baseline"] = {
        "nested_cv": nested_cv(Xc, y, args.repeats)[0],
        "leave_one_batch": leave_one_batch(Xc, y, batches),
    }
    metrics["cutoff"] = cutoff_threshold(y, oof)

    final = make_cv_model().fit(X, y)
    c_final = float(final.C_[0])
    model = LogisticRegression(C=c_final, class_weight="balanced", max_iter=5000).fit(X, y)
    p_maybe = model.predict_proba(X_maybe)[:, 1] if len(maybe) else np.array([])
    metrics["maybe_scores"] = {
        "n": len(maybe),
        "mean": round(float(p_maybe.mean()), 4) if len(maybe) else None,
        "oof_like_mean": round(float(oof[y == 1].mean()), 4),
        "oof_dislike_mean": round(float(oof[y == 0].mean()), 4),
        "note": "maybe を学習後のモデルで採点した平均。like と dislike の out-of-fold 平均の間に入るのが自然",
    }
    metrics["selected_C"] = c_final
    metrics["seed"] = SEED

    print(json.dumps({k: v for k, v in metrics.items() if k != "leave_one_batch"}, ensure_ascii=False, indent=2))
    lob = metrics["leave_one_batch"]
    print("leave_one_batch:", {k: v for k, v in lob.items() if k != "per_batch"})
    for b, e in lob["per_batch"].items():
        print(f"  {b}: {e}")
    if args.dry_run:
        return 0

    out = SCORERS
    out.mkdir(exist_ok=True)
    scorer = {
        "type": "logistic_regression",
        "positive_class": "like",
        "embedding": {
            "model_id": MODEL_ID,
            "revision": revision,
            "preprocess": "RGB -> 224x224 bicubic resize (no crop) -> CLIP mean/std -> image features -> L2 normalize",
        },
        "coef": [round(float(v), 6) for v in model.coef_[0]],
        "intercept": round(float(model.intercept_[0]), 6),
        "C": c_final,
        "class_weight": "balanced",
        "cutoff": metrics["cutoff"],
        "usage": "p = sigmoid(coef . embedding + intercept)。足切りは p >= cutoff.threshold",
    }
    manifest = {
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "git": git_info(),
        "label_policy": {
            "like": LIKE_DIRS,
            "dislike": DISLIKE_DIRS,
            "not_used_for_training": MAYBE_DIRS,
            "note": "reference と seed は同じ重みで like にまとめた",
        },
        "embedding": scorer["embedding"],
        "counts": metrics["data"],
        "images": [{"id": it["id"], "sha256": it["sha256"], "label": it["label"], "dir": it["dir"]} for it in train],
        "unused_images": [{"id": it["id"], "sha256": it["sha256"], "label": it["label"], "dir": it["dir"]} for it in maybe],
    }
    for name, data in (("scorer.json", scorer), ("manifest.json", manifest), ("metrics.json", metrics)):
        (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{out} に保存しました（以前の版は Git の履歴で見る）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
