#!/usr/bin/env python3
"""実使用の session（sessions/<日時>-<名前>/）を作り、候補の生成と、選択に沿った再生成まで進める。

実験の run（runs/）と違い、採点やレポートは作らない。分類器は、画像の生成直後に足切りするためだけに内部で使い、
スコアは画面にも出力にも出さない（state.json の内部値）。出力先は基本 Git 管理外（sessions/README.md）。

    uv run tools/session.py new brief.json [--size 8]        # sessions/<日時>-<slug>/ を作る（brief は tools/new_eval_run.py と同じ形式）
    uv run tools/session.py generate sessions/<id>           # 最初の候補を生成する（バックグラウンドで実行する）
    uv run tools/session.py selection sessions/<id>          # ページで選ばれた内容を読む（選んだカード / 個別の方向 / 全体の方針 / 押したボタン）
    uv run tools/session.py plan sessions/<id> [--mode add]  # 選択から、作る候補の計画と、AI への依頼文（instruction）を出す
    uv run tools/session.py regen sessions/<id> --auto [--prompts out.json]   # 計画どおりに再生成する（バックグラウンドで実行する）
    uv run tools/session.py regen sessions/<id> --items new.json              # AI が書いた項目で再生成する（--auto の代わり）
    uv run tools/session.py add sessions/<id> --auto         # 足りない分を、全カードを残したまま補う（バックグラウンドで実行する）
    uv run tools/session.py status sessions/<id>             # 段階（生成中 / 準備完了 / エラー）、進捗、足りない件数

カードのページは tools/serve_session.py で配信する。

件数のルール（size。既定 8 件）:
  - 1 prompt につき画像を 1 枚生成する。同じ idea_id に複数の prompt があれば、最初に足切りを通った 1 枚でそのアイデアを終了する。
  - 足切りを通らなかった画像は、カードになる前に削除する。採用済みカードは後から削除しない。
  - 予備が尽きても size 件に届かなければ、status の shortfall に足りない件数が出る。`add --auto` が AI に新しいアイデアを依頼する。

再生成の計画（--auto）:
  - 残すカード = ページで選んだカードだけ。選んでいないカードは、個別の方向が入っていても削除する。
  - 選んだカードに個別の方向があれば、元の画像を残したまま、異なる prompt の派生を 3 件作る。派生は、スコアの足切りをせず表示する。
    派生は、元の画像と**はっきり違う**ことを求める（方向の語句に重みを付け、語句の残りは 3〜8 割、派生どうしも似すぎないよう検査する）。
  - 空き枠は、まだ試していない予備のアイデアから埋める。全体の方針は、予備が作る新しい候補に反映する。
  - 個別の派生には全体の方針を反映しない。予備が尽きても、regen では AI に新しいアイデアを頼まない（足りない件数だけ出す）。人が「足りない分を補う」（add）を押したときに、AI に新しいアイデアを書いてもらう。
    AI の呼び方は、環境変数 CIGAR_COMPOSER_CMD（依頼文を標準入力、返答を標準出力）が設定されているときだけ、サーバーが呼ぶ。未設定なら、ページの依頼文を任意の AI に貼り、返ってきた JSON をページに貼る。

items.json（`--items`。AI が項目を直接書くとき）は項目の配列。複数 prompt を同じアイデアにする場合は、同じ `idea_id` と異なる `variant` を付ける。派生には `parent` と `protect: true` を付ける:
    [{"label": "...", "direction": "日本語の方針", "idea_id": "idea-01", "variant": 1, "text": "プロンプト全文（英語）"}, ...]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shlex
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parent.parent
SESSIONS = Path(os.environ.get("CIGAR_SESSIONS_DIR") or REPO_ROOT / "sessions")  # CIGAR_SESSIONS_DIR は、テスト用の出力先
COND = "p"
CARD_WIDTH = 960
DEFAULT_SIZE = 8


# ---- 状態の読み書き ---------------------------------------------------------------------


def write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_state(sdir: Path) -> dict:
    return json.loads((sdir / "state.json").read_text(encoding="utf-8"))


def save_state(sdir: Path, state: dict) -> None:
    write_json(sdir / "state.json", state)


def load_spec(sdir: Path) -> dict:
    return json.loads((sdir / "spec.json").read_text(encoding="utf-8"))


def spec_items(spec: dict) -> list[dict]:
    return spec["conditions"][0]["items"]


def card_id(item_id: str) -> str:
    return f"{COND}-{item_id}"


def item_id(cid: str) -> str:
    return cid.split("-", 1)[1]


def resolve(path: Path) -> Path:
    sdir = path.resolve()
    if not (sdir / "state.json").exists():
        sys.exit(f"session ではありません（state.json がありません）: {path}")
    return sdir


def read_selection(sdir: Path) -> dict | None:
    f = sdir / "selection.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


# ---- 採点（生成直後の足切りに使う内部値）---------------------------------------------


def score_cards(sdir: Path, ids: list[str]) -> dict[str, float]:
    """画像を分類器で採点して、like らしさ p を返す。"""
    import numpy as np

    from train_scorer import SCORERS, clip_embeddings, sha256

    scorer = json.loads((SCORERS / "scorer.json").read_text(encoding="utf-8"))
    items = [{"id": i, "path": sdir / "images" / f"{i}.png", "sha256": sha256(sdir / "images" / f"{i}.png")} for i in ids]
    X, _ = clip_embeddings(items)
    z = X @ np.array(scorer["coef"], dtype=np.float64) + scorer["intercept"]
    p = 1.0 / (1.0 + np.exp(-z))
    return {i: round(float(v), 4) for i, v in zip(ids, p)}


class OnlineScorer:
    """分類器を 1 回だけ読み込み、生成直後の画像を採点する。"""

    def __init__(self) -> None:
        import torch
        from transformers import CLIPModel
        from train_scorer import MODEL_ID, CLIP_MEAN, CLIP_STD, SCORERS

        self.np = __import__("numpy")
        self.torch = torch
        self.mean = CLIP_MEAN
        self.std = CLIP_STD
        self.scorer = json.loads((SCORERS / "scorer.json").read_text(encoding="utf-8"))
        self.threshold = float(self.scorer.get("cutoff", {}).get("threshold", 0.0))
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.model = CLIPModel.from_pretrained(MODEL_ID).eval().to(self.device)

    def score(self, path: Path) -> float:
        from PIL import Image

        arr = (
            self.np.asarray(Image.open(path).convert("RGB").resize((224, 224), Image.BICUBIC), dtype=self.np.float32) / 255.0
            - self.mean
        ) / self.std
        x = self.torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to(self.device)
        with self.torch.no_grad():
            out = self.model.get_image_features(pixel_values=x)
        feats = out if isinstance(out, self.torch.Tensor) else out.pooler_output
        feats = self.torch.nn.functional.normalize(feats, dim=-1).cpu().numpy()[0]
        z = feats @ self.np.array(self.scorer["coef"], dtype=self.np.float64) + self.scorer["intercept"]
        return round(float(1.0 / (1.0 + self.np.exp(-z))), 4)


def make_thumbs(sdir: Path, ids: list[str]) -> None:
    """カードのページ用に、画像を WebP（幅 960）にして cards/ に置く。"""
    from PIL import Image

    out = sdir / "cards"
    out.mkdir(exist_ok=True)
    for i in ids:
        im = Image.open(sdir / "images" / f"{i}.png").convert("RGB")
        im = im.resize((CARD_WIDTH, round(im.height * CARD_WIDTH / im.width)), Image.LANCZOS)
        im.save(out / f"{i}.webp", "WEBP", quality=82, method=4)


def remove_candidate(sdir: Path, state: dict, cid: str, score: float, reason: str = "below_cutoff") -> None:
    """表示前に落とした画像を削除し、理由だけ state.json に残す。"""
    spec = load_spec(sdir)
    by_id = {card_id(it["id"]): it for it in spec_items(spec)}
    it = by_id.get(cid)
    if it:
        state.setdefault("rejected", []).append({"id": cid, "score": score, "reason": reason, "item": it})
    state["scores"][cid] = score
    for f in (sdir / "images" / f"{cid}.png", sdir / "images" / f"{cid}.json", sdir / "cards" / f"{cid}.webp"):
        f.unlink(missing_ok=True)


def discard(sdir: Path, state: dict, spec: dict, ids: list[str]) -> None:
    """カードから外す画像を削除する。spec.json からも外し（再生成されないように）、項目の内容は state.json に残す。"""
    items = spec_items(spec)
    gone = {item_id(c) for c in ids}
    state.setdefault("dropped_items", []).extend(it for it in items if it["id"] in gone)
    items[:] = [it for it in items if it["id"] not in gone]
    for c in ids:
        for f in (sdir / "images" / f"{c}.png", sdir / "images" / f"{c}.json", sdir / "cards" / f"{c}.webp"):
            f.unlink(missing_ok=True)
        state["scores"].pop(c, None)
    write_json(sdir / "spec.json", spec)


# ---- 1 ラウンド（アイデア単位に生成 → 直後に足切り）-------------------------------------------


def item_idea(item: dict) -> str:
    return str(item.get("idea_id") or f"item-{item['id']}")


def run_round(sdir: Path, state: dict, *, keep: list[str], new_items: list[dict], comfy: str, selection: dict | None) -> None:
    """keep を残し、候補をアイデア単位で順に生成する。低スコア画像は表示前に捨てる。"""
    from run_generate import generate_one

    old_cards = list(state["cards"])
    keep = [c for c in old_cards if c in keep]  # 前の並び順のまま
    drop_old = [c for c in old_cards if c not in keep]
    if drop_old:
        discard(sdir, state, load_spec(sdir), drop_old)

    spec = load_spec(sdir)
    items = spec_items(spec)
    seeds = [int(it["seed"]) for it in items + state.get("dropped_items", [])]
    next_seed = (max(seeds) if seeds else 0) + 1
    new_ids: list[str] = []
    protected: set[str] = set()
    by_new: dict[str, dict] = {}
    for it in new_items:
        source_id = it.get("source_id")
        if source_id:
            iid = str(source_id)
            existing = next((x for x in items if x["id"] == iid), None)
            if existing is None:
                raise ValueError(f"予備の項目が spec.json にありません: {iid}")
            existing.update(
                {
                    "label": it["label"],
                    "direction": it.get("direction", ""),
                    "text": it["text"],
                    "idea_id": it.get("idea_id", item_idea(existing)),
                    "variant": int(it.get("variant", existing.get("variant", 1))),
                }
            )
            if it.get("reason"):
                existing["reason"] = it["reason"]
            item = existing
        else:
            iid = f"{state['next_no']:02d}"
            state["next_no"] += 1
            seed, next_seed = next_seed, next_seed + 1
            item = {
                "id": iid,
                "label": it["label"],
                "direction": it.get("direction", ""),
                "text": it["text"],
                "seed": seed,
                "idea_id": it.get("idea_id", f"idea-{iid}"),
                "variant": int(it.get("variant", 1)),
            }
            if it.get("parent"):
                item["parent"] = it["parent"]
            for k in ("reason", "card_note"):
                if it.get(k):
                    item[k] = it[k]
        if not source_id:
            items.append(item)
        cid = card_id(iid)
        new_ids.append(cid)
        by_new[cid] = item
        if it.get("protect"):
            protected.add(cid)
    write_json(sdir / "spec.json", spec)

    state["phase"] = "generating"
    state["error"] = ""
    state["live"] = list(keep)
    state["progress"] = {"done": 0, "total": len(new_ids)}
    save_state(sdir, state)

    # 同じ idea_id の prompt は、1 枚通った時点で打ち切る。
    groups: list[tuple[str, list[str]]] = []
    for cid in new_ids:
        idea = item_idea(by_new[cid])
        if groups and groups[-1][0] == idea:
            groups[-1][1].append(cid)
        else:
            groups.append((idea, [cid]))

    accepted: list[str] = []
    generated: list[str] = []
    rejected: list[str] = []
    idea_status = state.setdefault("idea_status", {})
    scorer: OnlineScorer | None = None
    top_now = top_count(keep, state.get("origin", {}))
    slots = max(0, state["size"] - top_now)

    for idea, group in groups:
        if top_now >= state["size"] and not (group and all(cid in protected for cid in group)):
            break
        if group and all(cid in protected for cid in group):
            for cid in group:
                generated.append(cid)
                generate_one(sdir, item_id(cid), host=comfy)
                accepted.append(cid)
                make_thumbs(sdir, [cid])
                state["live"].append(cid)
                state["progress"] = {"done": len(generated), "total": len(new_ids)}
                save_state(sdir, state)
            idea_status[idea] = "accepted"
            continue
        passed = False
        for cid in group:
            iid = item_id(cid)
            generated.append(cid)
            try:
                generate_one(sdir, iid, host=comfy)
            except Exception:
                raise
            png = sdir / "images" / f"{cid}.png"
            if cid in protected:
                accepted.append(cid)
                make_thumbs(sdir, [cid])
                state["live"].append(cid)
                passed = True
            else:
                if scorer is None:
                    scorer = OnlineScorer()
                score = scorer.score(png)
                state["scores"][cid] = score
                if score >= scorer.threshold:
                    accepted.append(cid)
                    make_thumbs(sdir, [cid])
                    state["live"].append(cid)
                    passed = True
                else:
                    rejected.append(cid)
                    remove_candidate(sdir, state, cid, score)
            state["progress"] = {"done": len(generated), "total": len(new_ids)}
            save_state(sdir, state)
            if passed:
                break
        idea_status[idea] = "accepted" if passed else "exhausted"
        if passed and group[0] not in protected:
            top_now += 1

    prev_origin = state.get("origin", {})
    chosen_new = accepted
    items_by = {card_id(it["id"]): it for it in spec_items(load_spec(sdir))}
    state["origin"] = {
        **{c: (prev_origin[c] if is_child(prev_origin, c, keep) else {"kind": "kept"}) for c in keep},
        **{
            c: {"kind": "derived", "parent": items_by[c].get("parent")}
            if c in protected
            else {"kind": "new"}
            for c in chosen_new
        },
    }
    cards = list(keep) + chosen_new
    state["history"].append(
        {
            "round": state["round"],
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "selection": selection,
            "new": generated,
            "kept": keep,
            "discarded": drop_old + rejected,
        }
    )
    state["cards"] = cards
    state["live"] = []
    state["round"] += 1
    state["phase"] = "ready"
    state["shortfall"] = max(0, state["size"] - top_count(cards, state["origin"]))
    state["error"] = ""
    state["progress"] = {}
    save_state(sdir, state)
    (sdir / "selection.json").unlink(missing_ok=True)
    print(f"カードを更新しました（{len(cards)} 件。残した {len(keep)}、生成を試した {len(generated)}、採用 {len(accepted)}、捨てた {len(drop_old) + len(rejected)}）")
    if state["shortfall"]:
        print(f"注意: あと {state['shortfall']} 件足りません。追加のアイデアを用意して add してください", file=sys.stderr)

def run_guarded(sdir: Path, state: dict, fn) -> int:
    """fn を実行し、失敗したら phase=error と理由を state.json に残す。"""
    try:
        fn()
        return 0
    except BaseException as e:  # noqa: BLE001  KeyboardInterrupt でも状態を残す
        state["phase"] = "error"
        state["error"] = f"{type(e).__name__}: {e}"
        save_state(sdir, state)
        traceback.print_exc()
        return 1


def load_items(path: str) -> list[dict]:
    from new_eval_run import load_json_lenient

    try:
        items = load_json_lenient(path, "items")
    except ValueError as e:
        sys.exit(str(e))
    if not isinstance(items, list) or not items:
        sys.exit("items は、項目の配列にしてください")
    for it in items:
        for k in ("label", "text"):
            if not isinstance(it, dict) or not it.get(k):
                sys.exit(f"items の項目に {k} がありません: {it}")
    return items


# ---- 再生成の計画（メモの有無で、AI が要るかが決まる）-------------------------------------------

def is_child(origin: dict, cid: str, cards: list[str]) -> bool:
    """派生カードで、元のカードもカードにあるとき True。派生は、元のカードの中に隠れる（件数にも数えない）。"""
    o = origin.get(cid, {})
    return o.get("kind") == "derived" and o.get("parent") in cards


def top_count(cards: list[str], origin: dict) -> int:
    return sum(1 for c in cards if not is_child(origin, c, cards))


def item_by_card(sdir: Path) -> dict[str, dict]:
    return {card_id(it["id"]): it for it in spec_items(load_spec(sdir))}


DERIVE_VARIANTS = 3


def reserve_groups(sdir: Path, state: dict, limit: int) -> list[list[dict]]:
    """まだ試していないアイデアを、spec.json の順に取り出す。"""
    by_idea: dict[str, list[dict]] = {}
    for it in spec_items(load_spec(sdir)):
        by_idea.setdefault(item_idea(it), []).append(it)
    status = state.setdefault("idea_status", {})
    active = set(state.get("cards", []))
    rejected = {x.get("id") for x in state.get("rejected", [])}
    groups = []
    for idea, items in by_idea.items():
        if len(groups) >= limit or status.get(idea) in ("accepted", "exhausted"):
            continue
        items = [it for it in items if card_id(it["id"]) not in active and card_id(it["id"]) not in rejected]
        if items:
            groups.append(items)
    return groups


def build_plan(sdir: Path, state: dict, sel: dict | None, *, mode: str = "regen") -> dict:
    """再生成（regen）または補充（add）の候補計画を作る。

    同じ idea_id の prompt は複数あっても、通常は最初に足切りを通った 1 枚だけ採用する。
    個別の派生だけは、最大 DERIVE_VARIANTS 枚をすべて表示する。
    """
    sel = sel or {}
    by_id = item_by_card(sdir)
    cards = list(state["cards"])
    origin = state.get("origin", {})
    if mode == "add":
        keep, notes, global_note = list(cards), {}, ""
    else:
        keep = [c for c in sel.get("keep", []) if c in cards]
        # 個別の方向は、残すカードだけが対象。選んでいないカードは、方向が入っていても捨てる。
        notes = {c: t.strip() for c, t in (sel.get("notes") or {}).items() if c in keep and t.strip()}
        global_note = (sel.get("note") or "").strip()

    slots = max(0, state["size"] - top_count(keep, origin))
    requests: list[dict] = []
    for c, text in notes.items():
        for variant in range(1, DERIVE_VARIANTS + 1):
            requests.append(
                {
                    "key": f"derive-{c}-{variant}",
                    "kind": "derive",
                    "base": c,
                    "base_direction": by_id[c].get("direction") or by_id[c]["label"],
                    "direction": by_id[c].get("direction") or by_id[c]["label"],
                    "base_prompt": by_id[c]["text"],
                    "card_note": text,
                    "variant_count": DERIVE_VARIANTS,
                    "idea_id": f"derive-{c}",
                    "variant": variant,
                    "needs_ai": True,
                }
            )

    # 空き枠より多めのアイデアを予約する。同じアイデアの別 prompt は run_round が順番に試す。
    reserve_limit = max(1, math.ceil(slots * 1.5)) if slots else 0
    reserve = reserve_groups(sdir, state, reserve_limit)
    for group in reserve:
        for it in group:
            requests.append(
                {
                    "key": f"fill-{it['id']}",
                    "kind": "fill",
                    "base": None,
                    "base_direction": it.get("direction") or it["label"],
                    "direction": it.get("direction") or it["label"],
                    "base_prompt": it["text"],
                    "source_id": it["id"],
                    "reason": it.get("reason", ""),
                    "idea_id": item_idea(it),
                    "variant": int(it.get("variant", 1)),
                    "needs_ai": bool(global_note),
                }
            )
    # 予備が尽きたときの新しいアイデアは、人が「足りない分を補う」を押したとき（add）だけ AI に頼む。
    missing_ideas = max(0, reserve_limit - len(reserve)) if mode == "add" else 0
    for n in range(missing_ideas):
        requests.append(
            {
                "key": f"new-idea-{n + 1}",
                "kind": "new_idea",
                "base": None,
                "base_direction": "",
                "direction": "新しいアイデア",
                "base_prompt": "",
                "idea_id": f"new-idea-{n + 1}",
                "variant": 1,
                "needs_ai": True,
            }
        )
    return {
        "mode": mode,
        "keep": keep,
        "global_note": global_note,
        "requests": requests,
        "needs_ai": any(r["needs_ai"] for r in requests),
        "shortfall": slots,
        "concept": load_spec(sdir).get("concept", ""),
        "existing_directions": [by_id[c].get("direction", "") for c in cards if c in by_id],
    }


COMPOSE_RULES = """あなたは、画像生成（Stable Diffusion 系）のプロンプトを書き換える担当です。
次の JSON の requests の各項目について、新しいプロンプト（英語）、その方針を表すタイトル（日本語）、採用した理由（日本語）を書いてください。

