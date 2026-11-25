#!/usr/bin/env python3
"""session の候補をカードで見せて、選んだ結果を sessions/<id>/selection.json に書くサーバー。標準ライブラリのみ。

    uv run tools/serve_session.py                         # http://127.0.0.1:8766/（この PC のブラウザだけ）
    uv run tools/serve_session.py --host tailscale        # Tailscale の IP に bind する（スマホから開く用）
    uv run tools/serve_session.py --host 100.64.0.1       # IP を直接指定してもよい
    uv run tools/serve_session.py --port 9000

起動すると、開く URL を表示する。session ごとのページは http://<host>:<port>/<session-id>/。
AI は、この URL をユーザーに返せばよい。ユーザーがページでカードを選び（枠をタップ）、必要なら全体の方針と、カードごとの方向を書いて、次を押す。
  - 「選んだものを残して再生成」: 選んだカードだけを残して、予備のアイデアで size 件に埋める。選んでいないカードは、方向が入っていても捨てる。予備が尽きても、AI には頼まない（足りない件数を出す）
  - 「足りない分を補う」: 予備のアイデアを使い、尽きたら AI に新しいアイデアを依頼する（人が押したときだけ）
  - 「選んだもので決定・微調整へ」: 選んだカードで決定して、次の段階へ進む（微調整の画面は未実装）
再生成と補充は、サーバーが tools/session.py を起動して行う（この PC の中だけで動く）。
AI は、個別の派生 prompt と、全体の方針の反映と、「足りない分を補う」で頼む新しいアイデアを書く。呼び方はツールに固定しない:
  - 環境変数 CIGAR_COMPOSER_CMD に「依頼文を標準入力 → 返答を標準出力」のコマンドを入れると、サーバーが呼ぶ。依頼と返答は sessions/<id>/compose_logs/ に残る。
    ファイルの編集やコマンドの実行をさせない設定で呼ぶこと（ページの入力が依頼文に入るため）。
  - 未設定なら、ページに依頼文が出る。コピーして、使っている AI に貼り、返ってきた JSON をページに貼る。
カード内の「プレビュー」は、箱に貼った見た目で確かめる（サイトの拡大表示と同じ描画。中に拡大表示がある）。
派生（個別の方向から作った案）は、元のカードの「派生」ボタンから見る。

配るもの・書くもの:
  - GET  /                          session の一覧
  - GET  /<id>/                     カードのページ（tools/session_page.html）
  - GET  /<id>/api/state            カードの状態と、実行中の処理（スコア・seed・プロンプトは含まない。AI への依頼文は、返答待ちのときだけ含む）
  - GET  /<id>/img/<カード id>.webp  cards/ の画像
  - GET  /_assets/boxview.js        箱の描画（site/boxview.js。サイトと共有）
  - POST /<id>/api/selection        選択（selection.json）を書く。再生成・補充のボタンなら、処理を始める
  - POST /<id>/api/compose          AI の返答（JSON）を受け取って、処理を進める（返答待ちのときだけ）。元のプロンプトの語句が残っていないと差し戻す
  - POST /<id>/api/cancel           返答待ち・エラーの処理を取り消す
書くのは、selection.json、job.json、compose_result.json だけ。プロンプト・seed・スコアは配らない。

認証はない。届く範囲は bind するアドレスで決まる。公開リポジトリなので、誰でも届く状態にしないこと:
  - 既定の 127.0.0.1 は、この PC だけ
  - tailscale は、自分の Tailnet の端末だけ
  - 0.0.0.0 は、同じネットワークの全員に届く（--allow-any を付けたときだけ許可）
POST は Content-Type: application/json のみ受け付け、他のサイトのページからの書き込み（CSRF）を防ぐ。
ログは /tmp/cigar-session.log に書く（端末が閉じても止まらないように、標準出力には出さない）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE = Path(__file__).resolve().parent / "session_page.html"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import session as S  # noqa: E402  プランの作成（重い処理は関数の中で読み込まれる）

SESSIONS = S.SESSIONS

LOG = Path("/tmp/cigar-session.log")
SESSION_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[A-Za-z0-9._-]+$")
CARD_ID = re.compile(r"^p-[0-9]+$")
ACTIONS = ("regen", "add", "finalize")
RUN_LOG = Path("/tmp/cigar-session-run.log")
JOB_LOCK = threading.Lock()
BOXVIEW = REPO_ROOT / "site" / "boxview.js"
MAX_BODY = 64 * 1024
MAX_TOTAL_NOTE = 1500
MAX_CARD_NOTE = 600
MAX_COMPOSE = 32 * 1024


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def session_dir(sid: str) -> Path | None:
    if not SESSION_ID.match(sid):
        return None
    d = SESSIONS / sid
    return d if (d / "state.json").exists() else None


def card_reason(it: dict, spec_items: dict) -> str:
    """カードの「説明」（このアイデアを採用した理由）。派生で理由がなければ、元の方針と方向から作る。"""
    if it.get("reason"):
        return it["reason"]
    if it.get("parent") and it.get("card_note"):
        base = spec_items.get(it["parent"], {}).get("direction", "")
        return f"「{base}」の案に、「{it['card_note']}」という方向を反映した派生です。"
    return ""


def card_info(sdir: Path, state: dict, spec_items: dict) -> list[dict]:
    """ページに出すカード。生成中は、残したカードと、できた順の新しいカード。"""
    ids = state.get("live", []) if state["phase"] == "generating" else state["cards"]
    out = []
    for cid in ids:
        it = spec_items.get(cid, {})
        out.append(
            {
                "id": cid,
                "no": cid.rsplit("-", 1)[1],
                "label": it.get("label", ""),
                "direction": it.get("direction", ""),
                "reason": card_reason(it, spec_items),
                "origin": state.get("origin", {}).get(cid, {}),
                "parent": state.get("origin", {}).get(cid, {}).get("parent") if state.get("origin", {}).get(cid, {}).get("kind") == "derived" else None,
                "has_image": (sdir / "cards" / f"{cid}.webp").exists(),
            }
        )
    return [c for c in out if c["has_image"]]


def read_job(sdir: Path) -> dict | None:
    f = sdir / "job.json"
    try:
        return read_json(f) if f.exists() else None
    except (OSError, ValueError):
        return None


def set_job(sdir: Path, **job) -> None:
    write_json(sdir / "job.json", job)


def clear_job(sdir: Path) -> None:
    (sdir / "job.json").unlink(missing_ok=True)


def api_state(sdir: Path) -> dict:
    state = read_json(sdir / "state.json")
    job = read_job(sdir)
    phase = state["phase"]
    if job:
        if job["status"] in ("composing", "awaiting"):
            phase = job["status"]
        elif job["status"] == "running" and phase == "ready":
            phase = "generating"  # session.py が段階を書くまでの間
        elif job["status"] == "error":
            phase = "job_error"
    spec = read_json(sdir / "spec.json")
    items = {f"p-{it['id']}": it for it in spec["conditions"][0]["items"]}
    sel_file = sdir / "selection.json"
    return {
        "id": sdir.name,
        "title": spec.get("brief", ""),
        "concept": spec.get("concept", ""),
        "phase": phase,
        "error": (job or {}).get("error", "") if phase == "job_error" else state.get("error", ""),
        "job": None if not job else {"status": job["status"], "mode": job.get("mode"), "text": job.get("text", "") if job["status"] == "awaiting" else ""},
        "progress": state.get("progress", {}),
        "round": state["round"],
        "size": state["size"],
        "shortfall": state.get("shortfall", 0),
        "selection": read_json(sel_file) if sel_file.exists() else None,
        "cards": card_info(sdir, state, items),
    }


def validate_selection(body: dict, state: dict) -> dict:
    """ページから届いた選択を検査して、書く形にする。不正なら ValueError。"""
    if body.get("round") != state["round"]:
        raise ValueError("stale")
    cards = set(state["cards"])
    keep = body.get("keep", [])
    if not isinstance(keep, list) or any(not isinstance(c, str) or c not in cards for c in keep):
        raise ValueError("いまのカードにない画像です")
    if len(set(keep)) != len(keep):
        raise ValueError("同じ画像が重なっています")
    raw_notes = body.get("notes", {})
    if not isinstance(raw_notes, dict):
        raise ValueError("カードの方向が不正です")
    notes: dict[str, str] = {}
    for cid, text in raw_notes.items():
        if cid not in cards or not isinstance(text, str):
            raise ValueError("いまのカードにない画像の方向です")
        if len(text) > MAX_CARD_NOTE:
            raise ValueError("カードの方向が長すぎます")
        if text.strip() and cid in keep:  # 選んでいないカードの方向は捨てる（選ばなければ、カードごと捨てられる）
            notes[cid] = text.strip()
    note = body.get("note", "")
    if not isinstance(note, str) or len(note) > MAX_TOTAL_NOTE:
        raise ValueError("全体の方針が長すぎます")
    action = body.get("action")
    if action is not None and action not in ACTIONS:
        raise ValueError("操作が不正です")
    if action == "finalize" and not keep:
        raise ValueError("決定するカードを選んでください")
    if action == "add" and state.get("shortfall", 0) <= 0:
        raise ValueError("足りない件数がありません")
    return {
        "round": state["round"],
        "keep": keep,
        "notes": notes,
        "note": note.strip(),
        "action": action,
        "submitted": bool(body.get("submitted")),
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


# ---- 再生成・補充の処理（session.py を起動する。メモがあるときだけ、AI の返答を挟む）--------------------


def spawn_session(sdir: Path, mode: str, prompts: Path | None = None) -> None:
    """session.py を起動して、終わるまで見張る。mode は regen / add。"""
    cmd = ["uv", "run", "tools/session.py", mode, str(sdir), "--auto"] + (["--prompts", str(prompts)] if prompts else [])
    set_job(sdir, status="running", mode=mode)
    log = RUN_LOG.open("ab")
    proc = subprocess.Popen(cmd, cwd=REPO_ROOT, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)

    def watch() -> None:
        rc = proc.wait()
        log.close()
        try:
            state = read_json(sdir / "state.json")
            if rc != 0 and state["phase"] != "error":  # session.py が段階を書く前に止まった（入力の不備など）
                set_job(sdir, status="error", mode=mode, error=f"処理を始められませんでした（ログ: {RUN_LOG}）")
            else:
                clear_job(sdir)
        except (OSError, ValueError):
            clear_job(sdir)

    threading.Thread(target=watch, daemon=True).start()


def start_job(sdir: Path, sel: dict) -> None:
    """選択（regen / add）から、処理を始める。別スレッドで動かす。"""

    def work() -> None:
        try:
            state = read_json(sdir / "state.json")
            mode = "add" if sel["action"] == "add" else "regen"
            plan = S.build_plan(sdir, state, sel, mode=mode)
            if not plan["requests"] and (mode == "add" or not plan["keep"]):
                set_job(sdir, status="error", mode=mode, error="作る候補がありません（空き枠がないか、残すカードがありません）")
            elif not plan["needs_ai"]:
                spawn_session(sdir, mode)
            elif S.composer_available():
                set_job(sdir, status="composing", mode=mode)
                prompts = S.compose(sdir, plan)  # 差し戻されたら、理由を添えて 1 回だけ頼み直す。依頼と返答は compose_logs/ に残る
                start_generation(sdir, mode, prompts)
            else:
                set_job(sdir, status="awaiting", mode=mode, text=S.compose_text(plan))
        except Exception as e:  # noqa: BLE001  ページに理由を出す
            set_job(sdir, status="error", mode=sel.get("action"), error=f"{type(e).__name__}: {e}")

    with JOB_LOCK:
        if read_job(sdir):
            return
        set_job(sdir, status="composing" if S.composer_available() else "running", mode=sel["action"])
    threading.Thread(target=work, daemon=True).start()


def start_generation(sdir: Path, mode: str, prompts: dict) -> None:
    """検査を通ったプロンプトを compose_result.json に書き、生成を始める。"""
    out = sdir / "compose_result.json"
    write_json_list(out, [{"key": k, "title": v["title"], "reason": v.get("reason", ""), "text": v["text"]} for k, v in prompts.items()])
    spawn_session(sdir, mode, out)


def finish_compose(sdir: Path, plan: dict, mode: str, output: str) -> None:
    """貼り付けで届いた AI の返答を検査して、処理を始める。不正なら ValueError。"""
    S.log_compose(sdir, datetime.now().strftime("%H%M%S"), "pasted-response", output)
    start_generation(sdir, mode, S.parse_compose_result(output, plan))


def write_json_list(path: Path, data: list) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class Handler(BaseHTTPRequestHandler):
    server_version = "cigar-session"

    def log_message(self, fmt, *args):
        try:
            with LOG.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%H:%M:%S} {self.address_string()} {fmt % args}\n")
        except OSError:
            pass

    def send_bytes(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, data: dict) -> None:
        self.send_bytes(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def not_found(self) -> None:
        self.send_bytes(404, "見つかりません".encode("utf-8"), "text/plain; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        try:
            if path == "/":
                return self.index()
            if path == "/_assets/boxview.js":
                return self.send_bytes(200, BOXVIEW.read_bytes(), "text/javascript; charset=utf-8")
            parts = path.strip("/").split("/")
            sdir = session_dir(parts[0])
            if not sdir:
                return self.not_found()
            if len(parts) == 1 and path.endswith("/"):
                return self.send_bytes(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            if len(parts) == 1:  # 末尾の / がないときは付ける
                return self.send_bytes(301, b"", "text/plain", {"Location": f"/{parts[0]}/"})
            if parts[1:] == ["api", "state"]:
                return self.send_json(200, api_state(sdir))
            if len(parts) == 3 and parts[1] == "img" and parts[2].endswith(".webp"):
                cid = parts[2][: -len(".webp")]
                f = sdir / "cards" / f"{cid}.webp"
                if CARD_ID.match(cid) and f.exists():
                    return self.send_bytes(200, f.read_bytes(), "image/webp", {"Cache-Control": "private, max-age=86400"})
            return self.not_found()
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_POST(self) -> None:  # noqa: N802
        parts = self.path.split("?", 1)[0].strip("/").split("/")
        sdir = session_dir(parts[0]) if parts else None
        if not sdir or len(parts) != 3 or parts[1] != "api" or parts[2] not in ("selection", "compose", "cancel"):
            return self.not_found()
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self.send_json(415, {"error": "Content-Type は application/json にしてください"})
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > (MAX_COMPOSE if parts[2] == "compose" else MAX_BODY):
            return self.send_json(413, {"error": "本文の大きさが不正です"})
        try:
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("本文が不正です")
            return getattr(self, "post_" + parts[2])(sdir, body)
        except ValueError as e:
            code = "stale" if str(e) == "stale" else "invalid"
            msg = "候補が更新されました。ページを読み込み直してください" if code == "stale" else str(e)
            return self.send_json(409 if code == "stale" else 400, {"error": msg, "code": code})

    def post_selection(self, sdir: Path, body: dict) -> None:
        state = read_json(sdir / "state.json")
        if state["phase"] != "ready" or read_job(sdir):
            return self.send_json(409, {"error": "処理中です。終わってから選んでください", "code": "busy"})
        sel = validate_selection(body, state)
        write_json(sdir / "selection.json", sel)
        if sel["submitted"] and sel["action"] in ("regen", "add"):
            start_job(sdir, sel)
        self.send_json(200, {"ok": True, "submitted": sel["submitted"]})

    def post_compose(self, sdir: Path, body: dict) -> None:
        job = read_job(sdir)
        if not job or job["status"] != "awaiting":
            return self.send_json(409, {"error": "返答を待っている処理がありません", "code": "busy"})
        text = body.get("result")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("返答が空です")
        state = read_json(sdir / "state.json")
        sel = S.read_selection(sdir)
        if not sel:
            raise ValueError("選択がありません")
        mode = job["mode"] if job.get("mode") in ("regen", "add") else "regen"
        plan = S.build_plan(sdir, state, sel, mode=mode)
        finish_compose(sdir, plan, mode, text)  # 不正なら ValueError（ページに理由が出る）
        self.send_json(200, {"ok": True})

    def post_cancel(self, sdir: Path, body: dict) -> None:
        job = read_job(sdir)
        if job and job["status"] in ("awaiting", "error"):
            clear_job(sdir)
        self.send_json(200, {"ok": True})

    def index(self) -> None:
        rows = []
        for d in sorted((p for p in SESSIONS.glob("*") if session_dir(p.name)), reverse=True):
            try:
                st, spec = read_json(d / "state.json"), read_json(d / "spec.json")
            except (OSError, ValueError):
                continue
            title = (spec.get("brief", "") or d.name).replace("<", "&lt;")
            rows.append(f'<li><a href="/{d.name}/">{title}</a><small> 第{st["round"]}案 / {st["phase"]}</small></li>')
        body = (
            '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>session</title><style>body{font:16px system-ui;background:#0f1115;color:#e8eaed;padding:20px}"
            "a{color:#8ab4f8}li{margin:12px 0}small{color:#9aa0a6;margin-left:8px}</style>"
            f"<h1>session</h1><ul>{''.join(rows) or '<li>session がありません</li>'}</ul>"
        )
        self.send_bytes(200, body.encode("utf-8"), "text/html; charset=utf-8")


def tailscale_info() -> tuple[str | None, str | None]:
    """（IPv4, MagicDNS 名）。Tailscale の CLI が見つからなければ (None, None)。"""
    exe = shutil.which("tailscale") or "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    if not Path(exe).exists():
        return None, None
    try:
        ip = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=10).stdout.split()[0]
    except (OSError, IndexError, subprocess.SubprocessError):
        return None, None
    dns = None
    try:
        st = json.loads(subprocess.run([exe, "status", "--json"], capture_output=True, text=True, timeout=10).stdout)
        dns = (st.get("Self", {}).get("DNSName") or "").rstrip(".") or None
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return ip, dns


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1", help="bind するアドレス。tailscale なら Tailscale の IP")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--allow-any", action="store_true", help="0.0.0.0 を許可する（同じネットワークの全員に届く）")
    args = ap.parse_args()

    shown = args.host
    if args.host == "tailscale":
        ip, dns = tailscale_info()
        if not ip:
            print("Tailscale の IP を取得できません。--host に IP を直接指定してください", file=sys.stderr)
            return 1
        args.host, shown = ip, dns or ip
    elif args.host in ("0.0.0.0", "::") and not args.allow_any:
        print("0.0.0.0 は同じネットワークの全員に届きます。意図するなら --allow-any を付けてください", file=sys.stderr)
        return 1

    SESSIONS.mkdir(exist_ok=True)
    for d in SESSIONS.glob("*"):  # 前回の処理の記録は、引き継がない（生成が続いていれば、state.json の段階に出る）
        if session_dir(d.name):
            clear_job(d)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    base = f"http://{shown}:{args.port}"
    print(f"session のページ: {base}/<session-id>/（一覧: {base}/）", flush=True)
    latest = sorted((p.name for p in SESSIONS.glob("*") if session_dir(p.name)), reverse=True)
    if latest:
        print(f"最新: {base}/{latest[0]}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
