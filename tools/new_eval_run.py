#!/usr/bin/env python3
"""発散 run の spec.json を、短い入力 JSON から作る。標準ライブラリのみ。

    uv run tools/new_eval_run.py generator/temp/briefs/<slug>.json

入力 JSON:
  {
    "slug": "kickback",                      # run 名に入る
    "brief_type": "music" | "mood",
    "brief": "米津玄師『KICK BACK』…",
    "context_sources": [{"kind": "...", "source": "...", "visual_elements": "..."}],
    "concept": "核となる英語の視覚コンセプト文",
    "note": "任意",
    "seed_base": 4000,                       # 内部的な再現用。発散の単位にはしない
    "items": [{"label": "...", "direction": "日本語の主方向", "idea_id": "idea-01", "variant": 1, "text": "プロンプト全文"}, ...]
  }

runs/<日時>-eval-prompts-<slug>/spec.json を作り、パスを表示する。モデルとサンプラーは XL Turbo-Lightning の既定。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLER = {"steps": 6, "cfg": 2.0, "sampler_name": "dpmpp_sde", "scheduler": "karras", "denoise": 1.0}
CHECKPOINT = "DreamShaperXL_Turbo-Lightning.safetensors"


def _repair_json(text: str) -> tuple[str, list[str]]:
    """AI が手で書いた JSON によくある崩れを直す。直した内容の一覧も返す。

    直すもの: コードフェンス / // と /* */ のコメント / 末尾のカンマ / 要素の間のカンマ抜け（} {、] [）/ 閉じ忘れ（末尾）。
    文字列の中は触らない。
    """
    notes: list[str] = []
    s = text.lstrip("\ufeff").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else ""
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
        notes.append("コードフェンスを除いた")

    out: list[str] = []
    stack: list[str] = []
    i, n = 0, len(s)
    counts = {"comment": 0, "trailing": 0, "missing": 0, "closed": 0}
    in_str = False

    def prev_index() -> int:
        k = len(out) - 1
        while k >= 0 and out[k].isspace():
            k -= 1
        return k

    while i < n:
        ch = s[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(s[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
        elif s.startswith("//", i):
            j = s.find("\n", i)
            i = n if j < 0 else j
            counts["comment"] += 1
            continue
        elif s.startswith("/*", i):
            j = s.find("*/", i + 2)
            i = n if j < 0 else j + 2
            counts["comment"] += 1
            continue
        elif ch in "{[":
            k = prev_index()
            if k >= 0 and out[k] in "}]" and stack:  # 直前が } か ] なら、カンマが抜けている
                out.insert(k + 1, ",")
                counts["missing"] += 1
            stack.append("}" if ch == "{" else "]")
            out.append(ch)
        elif ch in "}]":
            k = prev_index()
            if k >= 0 and out[k] == ",":  # 末尾のカンマ
                del out[k]
                counts["trailing"] += 1
            if stack and stack[-1] == ch:
                stack.pop()
            out.append(ch)
        else:
            out.append(ch)
        i += 1

    if in_str:
        out.append('"')
        notes.append("閉じていない文字列を閉じた")
    if stack:
        k = prev_index()
        if k >= 0 and out[k] == ",":
            del out[k]
        out.append("".join(reversed(stack)))
        counts["closed"] = len(stack)
    if counts["comment"]:
        notes.append(f"コメントを除いた（{counts['comment']} 件）")
    if counts["trailing"]:
        notes.append(f"末尾のカンマを除いた（{counts['trailing']} 件）")
    if counts["missing"]:
        notes.append(f"要素の間のカンマを補った（{counts['missing']} 件）")
    if counts["closed"]:
        notes.append(f"閉じ忘れの括弧を補った（{counts['closed']} 個）")
    return "".join(out), notes


def load_json_lenient(path, what: str = "入力 JSON"):
    """JSON を読む。AI が書いた崩れは直して読み、直した内容を stderr に出す。直せないときは、場所と周辺を示して ValueError。"""
    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fixed, notes = _repair_json(text)
    try:
        data = json.loads(fixed)
    except json.JSONDecodeError as e:
        lines = fixed.splitlines()
        lo, hi = max(0, e.lineno - 3), min(len(lines), e.lineno + 2)
        ctx = "\n".join(f"{'>' if k + 1 == e.lineno else ' '} {k + 1:4d}| {lines[k]}" for k in range(lo, hi))
        raise ValueError(
            f"{what} を読めません（{Path(path).name}、{e.lineno} 行 {e.colno} 列: {e.msg}）。\n{ctx}\n"
            '文字列の中の " は \\" にする、キーと値の間の : と要素の間の , を確かめてください。'
        ) from e
    print(f"{what} を補正して読みました: {'、'.join(notes) or '空白などを整えた'}（{Path(path).name}）", file=sys.stderr)
    return data


def validate_brief(brief) -> dict:
    """brief の必須項目を検査して、足りない既定値を補う。不正なら ValueError。"""
    if not isinstance(brief, dict):
        raise ValueError("brief は、JSON のオブジェクト（{ ... }）にしてください")
    missing = [k for k in ("slug", "brief", "concept", "items") if not brief.get(k)]
    if missing:
        raise ValueError(f"brief に次の項目がありません: {', '.join(missing)}")
    brief.setdefault("brief_type", "mood")
    if not isinstance(brief["items"], list):
        raise ValueError("items は、項目の配列にしてください")
    for n, it in enumerate(brief["items"], 1):
        if not isinstance(it, dict) or not it.get("text"):
            raise ValueError(f"items の {n} 番目に text（プロンプト）がありません")
        it.setdefault("label", it.get("direction") or f"idea-{n}")
    return brief


def build_spec(brief: dict) -> dict:
    """入力ブリーフから spec.json の中身を作る。"""
    base = brief.get("seed_base", 4000)
    items = []
    for i, it in enumerate(brief["items"], 1):
        item = {
            "id": f"{i:02d}",
            "label": it["label"],
            "direction": it.get("direction", ""),
            "text": it["text"],
            "seed": base + i,
            # idea_id が同じ項目は、同じアイデアの別プロンプト。
            # 未指定の項目は、それ自体を 1 アイデアとして扱う。
            "idea_id": it.get("idea_id", f"idea-{i:02d}"),
            "variant": int(it.get("variant", 1)),
        }
        if it.get("reason"):
            item["reason"] = it["reason"]  # このアイデアを採用した理由（日本語）。カードの「説明」に出る
        items.append(item)
    return {
        "brief_type": brief["brief_type"],
        "brief": brief["brief"],
        "context_sources": brief.get("context_sources", []),
        "concept": brief["concept"],
        "note": brief.get("note", ""),
        "workflow": "txt2img-api.json",
        "checkpoint": CHECKPOINT,
        "width": 1152,
        "height": 768,
        "sampler": SAMPLER,
        "conditions": [
            {
                "name": "p",
                "checkpoint": CHECKPOINT,
                "width": 1152,
                "height": 768,
                "sampler": SAMPLER,
                "prompt_prefix": "",
                "prompt_suffix": "",
                "negative_prompt": "",
                "items": items,
            }
        ],
    }


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    try:
        brief = validate_brief(load_json_lenient(sys.argv[1], "brief"))
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    spec = build_spec(brief)
    run_dir = REPO_ROOT / "runs" / f"{datetime.now():%Y%m%d-%H%M%S}-eval-prompts-{brief['slug']}"
    run_dir.mkdir(parents=True)
    (run_dir / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
