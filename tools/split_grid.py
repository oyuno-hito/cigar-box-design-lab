#!/usr/bin/env python3
"""グリッド状に並べた画像シートを 1 枚ずつに切り出し、generated/99_inbox に保存する。

LLM の画像生成は、1 枚ずつ呼ぶより「複数マスのシートを 1 回で作る」方が効率がよい。
このスクリプトは、そのシートを切り出して、画像ごとにメタデータ（.json）を付ける。

出力はすべて 3:2（既定。--ratio で変更可）に揃える。マスの比率が違う場合は、
中央から 3:2 で切り出す。1:1 のシートなら 4 列 x 6 行（既定）で、マスがほぼ 3:2 になる。

使い方（リポジトリのルートで）:

    uv run tools/split_grid.py SHEET.png --meta sheet-meta.json

sheet-meta.json の例:

    {
      "prompt": "シート全体のプロンプト",
      "source": "cursor-generateimage",
      "cells": ["r1c1 の説明", "r1c2 の説明", ...]   // 省略可。行優先で rows*cols 個
    }

画像ごとの JSON は source / prompt / cell_description だけを書く。
溝（白い区切り）の位置は自動検出する。検出できなければ等分にフォールバックする。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent


def find_bands(is_gutter: np.ndarray, expected: int, min_len: int) -> list[tuple[int, int]] | None:
    """溝でない連続区間（= セル）を返す。個数が expected と合わなければ None。"""
    bands: list[tuple[int, int]] = []
    start = None
    for i, gutter in enumerate(is_gutter):
        if not gutter and start is None:
            start = i
        elif gutter and start is not None:
            if i - start >= min_len:
                bands.append((start, i))
            start = None
    if start is not None and len(is_gutter) - start >= min_len:
        bands.append((start, len(is_gutter)))
    return bands if len(bands) == expected else None


def equal_bands(length: int, n: int) -> list[tuple[int, int]]:
    return [(round(length * i / n), round(length * (i + 1) / n)) for i in range(n)]


def detect_cells(
    img: Image.Image, rows: int, cols: int, white: int, ratio: float
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], bool]:
    """(行の範囲, 列の範囲, 自動検出に成功したか) を返す。"""
    arr = np.asarray(img.convert("RGB"))
    near_white = (arr >= white).all(axis=2)
    col_gutter = near_white.mean(axis=0) >= ratio
    row_gutter = near_white.mean(axis=1) >= ratio
    xs = find_bands(col_gutter, cols, min_len=img.width // (cols * 4))
    ys = find_bands(row_gutter, rows, min_len=img.height // (rows * 4))
    if xs is not None and ys is not None:
        return ys, xs, True
    return equal_bands(img.height, rows), equal_bands(img.width, cols), False


def crop_to_ratio(box: tuple[int, int, int, int], aspect: float) -> tuple[int, int, int, int]:
    """box の中央から、横/縦 = aspect になるように切り出した box を返す。"""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w / h > aspect:  # 横に長すぎる → 左右を削る
        new_w = round(h * aspect)
        x0 += (w - new_w) // 2
        x1 = x0 + new_w
    else:  # 縦に長い → 上下を削る
        new_h = round(w / aspect)
        y0 += (h - new_h) // 2
        y1 = y0 + new_h
    return x0, y0, x1, y1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sheet", type=Path, help="シート画像")
    p.add_argument("--rows", type=int, default=6)
    p.add_argument("--cols", type=int, default=4)
    p.add_argument("--meta", type=Path, help="プロンプト等の JSON（上記の形式）")
    p.add_argument("--out", type=Path, default=REPO_ROOT / "generated" / "99_inbox")
    p.add_argument("--ratio", type=float, default=3 / 2, help="出力の 横/縦（既定 3:2）")
    p.add_argument("--inset", type=int, default=3, help="切り出し時に各辺から削る px（縁の滲み除去）")
    p.add_argument("--white", type=int, default=245, help="溝とみなす白の下限（0-255）")
    p.add_argument("--gutter-ratio", type=float, default=0.97, help="行・列のうち白がこの割合以上なら溝")
    p.add_argument("--dry-run", action="store_true", help="保存せず、検出した範囲だけ表示")
    args = p.parse_args()

    meta = json.loads(args.meta.read_text(encoding="utf-8")) if args.meta else {}
    cells = meta.get("cells") or []
    if cells and len(cells) != args.rows * args.cols:
        print(f"cells の数({len(cells)})が rows*cols({args.rows * args.cols})と違います", file=sys.stderr)
        return 1

    img = Image.open(args.sheet).convert("RGB")
    ys, xs, detected = detect_cells(img, args.rows, args.cols, args.white, args.gutter_ratio)
    print(f"シート {img.width}x{img.height}: 溝の自動検出 = {'成功' if detected else '失敗（等分にフォールバック）'}")
    print("  行:", ys)
    print("  列:", xs)
    if args.dry_run:
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    args.out.mkdir(parents=True, exist_ok=True)

    for r, (y0, y1) in enumerate(ys):
        for c, (x0, x1) in enumerate(xs):
            box = (x0 + args.inset, y0 + args.inset, x1 - args.inset, y1 - args.inset)
            tile = img.crop(crop_to_ratio(box, args.ratio))
            name = f"{stamp}-r{r + 1}c{c + 1}"
            tile.save(args.out / f"{name}.png")
            record = {
                "source": meta.get("source", "unknown"),
                "prompt": meta.get("prompt", ""),
                "cell_description": cells[r * args.cols + c] if cells else "",
            }
            (args.out / f"{name}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    print(f"{args.rows * args.cols} 枚を {args.out} に保存しました（接頭辞 {stamp}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
