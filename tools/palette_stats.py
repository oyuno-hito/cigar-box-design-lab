#!/usr/bin/env python3
"""session の画像の色味を数える。色の偏り（どの session も同じ 2〜3 色になる）を見つけるための補助。

    uv run tools/palette_stats.py sessions/<id> [sessions/<id> ...]

画像ごとに、有彩色（彩度・明度が一定以上）の画素を色相の系統に分け、占める割合が大きい系統（上位 2 つまで）を出す。
地の色（明るい / 暗い / 有彩色）も出す。最後に、全画像で系統ごとに「その系統が主な色になっている画像の割合」を出す。
機械の目安であり、好みの判定ではない。
"""

from __future__ import annotations

import colorsys
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

# 色相（度）の範囲 → 系統名
FAMILIES = [
    (345, 360, "赤"), (0, 15, "赤"), (15, 45, "橙"), (45, 70, "黄"), (70, 160, "緑"),
    (160, 200, "青緑"), (200, 260, "青"), (260, 300, "紫"), (300, 345, "赤紫"),
]
MAIN_SHARE = 0.15  # 有彩色の画素のうち、この割合以上を占める系統を「主な色」にする


def family(hue_deg: float) -> str:
    for lo, hi, name in FAMILIES:
        if lo <= hue_deg < hi:
            return name
    return "赤"


def analyze(path: Path) -> dict:
    img = Image.open(path).convert("RGB").resize((96, 64))
    chroma: Counter[str] = Counter()
    light = dark = 0
    raw = img.tobytes()
    px = [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)]
    for r, g, b in px:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s >= 0.30 and v >= 0.25:
            chroma[family(h * 360)] += 1
        elif v < 0.25:
            dark += 1
        elif s < 0.20 and v >= 0.75:
            light += 1
    total_chroma = sum(chroma.values()) or 1
    mains = [(name, n / total_chroma) for name, n in chroma.most_common(3) if n / total_chroma >= MAIN_SHARE]
    return {
        "mains": mains,
        "chroma_ratio": sum(chroma.values()) / len(px),
        "dark_ratio": dark / len(px),
        "light_ratio": light / len(px),
    }


def ground(a: dict) -> str:
    if a["chroma_ratio"] >= 0.6:
        return "有彩色の地"
    return "暗い地" if a["dark_ratio"] >= a["light_ratio"] else "明るい地"


def main(argv: list[str]) -> int:
    dirs = [Path(a) for a in argv]
    if not dirs:
        print(__doc__)
        return 1
    main_counts: Counter[str] = Counter()
    pair_counts: Counter[str] = Counter()
    ground_counts: Counter[str] = Counter()
    n_images = 0
    for d in dirs:
        print(f"## {d.name}")
        for p in sorted((d / "images").glob("p-*.png")):
            a = analyze(p)
            names = [name for name, _ in a["mains"]]
            for name in names:
                main_counts[name] += 1
            pair_counts["+".join(sorted(names[:2]))] += 1
            ground_counts[ground(a)] += 1
            n_images += 1
            shown = " ".join(f"{name}{share:.0%}" for name, share in a["mains"]) or "（無彩色）"
            print(f"  {p.stem}: {ground(a)} / {shown}")
    if not n_images:
        return 1
    print(f"\n## 全体（{n_images} 枚）")
    print("主な色の系統（その系統が主な色になっている画像の割合）:")
    for name, n in main_counts.most_common():
        print(f"  {name}: {n / n_images:.0%}")
    top_pair, top_n = pair_counts.most_common(1)[0]
    print(f"最も多い色の組み合わせ: {top_pair}（{top_n / n_images:.0%}）")
    print("地: " + " / ".join(f"{k} {v / n_images:.0%}" for k, v in ground_counts.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
