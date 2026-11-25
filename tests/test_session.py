"""session の動作確認（ComfyUI・分類器・外部の AI なしで動く）。

    uv run python -m unittest discover -s tests -v

結果の記録は tests/results/ に置く（tests/README.md）。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as F  # noqa: E402

import serve_session as SV  # noqa: E402
import session as S  # noqa: E402
from new_eval_run import _repair_json, load_json_lenient, validate_brief  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        patcher = mock.patch.object(S, "SESSIONS", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        sv = mock.patch.object(SV, "SESSIONS", self.root)
        sv.start()
        self.addCleanup(sv.stop)
        self.addCleanup(self.tmp.cleanup)

    def session(self, **kw) -> Path:
        return F.build_session(self.root, **kw)

    def select(self, sdir: Path, keep, notes=None, note="") -> dict:
        state = S.load_state(sdir)
        sel = SV.validate_selection({"round": state["round"], "keep": keep, "notes": notes or {}, "note": note, "action": "regen", "submitted": True}, state)
        S.write_json(sdir / "selection.json", sel)
        return sel


class JsonRepair(unittest.TestCase):
    def load(self, text: str):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write(text)
        self.addCleanup(os.unlink, f.name)
        with mock.patch("sys.stderr"):
            return load_json_lenient(f.name)

    def test_trailing_comma_comment_fence(self):
        d = self.load('```json\n{"a": [1, 2,], // メモ\n "b": "x, \\"y\\"",}\n```')
        self.assertEqual(d, {"a": [1, 2], "b": 'x, "y"'})

    def test_unclosed_and_missing_comma(self):
        self.assertEqual(self.load('{"a": [{"x": 1} {"x": 2}'), {"a": [{"x": 1}, {"x": 2}]})

    def test_unfixable_reports_location(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write('{"a": "1" "b": 2}')
        self.addCleanup(os.unlink, f.name)
        with self.assertRaises(ValueError) as cm:
            load_json_lenient(f.name)
        self.assertIn("1 行", str(cm.exception))

    def test_validate_brief(self):
        with self.assertRaises(ValueError):
            validate_brief({"slug": "x"})


class Plan(Base):
    def test_notes_apply_only_to_kept_cards(self):
        sdir = self.session()
        sel = self.select(sdir, ["p-01"], {"p-01": "もっと大きく", "p-02": "選んでいない方向"})
        self.assertEqual(sel["keep"], ["p-01"])
        self.assertEqual(sel["notes"], {"p-01": "もっと大きく"})  # 選んでいない p-02 の方向は捨てられる
        plan = S.build_plan(sdir, S.load_state(sdir), sel)
        derives = [r for r in plan["requests"] if r["kind"] == "derive"]
        self.assertEqual(len(derives), 3)
        self.assertTrue(all(r["base"] == "p-01" for r in derives))
        self.assertEqual(plan["keep"], ["p-01"])

    def test_unselected_card_with_note_is_not_forced(self):
        sdir = self.session()
        sel = self.select(sdir, [], {"p-02": "方向だけ書いた"})
        self.assertEqual(sel["keep"], [])
        self.assertEqual(sel["notes"], {})

    def test_build_plan_ignores_notes_of_unkept_cards(self):
        sdir = self.session()
        sel = {"keep": ["p-01"], "notes": {"p-02": "選んでいない"}, "note": ""}  # validate_selection を通らない生の選択でも
        plan = S.build_plan(sdir, S.load_state(sdir), sel)
        self.assertFalse(any(r["kind"] == "derive" for r in plan["requests"]))
        self.assertEqual(plan["keep"], ["p-01"])

    def test_regen_never_asks_for_new_ideas_but_add_does(self):
        sdir = self.session(n_ideas=4)  # 予備なし
        sel = self.select(sdir, ["p-01"])
        regen = S.build_plan(sdir, S.load_state(sdir), sel)
        self.assertFalse(any(r["kind"] == "new_idea" for r in regen["requests"]))
        self.assertFalse(regen["needs_ai"])
        state = S.load_state(sdir)
        state["cards"], state["shortfall"] = ["p-01"], 3
        add = S.build_plan(sdir, state, None, mode="add")
        self.assertTrue(any(r["kind"] == "new_idea" for r in add["requests"]))

    def test_derive_ignores_global_note_and_fill_uses_it(self):
        sdir = self.session()
        sel = self.select(sdir, ["p-01"], {"p-01": "密度を上げる"}, note="暗い地に")
        plan = S.build_plan(sdir, S.load_state(sdir), sel)
        text = S.compose_text(plan)
        self.assertIn("global_note は反映しない", text)
        fills = [r for r in plan["requests"] if r["kind"] == "fill"]
        self.assertTrue(fills and all(r["needs_ai"] for r in fills))


class ComposeChecks(Base):
    def plan(self):
        sdir = self.session()
        sel = self.select(sdir, ["p-01"], {"p-01": "円を大きく"})
        return sdir, S.build_plan(sdir, S.load_state(sdir), sel)

    def answer(self, plan, make) -> str:
        return json.dumps([{"key": r["key"], "title": "t", "reason": "r", "text": make(r)} for r in plan["requests"] if r["needs_ai"]])

    def good(self, r):
        k = r["key"][-1]
        ph = [p.strip() for p in r["base_prompt"].split(",")]
        return ", ".join(ph[:2] + [f"(big circle {k}:1.3)"] + ph[2:7] + [f"shape{k}", f"layout{k}", "no text"])

    def test_good_answer_passes_and_keeps_reason(self):
        _, plan = self.plan()
        got = S.parse_compose_result(self.answer(plan, self.good), plan)
        self.assertEqual(len(got), 3)
        self.assertTrue(all(v["reason"] == "r" for v in got.values()))

    def test_missing_weight_rejected(self):
        _, plan = self.plan()
        with self.assertRaises(ValueError) as cm:
            S.parse_compose_result(self.answer(plan, lambda r: self.good(r).replace(":1.3)", ")")), plan)
        self.assertIn("重み", str(cm.exception))

    def test_too_close_to_base_rejected(self):
        _, plan = self.plan()
        with self.assertRaises(ValueError) as cm:
            S.parse_compose_result(self.answer(plan, lambda r: r["base_prompt"] + ", (big:1.3)"), plan)
        self.assertIn("変化が弱すぎ", str(cm.exception))

    def test_unrelated_prompt_rejected(self):
        _, plan = self.plan()
        with self.assertRaises(ValueError) as cm:
            S.parse_compose_result(self.answer(plan, lambda r: "(a:1.3), totally different, words only"), plan)
        self.assertIn("しか残っていません", str(cm.exception))

    def test_identical_siblings_rejected(self):
        _, plan = self.plan()
        with self.assertRaises(ValueError) as cm:
            S.parse_compose_result(self.answer(plan, lambda r: self.good({**r, "key": "x-1"})), plan)
        self.assertIn("似すぎ", str(cm.exception))

    def test_repairs_trailing_comma(self):
        _, plan = self.plan()
        raw = self.answer(plan, self.good)
        S.parse_compose_result("説明です\n" + raw[:-1] + ",]", plan)


class ComposerRun(Base):
    def setUp(self) -> None:
        super().setUp()
        self.stub = self.root / "fake_ai.py"
        self.stub.write_text(F.FAKE_AI, encoding="utf-8")
        env = mock.patch.dict(os.environ, {"CIGAR_COMPOSER_CMD": f"{sys.executable} {self.stub}"})
        env.start()
        self.addCleanup(env.stop)

    def test_compose_logs_and_retries_after_rejection(self):
        sdir = self.session()
        sel = self.select(sdir, ["p-01"], {"p-01": "円を大きく"})
        plan = S.build_plan(sdir, S.load_state(sdir), sel)
        with mock.patch.dict(os.environ, {"FAKE_AI_BAD_FIRST": "1"}):
            got = S.compose(sdir, plan)
        self.assertEqual(len([k for k in got if k.startswith("derive-")]), 3)
        logs = sorted(p.name for p in (sdir / "compose_logs").iterdir())
        self.assertTrue(any("1-problem" in n for n in logs), logs)  # 1 回目は差し戻された
        self.assertTrue(any("2-response" in n for n in logs), logs)  # 理由を添えて頼み直した

    def test_unset_composer_is_not_called(self):
        with mock.patch.dict(os.environ, {"CIGAR_COMPOSER_CMD": ""}):
            self.assertFalse(S.composer_available())
            with self.assertRaises(S.ComposerUnavailable):
                S.run_composer("x")


class RunRound(Base):
    def run_regen(self, sdir: Path, sel: dict, prompts: dict | None = None, allow=()) -> dict:
        import run_generate

        state = S.load_state(sdir)
        plan = S.build_plan(sdir, state, sel)
        items = S.plan_items(plan, prompts or {})
        scorer = F.FakeScorer()
        scorer.allow = set(allow)
        with mock.patch.object(run_generate, "generate_one", F.fake_generate_one), mock.patch.object(S, "OnlineScorer", lambda: scorer):
            S.run_round(sdir, state, keep=plan["keep"], new_items=items, comfy="", selection=sel)
        return S.load_state(sdir)

    def prompts_for(self, sdir, sel):
        plan = S.build_plan(sdir, S.load_state(sdir), sel)
        out = {}
        for r in plan["requests"]:
            if r["needs_ai"]:
                k = r["key"][-1]
                ph = [p.strip() for p in r["base_prompt"].split(",")]
                out[r["key"]] = {"title": f"合体方針 {k}", "reason": f"理由 {k}", "text": ", ".join(ph[:2] + [f"(big {k}:1.3)"] + ph[2:7] + [f"s{k}", f"l{k}", "no text"])}
        return out

    def test_kept_stay_kept_derived_are_ungated_and_hidden(self):
        sdir = self.session()
        sel = self.select(sdir, ["p-01", "p-02"], {"p-01": "円を大きく"})
        st = self.run_regen(sdir, sel, self.prompts_for(sdir, sel), allow={"p-05"})  # p-06 は足切りで落ちる。派生は足切りしない
        self.assertEqual(st["origin"]["p-01"]["kind"], "kept")
        self.assertEqual(st["origin"]["p-02"]["kind"], "kept")
        kids = [c for c, o in st["origin"].items() if o.get("kind") == "derived"]
        self.assertEqual(len(kids), 3)  # 足切りなしで 3 件
        self.assertTrue(all(st["origin"][c]["parent"] == "p-01" for c in kids))
        self.assertEqual(S.top_count(st["cards"], st["origin"]), 3)  # p-01, p-02, p-05（派生は数えない）
        self.assertIn("p-05", st["cards"])
        self.assertNotIn("p-06", st["cards"])
        spec = {S.card_id(i["id"]): i for i in S.spec_items(S.load_spec(sdir))}
        self.assertEqual(spec[kids[0]]["card_note"], "円を大きく")
        self.assertEqual(spec[kids[0]]["reason"], "理由 1")
        self.assertEqual(st["shortfall"], 1)  # size 4 に 1 件足りない。AI は呼ばれない

    def test_regen_with_empty_reserve_keeps_selection_and_reports_shortfall(self):
        sdir = self.session(n_ideas=4)
        sel = self.select(sdir, ["p-02"])
        st = self.run_regen(sdir, sel)
        self.assertEqual(st["cards"], ["p-02"])
        self.assertEqual(st["shortfall"], 3)
        self.assertFalse((sdir / "images" / "p-01.png").exists())  # 選ばなかったカードは捨てられる

    def test_unselected_card_with_note_is_discarded(self):
        sdir = self.session(n_ideas=4)
        sel = self.select(sdir, ["p-03"], {"p-02": "捨てられる方向"})
        st = self.run_regen(sdir, sel)
        self.assertEqual(st["cards"], ["p-03"])
        self.assertFalse((sdir / "cards" / "p-02.webp").exists())


class ApiAndServer(Base):
    def test_card_reason_and_fallback(self):
        sdir = self.session()
        cards = {c["id"]: c for c in SV.api_state(sdir)["cards"]}
        self.assertEqual(cards["p-01"]["reason"], "アイデア 1 の理由（テスト用）")
        self.assertEqual(cards["p-02"]["reason"], "")  # 理由なし
        items = {"p-01": {"direction": "元の方針"}}
        self.assertIn("円を大きく", SV.card_reason({"parent": "p-01", "card_note": "円を大きく"}, items))

    def test_http_selection_flow(self):
        sdir = self.session()
        started = []
        with mock.patch.object(SV, "start_job", lambda d, sel: started.append(sel)):
            server = ThreadingHTTPServer(("127.0.0.1", 0), SV.Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            base = f"http://127.0.0.1:{server.server_address[1]}/{sdir.name}"

            def post(path, body):
                req = urllib.request.Request(f"{base}{path}", json.dumps(body).encode(), {"Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(req) as r:
                        return r.status, json.loads(r.read())
                except urllib.error.HTTPError as e:
                    return e.code, json.loads(e.read())

            with urllib.request.urlopen(f"{base}/api/state") as r:
                state = json.loads(r.read())
            self.assertEqual(state["phase"], "ready")
            self.assertNotIn("prompt", json.dumps(state))  # プロンプトは配らない
            code, _ = post("/api/selection", {"round": 1, "keep": ["p-01"], "notes": {"p-01": "a", "p-02": "b"}, "note": "", "action": "regen", "submitted": True})
            self.assertEqual(code, 200)
            saved = json.loads((sdir / "selection.json").read_text(encoding="utf-8"))
            self.assertEqual((saved["keep"], saved["notes"]), (["p-01"], {"p-01": "a"}))
            self.assertEqual(len(started), 1)
            self.assertEqual(post("/api/selection", {"round": 9, "keep": [], "notes": {}, "note": "", "action": None, "submitted": False})[0], 409)  # 古い画面


if __name__ == "__main__":
    unittest.main()
