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
    "seed_base": 4000,                       # 画像ごとに seed_base + 連番（発散のため、画像ごとに seed を変える）
    "items": [{"label": "...", "direction": "日本語の主方向", "text": "プロンプト全文"}, ...]
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


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    brief = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    base = brief.get("seed_base", 4000)
    items = [
        {"id": f"{i:02d}", "label": it["label"], "direction": it.get("direction", ""), "text": it["text"], "seed": base + i}
        for i, it in enumerate(brief["items"], 1)
    ]
    spec = {
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
    run_dir = REPO_ROOT / "runs" / f"{datetime.now():%Y%m%d-%H%M%S}-eval-prompts-{brief['slug']}"
    run_dir.mkdir(parents=True)
    (run_dir / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
