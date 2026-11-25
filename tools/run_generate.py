#!/usr/bin/env python3
"""実験 run の spec.json を読み、起動中の ComfyUI（API）で画像を生成する。標準ライブラリのみ。

    uv run tools/run_generate.py runs/<run-id>            # 未生成の画像だけ作る（途中から再開できる）
    uv run tools/run_generate.py runs/<run-id> --force    # すべて作り直す
    uv run tools/run_generate.py runs/<run-id> --limit 3  # 条件ごとに先頭 N 件だけ（動作確認用）

前提:
  - ComfyUI が起動していること（既定は http://127.0.0.1:8188。--host で変更）
  - ワークフローは generator/workflows/ のテンプレート（spec.json の workflow）を使い、プロンプト・seed・サイズなどを差し替える
  - checkpoint / width / height / sampler は run 全体の既定で、条件（conditions[]）ごとに上書きできる

出力:
  runs/<run-id>/images/<条件名>-<番号>.png と、同名の .json（source / prompt / negative_prompt / seed）
  画像は ComfyUI の PreviewImage（temp）から取得するため、ComfyUI の output/ は汚れない。
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / "generator" / "workflows"
TIMEOUT_PER_IMAGE = 900  # 秒


def http_json(url: str, data: dict | None = None) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8") if data is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def join_prompt(*parts: str) -> str:
    return ", ".join(p.strip().strip(",") for p in parts if p and p.strip())


def effective(spec: dict, cond: dict) -> dict:
    """run 全体の設定を、条件ごとの指定（checkpoint / width / height / sampler）で上書きしたもの。"""
    return {k: cond.get(k, spec[k]) for k in ("checkpoint", "width", "height", "sampler")}


def build_workflow(template: dict, eff: dict, prompt: str, negative: str, seed: int) -> dict:
    wf = copy.deepcopy(template)
    wf["1"]["inputs"]["ckpt_name"] = eff["checkpoint"]
    wf["2"]["inputs"]["text"] = prompt
    wf["3"]["inputs"]["text"] = negative
    wf["4"]["inputs"]["width"] = eff["width"]
    wf["4"]["inputs"]["height"] = eff["height"]
    wf["5"]["inputs"].update(eff["sampler"])
    wf["5"]["inputs"]["seed"] = seed
    return wf


def run_one(host: str, wf: dict) -> bytes:
    """ワークフローを投入し、完了を待って 1 枚目の画像を返す。"""
    client_id = str(uuid.uuid4())
    res = http_json(f"{host}/prompt", {"prompt": wf, "client_id": client_id})
    pid = res["prompt_id"]
    deadline = time.time() + TIMEOUT_PER_IMAGE
    while time.time() < deadline:
        hist = http_json(f"{host}/history/{pid}")
        if pid in hist:
            entry = hist[pid]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                msgs = [m for m in status.get("messages", []) if m and m[0] == "execution_error"]
                raise RuntimeError(f"ComfyUI でエラー: {msgs[-1][1] if msgs else status}")
            for node in entry.get("outputs", {}).values():
                for img in node.get("images", []):
                    q = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": img["type"]})
                    with urllib.request.urlopen(f"{host}/view?{q}", timeout=60) as r:
                        return r.read()
            raise RuntimeError("画像の出力がありません")
        time.sleep(1.0)
    raise TimeoutError(f"{TIMEOUT_PER_IMAGE} 秒以内に終わりませんでした")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--host", default="http://127.0.0.1:8188")
    ap.add_argument("--force", action="store_true", help="既にある画像も作り直す")
    ap.add_argument("--limit", type=int, default=0, help="条件ごとに先頭 N 件だけ生成する")
    args = ap.parse_args()

    run_dir = args.run_dir.resolve()
    spec = json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))
    template = json.loads((WORKFLOWS / spec["workflow"]).read_text(encoding="utf-8"))
    out = run_dir / "images"
    out.mkdir(exist_ok=True)

    try:
        stats = http_json(f"{args.host}/system_stats")
    except (urllib.error.URLError, OSError) as e:
        print(f"ComfyUI に接続できません（{args.host}）: {e}", file=sys.stderr)
        return 1
    version = stats.get("system", {}).get("comfyui_version", "unknown")

    jobs = []
    for cond in spec["conditions"]:
        eff = effective(spec, cond)
        sm = eff["sampler"]
        source = f"comfyui {version} / {eff['checkpoint']} / {sm['sampler_name']} {sm['steps']}steps cfg{sm['cfg']} / {eff['width']}x{eff['height']}"
        items = cond["items"][: args.limit] if args.limit else cond["items"]
        for it in items:
            prompt = join_prompt(cond.get("prompt_prefix", ""), it["text"], cond.get("prompt_suffix", ""))
            jobs.append((f"{cond['name']}-{it['id']}", prompt, cond.get("negative_prompt", ""), int(it["seed"]), eff, source))

    t0 = time.time()
    done = 0
    for i, (name, prompt, negative, seed, eff, source) in enumerate(jobs, 1):
        png = out / f"{name}.png"
        if png.exists() and not args.force:
            print(f"[{i}/{len(jobs)}] {name}: 既にあるのでスキップ")
            continue
        t = time.time()
        data = run_one(args.host, build_workflow(template, eff, prompt, negative, seed))
        png.write_bytes(data)
        meta = {"source": source, "prompt": prompt, "negative_prompt": negative, "seed": seed}
        png.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        done += 1
        print(f"[{i}/{len(jobs)}] {name}: {time.time() - t:.1f} 秒")
    print(f"完了: {done} 枚を生成（合計 {time.time() - t0:.0f} 秒）→ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
