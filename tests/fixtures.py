"""テスト用の session（合成画像・偽の AI・偽の生成）。実際の ComfyUI・分類器・外部の AI は使わない。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import session as S  # noqa: E402
from new_eval_run import build_spec  # noqa: E402

BASE_TEXT = (
    "flat graphic decoration, full frame composition, off-white ground, scattered flat circles, cobalt and coral, "
    "short thin segments, even spacing, crisp print-like edges, matte paper texture, no text, no people"
)


def brief(n_ideas: int = 6) -> dict:
    items = []
    for i in range(1, n_ideas + 1):
        items.append(
            {
                "label": f"idea {i}",
                "direction": f"方針 {i}",
                "reason": f"アイデア {i} の理由（テスト用）" if i % 2 else "",
                "idea_id": f"idea-{i:02d}",
                "text": BASE_TEXT.replace("cobalt and coral", f"color{i} and coral"),
            }
        )
    return {"slug": "fixture", "brief_type": "mood", "brief": "テスト用の題材", "concept": "テスト用のコンセプト", "items": items}


def solid(path: Path, rgb: tuple[int, int, int], size=(1152, 768)) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, rgb).save(path)


def build_session(root: Path, *, cards=(1, 2, 3, 4), size=4, n_ideas=6, name="20261125-000000-fixture") -> Path:
    """cards に入れた番号の項目がカードになっている session を作る。残りの項目は予備。"""
    sdir = root / name
    (sdir / "images").mkdir(parents=True)
    spec = build_spec(brief(n_ideas))
    S.write_json(sdir / "spec.json", spec)
    ids = [S.card_id(f"{n:02d}") for n in cards]
    for k, cid in enumerate(ids):
        solid(sdir / "images" / f"{cid}.png", (40 + k * 50, 90, 160))
        (sdir / "images" / f"{cid}.json").write_text(json.dumps({"prompt": "x", "seed": 1}), encoding="utf-8")
    S.make_thumbs(sdir, ids)
    state = {
        "size": size,
        "round": 1,
        "phase": "ready",
        "error": "",
        "progress": {},
        "cards": ids,
        "live": [],
        "origin": {c: {"kind": "new"} for c in ids},
        "shortfall": max(0, size - len(ids)),
        "next_no": n_ideas + 4,
        "dropped_items": [],
        "history": [],
    }
    S.save_state(sdir, state)
    return sdir


def fake_generate_one(run_dir: Path, item_id: str, host: str = "") -> Path:
    """画像を作らず、番号に応じた単色の PNG と .json を書く偽の生成。"""
    run_dir = Path(run_dir)
    spec = S.load_spec(run_dir)
    it = next(i for i in S.spec_items(spec) if i["id"] == item_id)
    png = run_dir / "images" / f"p-{item_id}.png"
    solid(png, (30 + int(item_id) * 9 % 200, 120, 90 + int(item_id) * 13 % 140))
    png.with_suffix(".json").write_text(json.dumps({"prompt": it["text"], "seed": it["seed"]}), encoding="utf-8")
    return png


FAKE_AI = '''\
import json, os, re, sys

text = sys.stdin.read()
payload = json.loads(re.search(r"```json\\n(.*?)\\n```", text, re.S).group(1))
retry = "前回の返答は" in text or not os.environ.get("FAKE_AI_BAD_FIRST")  # BAD_FIRST のときは、最初の返答を不正（重みなし）にする
rows = []
for r in payload["requests"]:
    phrases = [p.strip() for p in r["base_prompt"].split(",")] if r["base_prompt"] else []
    head, tail = phrases[:2], phrases[2:7]
    variant = r["key"][-1]
    if r["kind"] == "derive":
        new = head + ([f"({r['card_note']} v{variant}:1.3)"] if retry else [f"{r['card_note']} v{variant}"]) + tail + [f"variant{variant} shape", f"variant{variant} layout"] + ["no text"]
    elif r["kind"] == "fill":
        new = phrases[:6] + [f"note {payload['global_note']}"] + ["no text"]
    else:
        new = ["flat graphic decoration", f"brand new idea {r['key']}", "no text"]
    rows.append({"key": r["key"], "title": f"AI の方針 {r['key']}", "reason": f"理由 {r['key']}", "text": ", ".join(new)})
print("説明の文章 " + json.dumps(rows, ensure_ascii=False))
'''