【kind が derive のとき（個別の方向からの派生）】
- card_note は、その画像だけに向けた方向（日本語）です。global_note は反映しない。
- 同じ base の derive は 3 件（variant 1〜3）あります。**元の画像とはっきり違って見えること**。同じ配置・同じ密度に見えるのは失敗です。
- 3 件は、card_note の**解釈を変える**（形・配置・密度・色数のどれかを大きく変える）。3 件で語句の共通部分が 8 割を超えてはいけません。
- card_note に関係する語句は、プロンプトの前のほう（形式の語句の直後）に置き、`(語句:1.3)` の形で重みを付ける（1〜2 か所。必須）。
- card_note と矛盾する元の語句は取り除く。方向に関係しない語句は、元のまま残してよい（元の語句の 3〜8 割は残す。0 割は、別の絵になるので差し戻す）。
- 風景を連想させる語（space, field, garden, landscape, scene, network など）は、風景に化けやすい。形の語（flat circles, bars, diagonal stripes, grid of dots など）で具体的に書く。

【kind が fill のとき（予備のアイデアに全体の方針を反映）】
- base_prompt を土台に、global_note を反映する。方向に関係しない語句は、一語も変えずに残す（3 割以上残す）。

【kind が new_idea のとき】
- 既存の方向（existing_directions）と重ならない、新しいアイデアの prompt を書く。base_prompt はありません。

