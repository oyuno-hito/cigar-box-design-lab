#!/usr/bin/env python3
"""run の画像を、公開用に WebP へ変換して artifacts/<テーマ>/ に置く。

    .venv/bin/python tools/export_artifacts.py runs/<run> --id koi --title '星野源『恋』' --kind song
    .venv/bin/python tools/export_artifacts.py runs/<run> --id koi --pick 01,03,07   # 選定しなおす

- 既定は run の全画像。`--pick` で画像の番号（`p-01` の `01`）を選ぶ。選びなおすと、外れた画像のファイルを消す。
- 画像は `<番号>.webp`（長辺 768）と `<番号>.thumb.webp`（長辺 384、一覧用）。
- `artifacts/manifest.json` にテーマ名と、画像の並び・題名を書く。サイトはこれだけを読む。題名は spec.json の
  `direction`（そのプロンプトの狙い。「基準: 」は外す）。プロンプト本文は書かない。`--title` と `--kind` は、
  すでにあるテーマでは省略できる（既存の値を保つ）。
- 出どころ（run と元の画像 ID）は `artifacts/<テーマ>/provenance.json` に書く。`tools/build_site.py` は
  .webp と manifest.json 以外をコピーしないので、公開されない。プロンプトは書かない。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = REPO_ROOT / "artifacts"
MANIFEST = ARTIFACTS / "manifest.json"
FULL_SIZE = (768, 512)
THUMB_SIZE = (384, 256)
KINDS = {"song": "曲", "mood": "ムード"}


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"themes": []}


def save_webp(src: Path, dst: Path, size: tuple[int, int], quality: int) -> None:
    im = Image.open(src).convert("RGB")
    if im.size != size:
        im = im.resize(size, Image.LANCZOS)
    im.save(dst, "WEBP", quality=quality, method=6)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path, help="runs/<run>（images/ に p-NN.png がある）")
    ap.add_argument("--id", required=True, help="テーマの ID（ディレクトリ名。英数字とハイフン）")
    ap.add_argument("--title", help="表示するテーマ名（新規テーマでは必須）")
    ap.add_argument("--kind", choices=sorted(KINDS), help="song = 曲を題材にしたもの / mood = ムード")
    ap.add_argument("--pick", help="使う画像の番号をカンマ区切りで（既定は全画像）。例: 01,03,07")
    args = ap.parse_args()

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.id):
        print("--id は英小文字・数字・ハイフンだけにしてください", file=sys.stderr)
        return 2
    run = args.run if args.run.is_absolute() else (Path.cwd() / args.run)
    images = sorted((run / "images").glob("p-*.png"))
    if not images:
        print(f"{run}/images/p-*.png がありません", file=sys.stderr)
        return 2
    by_no = {p.stem.removeprefix("p-"): p for p in images}
    pick = [x.strip() for x in args.pick.split(",")] if args.pick else list(by_no)
    missing = [x for x in pick if x not in by_no]
    if missing:
        print(f"run にない番号: {', '.join(missing)}", file=sys.stderr)
        return 2

    spec = json.loads((run / "spec.json").read_text(encoding="utf-8"))
    titles = {}
    for cond in spec.get("conditions", []):
        for it in cond.get("items", []):
            titles[it["id"]] = re.sub(r"^基準[:：]\s*", "", it.get("direction") or it.get("label") or "")

    manifest = load_manifest()
    theme = next((t for t in manifest["themes"] if t["id"] == args.id), None)
    if theme is None:
        if not args.title or not args.kind:
            print("新しいテーマには --title と --kind が要ります", file=sys.stderr)
            return 2
        theme = {"id": args.id, "kind": args.kind, "title": args.title, "images": []}
        manifest["themes"].append(theme)
    else:
        theme["title"] = args.title or theme["title"]
        theme["kind"] = args.kind or theme["kind"]

    out = ARTIFACTS / args.id
    out.mkdir(parents=True, exist_ok=True)
    for no in pick:
        save_webp(by_no[no], out / f"{no}.webp", FULL_SIZE, 82)
        save_webp(by_no[no], out / f"{no}.thumb.webp", THUMB_SIZE, 76)
    old_ids = {i["id"] if isinstance(i, dict) else i for i in theme["images"]}
    for old in old_ids - set(pick):
        for name in (f"{old}.webp", f"{old}.thumb.webp"):
            (out / name).unlink(missing_ok=True)
    theme["images"] = [{"id": no, "title": titles.get(no, "")} for no in pick]

    (out / "provenance.json").write_text(
        json.dumps({"run": run.name, "images": {no: by_no[no].stem for no in pick}}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    size = sum(f.stat().st_size for f in out.glob("*.webp")) / 1024
    print(f"{args.id}: {len(pick)} 枚 / {size:.0f} KB -> {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
