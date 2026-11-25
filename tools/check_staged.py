#!/usr/bin/env python3
"""ステージされたファイルのうち、意図せず入りがちなものを止める。pre-commit から呼ぶ。

止めるもの（新規追加・変更のみ。削除は見ない）:
  1. 置き場の決まっていない画像（.png .jpg .jpeg .webp .gif）。画像を置いてよいのは次の場所だけ
       generated/   ラベル付けした生成画像（PNG）
       artifacts/   公開用の画像（WebP）
       site/        サイトの素材
       runs/<run>/contact.webp   run ごとの一覧画像
       tests/results/   動作確認のスクリーンショット（合成画像の session だけ。実際の生成物は入れない）
       （例外）見本の 2 件の runs/<run>/images/
     run の画像本体（runs/*/images/*.png）は再生成できるので管理しない（runs/README.md）。
  2. 1 MB を超えるファイル（ロックファイルなど、テキストの例外は LARGE_OK に書く）。

意図して入れるときだけ、環境変数で省略できる。

    ALLOW_STAGED=1 git commit

標準ライブラリだけで動く。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
IMAGE_OK = (
    re.compile(r"^generated/"),
    re.compile(r"^artifacts/"),
    re.compile(r"^site/"),
    re.compile(r"^runs/[^/]+/contact\.webp$"),
    re.compile(r"^tests/results/[^/]+\.png$"),
    # チュートリアル用の例外（画像も追跡している見本の 2 件。runs/README.md）
    re.compile(r"^runs/(20261124-204000-gap-09-scifi|20261124-234236-eval-prompts-idol-structured)/images/"),
)
LARGE_BYTES = 1024 * 1024
LARGE_OK: set[str] = set()


def staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=AM", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    return [p for p in out.split("\0") if p]


def main() -> int:
    if os.environ.get("ALLOW_STAGED") == "1":
        return 0
    errors: list[str] = []
    for path in staged_files():
        p = Path(path)
        if p.suffix.lower() in IMAGE_EXTS and not any(r.match(path) for r in IMAGE_OK):
            errors.append(f"    {path}: 画像の置き場所ではありません（画像を置けるのは generated/ artifacts/ site/ runs/*/contact.webp tests/results/*.png）")
        size = (REPO_ROOT / path).stat().st_size if (REPO_ROOT / path).is_file() else 0
        if size > LARGE_BYTES and path not in LARGE_OK:
            errors.append(f"    {path}: {size / 1024 / 1024:.1f} MB あります（上限 1 MB）")
    if errors:
        print("ステージされたファイルに、止めたいものがあります。\n", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        print("\n意図して入れるときは ALLOW_STAGED=1 git commit", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
