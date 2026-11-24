#!/usr/bin/env python3
"""generated/ の整合性を確認する。問題があれば、理由を表示して終了コード 1 で終わる。

確認すること:
  1. generated/99_inbox/ に未分類の画像・JSON が残っていない（.gitkeep は除く）
  2. 画像（.png）と同名の .json が、同じディレクトリに 1 組ずつある

generated/999_sheet/（切り出し前の元シートとそのメタデータ）は、分類の対象ではないので検査しない。

正常なときは何も表示しない（警告を毎回出すと無視する習慣がつくため）。

--pairs-only は、画像と .json の組だけを見る。pre-commit から呼ぶ。
inbox の検査は pre-push で行い、意図して未分類のまま進めたいときだけ ALLOW_INBOX=1 で省略できる。

    ALLOW_INBOX=1 git push

標準ライブラリだけで動く。
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATED = REPO_ROOT / "generated"
INBOX = GENERATED / "99_inbox"
MEDIA_EXTS = {".png", ".json"}
# 分類の対象ではないディレクトリ（元シートなど）
SKIP_DIRS = {"999_sheet"}


def collect(root: Path) -> dict[str, dict[str, list[Path]]]:
    """{ ファイル名の stem: { 拡張子: [ディレクトリ, ...] } } を返す。"""
    found: dict[str, dict[str, list[Path]]] = defaultdict(lambda: defaultdict(list))
    for path in root.rglob("*"):
        if SKIP_DIRS & set(path.relative_to(root).parts):
            continue
        if path.is_file() and path.suffix in MEDIA_EXTS:
            found[path.stem][path.suffix].append(path.parent)
    return found


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pairs-only",
        action="store_true",
        help="画像と .json の組だけを確認する（pre-commit 用。inbox は見ない）",
    )
    args = parser.parse_args()
    errors: list[str] = []

    if not args.pairs_only and os.environ.get("ALLOW_INBOX") != "1" and INBOX.is_dir():
        left = sorted(p for p in INBOX.iterdir() if p.is_file() and p.name != ".gitkeep")
        if left:
            errors.append(
                f"{rel(INBOX)} に未分類のファイルが {len(left)} 個残っています"
                "（0_like / 1_dislike / 2_maybe へ移動してください）:"
            )
            errors += [f"    {rel(p)}" for p in left[:10]]
            if len(left) > 10:
                errors.append(f"    ... ほか {len(left) - 10} 個")

    pair_errors: list[str] = []
    for stem, exts in sorted(collect(GENERATED).items()):
        pngs, jsons = exts.get(".png", []), exts.get(".json", [])
        if len(pngs) == 1 and len(jsons) == 1 and pngs == jsons:
            continue
        if len(pngs) > 1 or len(jsons) > 1:
            pair_errors.append(f"    {stem}: 同名のファイルが複数あります（{[rel(d) for d in pngs + jsons]}）")
        elif not pngs:
            pair_errors.append(f"    {stem}: 画像がありません（.json のみ: {rel(jsons[0])}）")
        elif not jsons:
            pair_errors.append(f"    {stem}: .json がありません（画像: {rel(pngs[0])}）")
        else:
            pair_errors.append(
                f"    {stem}: 画像と .json の置き場所が違います（画像: {rel(pngs[0])}, .json: {rel(jsons[0])}）"
            )
    if pair_errors:
        errors.append("画像と .json の組が揃っていません（同じディレクトリに置いてください）:")
        errors += pair_errors

    if errors:
        print("generated/ の確認でエラーがあります。\n", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