【共通】
- 形式（flat graphic decoration, full frame composition, ... no text, no people, no hands のような、カンマ区切りの英語）を保つ。
- 様式名・作者名・人物は書かない。色・形・素材感を具体的に書く。文字は入れない。
- needs_ai が false の項目は、出力に含めない。

【タイトルと理由】
- title: 8〜20 字の日本語。derive / fill は base_direction（元の方針）と反映した方向を、**合体させた 1 つの方針**にする。new_idea は新しいアイデアの方針を短く表す。方向の文言をそのまま写さない。「別の seed」「派生」「再生成」のような言葉は入れない。
- reason: 1〜2 文の日本語。なぜこの案を採用したか（derive は、元の案の何を残し何を変えたか。new_idea は、既存と何が違う方向か）。

出力は、次の形の JSON 配列だけにしてください（説明やコードフェンスは不要）。
[{"key": "<requests の key>", "title": "<方針（日本語）>", "reason": "<採用した理由（日本語）>", "text": "<新しいプロンプト（英語）>"}, ...]
"""

# 元の語句の残り具合を調べるとき、全部のプロンプトに共通する語句は数えない
_COMMON = {"flat graphic decoration", "abstract flat decoration", "full frame composition"}
KEEP_RANGE = {"derive": (0.3, 0.8), "fill": (0.3, 1.0)}  # 元の語句が残る割合の範囲
DERIVE_SIBLING_MAX = 0.8  # 同じ元からの派生どうしで、語句が共通する割合の上限
_WEIGHTED = re.compile(r"\([^()]+:\d(?:\.\d+)?\)")


def content_phrases(prompt: str) -> list[str]:
    out = []
    for ph in (x.strip().lower() for x in prompt.split(",")):
        if ph and ph not in _COMMON and not ph.startswith("no "):
            out.append(ph)
    return out


def keep_ratio(base: str, new: str) -> float:
    """base の語句のうち、new にそのまま残っている割合。"""
    b, n = content_phrases(base), set(content_phrases(new))
    return sum(1 for x in b if x in n) / len(b) if b else 1.0


def compose_text(plan: dict, problem: str = "") -> str:
    """AI に渡す依頼文。problem は、前回の返答の差し戻し理由。"""
    reqs = [
        {k: r[k] for k in ("key", "kind", "base_direction", "base_prompt", "card_note") if k in r} | {"needs_ai": r["needs_ai"]}
        for r in plan["requests"]
        if r["needs_ai"]
    ]
    payload = {
        "concept": plan.get("concept", ""),
        "existing_directions": plan.get("existing_directions", []),
        "global_note": plan["global_note"],
        "requests": reqs,
    }
    text = COMPOSE_RULES + "\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```\n"
    if problem:
        text += f"\n前回の返答は、次の理由で差し戻されました。直してください。\n{problem}\n"
    return text


def parse_compose_result(text: str, plan: dict) -> dict[str, dict]:
    """AI の出力から JSON 配列を取り出し、key → {text, title, reason} にする。不正なら ValueError。

    差し戻す条件: 項目の欠け / 元の語句の残り具合が範囲外（派生は 3〜8 割、補充は 3 割以上）/
    派生に重み付きの語句（(語句:1.3)）がない / 同じ元からの派生どうしが似すぎ。
    """
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        raise ValueError("JSON の配列が見つかりません")
    raw = text[start : end + 1]
    try:
        data = json.loads(raw)
    except ValueError:
        from new_eval_run import _repair_json  # 末尾のカンマなど、AI の書き崩れは直して読む

        try:
            data = json.loads(_repair_json(raw)[0])
        except ValueError as e:
            raise ValueError(f"JSON として読めません: {e}") from e
    result: dict[str, dict] = {}
    for row in data if isinstance(data, list) else []:
        if isinstance(row, dict) and isinstance(row.get("key"), str) and isinstance(row.get("text"), str) and row["text"].strip():
            title, reason = row.get("title"), row.get("reason")
            result[row["key"]] = {
                "text": row["text"].strip(),
                "title": title.strip() if isinstance(title, str) else "",
                "reason": reason.strip() if isinstance(reason, str) else "",
            }
    reqs = {r["key"]: r for r in plan["requests"] if r["needs_ai"]}
    missing = [k for k in reqs if k not in result]
    if missing:
        raise ValueError(f"次の項目のプロンプトがありません: {', '.join(missing)}")
    far, flat = [], []
    for k, r in reqs.items():
        if r["kind"] not in KEEP_RANGE:  # new_idea は元のプロンプトがないので、残り具合を調べない
            continue
        lo, hi = KEEP_RANGE[r["kind"]]
        ratio = keep_ratio(r["base_prompt"], result[k]["text"])
        if ratio < lo:
            far.append(f"{k}（元の語句が {round(ratio * 100)}% しか残っていません。{round(lo * 100)}% 以上にしてください）")
        elif ratio > hi:
            far.append(f"{k}（元の語句が {round(ratio * 100)}% 残っていて、変化が弱すぎます。{round(hi * 100)}% 以下にして、方向に合わせて大きく変えてください）")
        if r["kind"] == "derive" and not _WEIGHTED.search(result[k]["text"]):
            flat.append(k)
    problems = []
    if far:
        problems.append("元のプロンプトとの距離が不適切です: " + "、".join(far))
    if flat:
        problems.append("方向の語句に (語句:1.3) の重みが付いていません: " + "、".join(flat))
    by_base: dict[str, list[str]] = {}
    for k, r in reqs.items():
        if r["kind"] == "derive":
            by_base.setdefault(r["base"], []).append(k)
    twins = []
    for keys in by_base.values():
        for i, a in enumerate(keys):
            for b in keys[i + 1 :]:
                sim = max(keep_ratio(result[a]["text"], result[b]["text"]), keep_ratio(result[b]["text"], result[a]["text"]))
                if sim > DERIVE_SIBLING_MAX:
                    twins.append(f"{a} と {b}（共通 {round(sim * 100)}%）")
    if twins:
        problems.append(f"同じ元からの派生が似すぎです。解釈を変えて、{round(DERIVE_SIBLING_MAX * 100)}% 以下にしてください: " + "、".join(twins))
    if problems:
        raise ValueError("。".join(problems))
    return {k: v for k, v in result.items() if k in reqs}


# ---- AI（composer）。呼び方は環境変数だけ。未設定なら、ページで貼って渡す ----------------------------
# CIGAR_COMPOSER_CMD は「依頼文を標準入力 → 返答を標準出力」のコマンド。特定のツールには固定しない。
# 依頼と返答は、デバッグのため sessions/<id>/compose_logs/ に毎回残す。

COMPOSER_TIMEOUT = 300


class ComposerUnavailable(RuntimeError):
    pass


def composer_command() -> str:
    return os.environ.get("CIGAR_COMPOSER_CMD", "").strip()


def composer_available() -> bool:
    return bool(composer_command())


def run_composer(text: str) -> str:
    """CIGAR_COMPOSER_CMD に依頼文を渡して、返答の文字列を得る。リポジトリの外のディレクトリで実行する。"""
    cmd = composer_command()
    if not cmd:
        raise ComposerUnavailable("CIGAR_COMPOSER_CMD が未設定です。ページで依頼文を貼って渡してください")
    try:
        r = subprocess.run(
            shlex.split(cmd),
            input=text,
            capture_output=True,
            text=True,
            timeout=COMPOSER_TIMEOUT,
            cwd=tempfile.gettempdir(),
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"AI が {COMPOSER_TIMEOUT} 秒以内に返答しませんでした") from e
    if r.returncode != 0:
        raise RuntimeError(f"AI の呼び出しに失敗しました（終了コード {r.returncode}）: {((r.stderr or '') + (r.stdout or '')).strip()[-400:]}")
    return r.stdout


def log_compose(sdir: Path, tag: str, name: str, body: str) -> None:
    d = sdir / "compose_logs"
    d.mkdir(exist_ok=True)
    (d / f"{tag}-{name}.txt").write_text(body, encoding="utf-8")


def compose(sdir: Path, plan: dict) -> dict[str, dict]:
    """AI にプロンプトを書かせる。検査で差し戻されたら、理由を添えて 1 回だけ頼み直す。依頼と返答は compose_logs/ に残す。"""
    tag = datetime.now().strftime("%H%M%S")
    problem = ""
    for attempt in (1, 2):
        text = compose_text(plan, problem)
        log_compose(sdir, tag, f"{attempt}-request", text)
        out = run_composer(text)
        log_compose(sdir, tag, f"{attempt}-response", out)
        try:
            return parse_compose_result(out, plan)
        except ValueError as e:
            log_compose(sdir, tag, f"{attempt}-problem", str(e))
            if attempt == 2:
                raise
            problem = str(e)
    raise AssertionError("unreachable")


def plan_items(plan: dict, prompts: dict[str, dict]) -> list[dict]:
    """計画と、AI が書いたプロンプト・タイトル・理由から、run_round に渡す項目にする。"""
    items = []
    for r in plan["requests"]:
        if r["needs_ai"]:
            got = prompts.get(r["key"])
            if not got:
                raise ValueError(f"プロンプトがありません: {r['key']}")
            text, title, reason = got["text"], got.get("title") or r["direction"], got.get("reason", "")
        else:
            text, title, reason = r["base_prompt"], r["direction"], r.get("reason", "")
        it = {
            "label": r["kind"],
            "direction": title,
            "text": text,
            "idea_id": r.get("idea_id"),
            "variant": r.get("variant", 1),
        }
        if reason:
            it["reason"] = reason
        if r.get("source_id"):
            it["source_id"] = r["source_id"]
        if r["kind"] == "derive":
            it["parent"] = r["base"]
            it["protect"] = True
            it["card_note"] = r.get("card_note", "")
        items.append(it)
    return items


# ---- コマンド ---------------------------------------------------------------------------


def cmd_new(args) -> int:
    from new_eval_run import build_spec, load_json_lenient, validate_brief

    try:
        brief = validate_brief(load_json_lenient(args.brief, "brief"))
    except ValueError as e:
        sys.exit(str(e))
    spec = build_spec(brief)
    sdir = SESSIONS / f"{datetime.now():%Y%m%d-%H%M%S}-{brief['slug']}"
    sdir.mkdir(parents=True)
    write_json(sdir / "spec.json", spec)
    items = spec_items(spec)
    state = {
        "size": args.size,
        "round": 0,
        "phase": "new",
        "error": "",
        "progress": {},
        "cards": [],
        "live": [],
        "origin": {},
        "scores": {},
        "rejected": [],
        "idea_status": {},
        "shortfall": 0,
        "next_no": len(items) + 1,
        "dropped_items": [],
        "history": [],
    }
    save_state(sdir, state)
    print(sdir)
    return 0


def cmd_generate(args) -> int:
    sdir = resolve(args.session)
    state = load_state(sdir)
    if state["round"] != 0:
        sys.exit("最初の候補は生成済みです。regen（選んだカードを残す）か add（足りない分を補う）を使ってください")
    spec = load_spec(sdir)
    ids = [card_id(it["id"]) for it in spec_items(spec)]
    # 最初の項目は spec.json にあるので、新しい項目として扱う（採点・下位の破棄も同じ流れ）
    state["next_no"] = max(state["next_no"], len(ids) + 1)

    def work() -> None:
        _first_round(sdir, state, ids, args.comfy)

    return run_guarded(sdir, state, work)


def _first_round(sdir: Path, state: dict, ids: list[str], comfy: str) -> None:
    """候補をアイデア単位で生成し、画像直後の足切りを通ったものだけカードにする。"""
    from run_generate import generate_one

    spec = load_spec(sdir)
    by_id = {card_id(it["id"]): it for it in spec_items(spec)}
    groups: list[tuple[str, list[str]]] = []
    for cid in ids:
        idea = item_idea(by_id[cid])
        if groups and groups[-1][0] == idea:
            groups[-1][1].append(cid)
        else:
            groups.append((idea, [cid]))

    state["phase"] = "generating"
    state["live"] = []
    state["error"] = ""
    state["progress"] = {"done": 0, "total": len(ids)}
    save_state(sdir, state)
    scorer: OnlineScorer | None = None
    accepted: list[str] = []
    generated: list[str] = []
    rejected: list[str] = []
    idea_status = state.setdefault("idea_status", {})

    for idea, group in groups:
        if len(accepted) >= state["size"]:
            break
        passed = False
        for cid in group:
            generated.append(cid)
            generate_one(sdir, item_id(cid), host=comfy)
            png = sdir / "images" / f"{cid}.png"
            if scorer is None:
                scorer = OnlineScorer()
            score = scorer.score(png)
            state["scores"][cid] = score
            if score >= scorer.threshold:
                accepted.append(cid)
                make_thumbs(sdir, [cid])
                state["live"].append(cid)
                passed = True
            else:
                rejected.append(cid)
                remove_candidate(sdir, state, cid, score)
            state["progress"] = {"done": len(generated), "total": len(ids)}
            save_state(sdir, state)
            if passed:
                break
        idea_status[idea] = "accepted" if passed else "exhausted"

    state["cards"] = accepted
    state["origin"] = {c: {"kind": "new"} for c in accepted}
    state["history"].append(
        {
            "round": 0,
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "selection": None,
            "new": generated,
            "kept": [],
            "discarded": rejected,
        }
    )
    state["live"] = []
    state["round"] = 1
    state["phase"] = "ready"
    state["shortfall"] = max(0, state["size"] - len(accepted))
    state["progress"] = {}
    save_state(sdir, state)
    print(f"カードを作りました（{len(accepted)} 件。生成を試した {len(generated)}、捨てた {len(rejected)}）")
    if state["shortfall"]:
        print(f"注意: あと {state['shortfall']} 件足りません。追加のアイデアを用意して add してください", file=sys.stderr)


def _auto_items(sdir: Path, state: dict, args, mode: str) -> tuple[list[str], list[dict]]:
    """--auto のとき、計画から keep と項目を作る。メモがあれば、--prompts（AI の出力）が要る。"""
    sel = read_selection(sdir)
    plan = build_plan(sdir, state, sel, mode=mode)
    prompts: dict[str, str] = {}
    if plan["needs_ai"]:
        if not args.prompts:
            sys.exit("メモがあるので、AI が書いたプロンプトが要ります。session.py plan で依頼文を作り、--prompts に結果の JSON を渡してください")
        try:
            prompts = parse_compose_result(Path(args.prompts).read_text(encoding="utf-8"), plan)
        except ValueError as e:
            sys.exit(f"--prompts が不正です: {e}")
    if not plan["requests"] and (mode == "add" or not plan["keep"]):
        sys.exit("作る候補がありません（空き枠がないか、残すカードがありません）")
    # regen で予備が尽きていても、選んだカードは残す。足りない分は、人が「足りない分を補う」を押したときに補う
    return plan["keep"], plan_items(plan, prompts)


def cmd_regen(args) -> int:
    sdir = resolve(args.session)
    state = load_state(sdir)
    if state["phase"] == "generating":
        sys.exit("生成中です。終わってから実行してください")
    if state["round"] == 0:
        sys.exit("先に generate で最初の候補を作ってください")
    sel = read_selection(sdir) or {}
    if args.auto:
        keep, new_items = _auto_items(sdir, state, args, "regen")
    else:
        if not args.items:
            sys.exit("--items か --auto のどちらかが要ります")
        keep = [c for c in sel.get("keep", []) if c in state["cards"]]
        new_items = load_items(args.items)
        slots = state["size"] - len(keep)
        if len(new_items) < slots:
            print(f"注意: 空き枠 {slots} に対して、新しい項目が {len(new_items)} 件です。size に届きません", file=sys.stderr)
    return run_guarded(
        sdir, state, lambda: run_round(sdir, state, keep=keep, new_items=new_items, comfy=args.comfy, selection=sel or None)
    )


def cmd_add(args) -> int:
    sdir = resolve(args.session)
    state = load_state(sdir)
    if state["phase"] == "generating":
        sys.exit("生成中です。終わってから実行してください")
    if state["round"] == 0:
        sys.exit("先に generate で最初の候補を作ってください")
    if args.auto:
        keep, new_items = _auto_items(sdir, state, args, "add")
    else:
        if not args.items:
            sys.exit("--items か --auto のどちらかが要ります")
        new_items = load_items(args.items)
        keep = list(state["cards"])
    return run_guarded(sdir, state, lambda: run_round(sdir, state, keep=keep, new_items=new_items, comfy=args.comfy, selection=None))


def cmd_plan(args) -> int:
    """選択（selection.json）から、再生成 / 補充の計画と、AI への依頼文を出す。"""
    sdir = resolve(args.session)
    state = load_state(sdir)
    plan = build_plan(sdir, state, read_selection(sdir), mode=args.mode)
    out = {
        "mode": plan["mode"],
        "needs_ai": plan["needs_ai"],
        "keep": plan["keep"],
        "new": [{k: r[k] for k in ("key", "kind", "direction", "needs_ai")} for r in plan["requests"]],
        "instruction": compose_text(plan) if plan["needs_ai"] else "",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_selection(args) -> int:
    sdir = resolve(args.session)
    state = load_state(sdir)
    sel = read_selection(sdir)
    by_id = {card_id(it["id"]): it for it in spec_items(load_spec(sdir))}

    def info(cid: str) -> dict:
        meta = {}
        f = sdir / "images" / f"{cid}.json"
        if f.exists():
            m = json.loads(f.read_text(encoding="utf-8"))
            meta = {"prompt": m.get("prompt"), "seed": m.get("seed")}
        return {"id": cid, "direction": by_id.get(cid, {}).get("direction", ""), **meta}

    out = {
        "phase": state["phase"],
        "round": state["round"],
        "selected": bool(sel),
        "submitted": bool(sel and sel.get("submitted")),
        "action": (sel or {}).get("action"),
        "keep": [info(c) for c in (sel or {}).get("keep", [])],
        "note": (sel or {}).get("note", ""),
        "card_notes": (sel or {}).get("notes", {}),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_status(args) -> int:
    sdir = resolve(args.session)
    state = load_state(sdir)
    sel = read_selection(sdir)
    print(
        json.dumps(
            {
                "phase": state["phase"],
                "round": state["round"],
                "size": state["size"],
                "progress": state.get("progress", {}),
                "error": state.get("error", ""),
                "cards": state["cards"],
                "shortfall": state.get("shortfall", 0),
                "selection": None
                if not sel
                else {"keep": len(sel.get("keep", [])), "action": sel.get("action"), "submitted": bool(sel.get("submitted"))},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new", help="session を作る")
    p.add_argument("brief")
    p.add_argument("--size", type=int, default=DEFAULT_SIZE, help=f"カードの件数（既定 {DEFAULT_SIZE}）")
    p.set_defaults(fn=cmd_new)

    for name, fn, help_ in (
        ("generate", cmd_generate, "最初の候補を生成してカードを作る"),
        ("regen", cmd_regen, "選んだカードを残して再生成する"),
        ("add", cmd_add, "全カードを残したまま、足りない分を補う"),
        ("selection", cmd_selection, "ページで選ばれた内容を表示する"),
        ("plan", cmd_plan, "選択から、再生成 / 補充の計画と、AI への依頼文を出す"),
        ("status", cmd_status, "状況を表示する"),
    ):
        p = sub.add_parser(name, help=help_)
        p.add_argument("session", type=Path)
        if name in ("generate", "regen", "add"):
            p.add_argument("--comfy", default="http://127.0.0.1:8188", help="ComfyUI の URL")
        if name in ("regen", "add"):
            p.add_argument("--items", help="新しい項目の JSON（AI が書いたとき）")
            p.add_argument("--auto", action="store_true", help="計画（plan）から作る。メモがあるときは --prompts が要る")
            p.add_argument("--prompts", help="AI が書いたプロンプトの JSON（plan の instruction への返答）")
        if name == "plan":
            p.add_argument("--mode", choices=("regen", "add"), default="regen")
        p.set_defaults(fn=fn)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
