#!/usr/bin/env python3
"""site/ と artifacts/ から、公開用ディレクトリ _site/ を作る。標準ライブラリのみ。

    python3 tools/build_site.py             # _site/ を作り直す
    python3 tools/build_site.py --serve     # 作ったあと http://127.0.0.1:8000/ で確認する（--port で変更）

公開するのは次だけ。それ以外（provenance.json など）は、artifacts/ にあってもコピーしない。
  - site/ の中身（index.html、style.css、app.js）
  - artifacts/manifest.json
  - artifacts/<テーマ>/*.webp
"""

from __future__ import annotations

import argparse
import functools
import json
import shutil
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE = REPO_ROOT / "site"
ARTIFACTS = REPO_ROOT / "artifacts"
OUT = REPO_ROOT / "_site"


def build() -> int:
    manifest_path = ARTIFACTS / "manifest.json"
    if not manifest_path.exists():
        print("artifacts/manifest.json がありません（tools/export_artifacts.py で作る）", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for f in SITE.iterdir():
        if f.is_file() and f.name != "README.md":
            shutil.copy2(f, OUT / f.name)

    (OUT / "artifacts").mkdir()
    shutil.copy2(manifest_path, OUT / "artifacts" / "manifest.json")
    n = 0
    for theme in manifest["themes"]:
        src = ARTIFACTS / theme["id"]
        dst = OUT / "artifacts" / theme["id"]
        dst.mkdir()
        for image in theme["images"]:
            no = image["id"]
            for name in (f"{no}.webp", f"{no}.thumb.webp"):
                if not (src / name).exists():
                    print(f"画像がありません: {src / name}", file=sys.stderr)
                    return 1
                shutil.copy2(src / name, dst / name)
                n += 1
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1024 / 1024
    print(f"_site/ を作りました: テーマ {len(manifest['themes'])} 件、画像ファイル {n} 個、{size:.1f} MB")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    code = build()
    if code or not args.serve:
        return code
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(OUT))
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"http://127.0.0.1:{args.port}/ （Ctrl-C で終了）")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
