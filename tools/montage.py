#!/usr/bin/env python3
"""run の画像をコンタクトシート（1 枚の画像）にまとめる。エージェントや人間が、数十枚をまとめて眺める用。

    uv run tools/montage.py runs/<run-id> [--condition NAME] [--cols 4] [--width 1600] [--sort score|id] [--out PATH]
    uv run tools/montage.py runs/<run-id> --contact   # runs/<run-id>/contact.webp を作る（Git 管理する一覧画像）

  - 条件ごとに 1 枚ずつ作る（--condition で絞る）。各マスに id の末尾番号とスコアを入れる
  - 出力先の既定は generator/temp/montage/（Git 管理外）
  - review.json があれば、印の付いた画像に黄色い枠、確認済みの条件では機械の判定（通過=緑 / 不通過=赤）の枠を付ける
  - --contact は、全条件を 1 枚に縦に積んだ WebP を run のディレクトリに書く（id 順）。画像本体（PNG）は
    Git 管理しないので、この 1 枚が「その run で何が出たか」の目視ログになる。他のオプション（--out など）とは併用しない
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
GAP = 8
CONTACT_WIDTH = 1200
CONTACT_QUALITY = 78
HEADER_H = 26


def render(run: Path, items: list[dict], flags: set[str], cols: int, width: int) -> Image.Image:
    """1 つの条件のコンタクトシートを描く。items は並べる順に渡す。"""
    cell_w = (width - GAP * (cols + 1)) // cols
    cell_h = cell_w * 2 // 3
    rows = -(-len(items) // cols)
    sheet = Image.new("RGB", (width, GAP + rows * (cell_h + GAP)), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    for i, it in enumerate(items):
        x, y = GAP + (i % cols) * (cell_w + GAP), GAP + (i // cols) * (cell_h + GAP)
        im = Image.open(run / "images" / f"{it['id']}.png").convert("RGB").resize((cell_w, cell_h), Image.LANCZOS)
        sheet.paste(im, (x, y))
        color = (63, 185, 80) if it["pass"] else (248, 81, 73)
        if it["id"] in flags:
            color = (240, 183, 47)
        d.rectangle([x, y, x + cell_w - 1, y + cell_h - 1], outline=color, width=4)
        d.rectangle([x, y, x + 120, y + 22], fill=(0, 0, 0))
        d.text((x + 4, y + 4), f"#{it['id'].rsplit('-', 1)[1]}  p={it['p']:.2f}", fill=(255, 255, 255))
    return sheet


def contact_sheet(run: Path, scores: dict, flags: set[str]) -> Path:
    """全条件を 1 枚に縦に積んだ WebP を run のディレクトリに書く。条件が複数のときは条件名の見出しを付ける。"""
    conds = sorted({it["condition"] for it in scores["items"]})
    sheets = []
    for c in conds:
        items = sorted((it for it in scores["items"] if it["condition"] == c), key=lambda it: it["id"])
        sheets.append((c, render(run, items, flags, cols=4, width=CONTACT_WIDTH)))
    header = HEADER_H if len(sheets) > 1 else 0
    out_img = Image.new("RGB", (CONTACT_WIDTH, sum(s.height + header for _, s in sheets)), (24, 24, 24))
    d = ImageDraw.Draw(out_img)
    y = 0
    for c, s in sheets:
        if header:
            d.text((GAP, y + 6), c, fill=(255, 255, 255))
        out_img.paste(s, (0, y + header))
        y += s.height + header
    out = run / "contact.webp"
    out_img.save(out, "WEBP", quality=CONTACT_QUALITY, method=6)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--condition", default=None)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--width", type=int, default=1600, help="シート全体の幅")
    ap.add_argument("--sort", choices=["score", "id"], default="score")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--contact", action="store_true", help="run のディレクトリに contact.webp を作る（Git 管理する一覧画像）")
    args = ap.parse_args()

    run = args.run_dir.resolve()
    scores = json.loads((run / "scores.json").read_text(encoding="utf-8"))
    review = json.loads((run / "review.json").read_text(encoding="utf-8")) if (run / "review.json").exists() else {}
    flags = set(review.get("flags", []))

    if args.contact:
        out = contact_sheet(run, scores, flags)
        print(f"{out} ({out.stat().st_size / 1024:.0f} KB)")
        return 0

    out_dir = args.out.parent if args.out else REPO_ROOT / "generator" / "temp" / "montage"
    out_dir.mkdir(parents=True, exist_ok=True)

    conds = sorted({it["condition"] for it in scores["items"]})
    if args.condition:
        conds = [c for c in conds if c == args.condition]
    for c in conds:
        items = [it for it in scores["items"] if it["condition"] == c]
        items.sort(key=(lambda it: -it["p"]) if args.sort == "score" else (lambda it: it["id"]))
        sheet = render(run, items, flags, args.cols, args.width)
        out = args.out if args.out and len(conds) == 1 else out_dir / f"{run.name}__{c}.jpg"
        sheet.save(out, quality=88)
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
