#!/usr/bin/env python3
"""runs/ をまとめて配信し、未検査の run を一覧するページを出す。標準ライブラリのみ。

    python3 tools/serve_runs.py                 # http://127.0.0.1:8765/ に一覧
    python3 tools/serve_runs.py --no-open       # ブラウザを開かない
    python3 tools/serve_runs.py --port 9000

一覧（/）は、開くたびに runs/ を読み直す。run の状態は次で決める。
  - 生成候補    scores.json がない（画像生成前、または生成が途中）
  - 未レビュー  review.json がない
  - 一部未確認  review.json はあるが、「最後まで見た」の条件が足りない
  - 確認済み    すべての条件にチェックがある
旧形式の review.json（reviewed: true だけ）は、条件が 1 つの run のときだけ確認済みとみなす。
report.html がない run は、開いたときに make_report.py で作る。

各 run のレポートの「review.json に保存」は、PUT /<run>/review.json で、その run のディレクトリに書く。
一覧の「選択した run を削除」は、確認ダイアログのあと POST /_delete で run を完全に削除する（Git 管理下の run は削除しない）。
それ以外のファイルには書き込まない。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import socket
import subprocess
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "runs"
RUN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

STATUS_ORDER = {"未レビュー": 0, "一部未確認": 1, "生成候補": 2, "確認済み": 3}
STATUS_COLOR = {"未レビュー": "#f85149", "一部未確認": "#f0b72f", "生成候補": "#8b949e", "確認済み": "#3fb950"}


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def run_info(run_dir: Path) -> dict:
    spec = read_json(run_dir / "spec.json") or {}
    scores = read_json(run_dir / "scores.json")
    review = read_json(run_dir / "review.json")
    conds = [c["name"] for c in spec.get("conditions", [])]

    reviewed: set[str] = set()
    if review:
        if "reviewed_conditions" in review:
            reviewed = set(review["reviewed_conditions"])
        elif review.get("reviewed") and len(conds) == 1:
            reviewed = set(conds)
    missing = [c for c in conds if c not in reviewed]

    if scores is None:
        status = "生成候補"
    elif review is None:
        status = "未レビュー"
    elif missing:
        status = "一部未確認"
    else:
        status = "確認済み"

    n_images = len(list((run_dir / "images").glob("*.png"))) if (run_dir / "images").is_dir() else 0
    pass_rate = human_ok = None
    if scores:
        items = scores["items"]
        if items:
            pass_rate = sum(1 for i in items if i["pass"]) / len(items)
        flags = set((review or {}).get("flags", []))
        seen = [i for i in items if i["condition"] in reviewed]
        if seen:
            human_ok = sum(1 for i in seen if i["pass"] != (i["id"] in flags)) / len(seen)
    return {
        "name": run_dir.name,
        "concept": spec.get("concept", ""),
        "conditions": conds,
        "missing": missing,
        "status": status,
        "n_images": n_images,
        "flags": len((review or {}).get("flags", [])),
        "pass_rate": pass_rate,
        "human_ok": human_ok,
        "has_report": (run_dir / "report.html").exists(),
    }


def list_runs() -> list[dict]:
    runs = [run_info(d) for d in RUNS_DIR.iterdir() if d.is_dir() and (d / "spec.json").exists()]
    runs.sort(key=lambda r: r["name"], reverse=True)
    runs.sort(key=lambda r: STATUS_ORDER[r["status"]])
    return runs


def pct(x: float | None) -> str:
    return "-" if x is None else f"{x:.0%}"


TABS = [("todo", "未検査"), ("done", "検査済み"), ("unscored", "生成候補")]
TAB_STATUS = {"todo": ("未レビュー", "一部未確認"), "done": ("確認済み",), "unscored": ("生成候補",)}


def index_html(tab: str) -> str:
    runs = list_runs()
    count = {k: sum(1 for r in runs if r["status"] in TAB_STATUS[k]) for k, _ in TABS}
    if tab not in TAB_STATUS:
        tab = "todo"
    shown = [r for r in runs if r["status"] in TAB_STATUS[tab]]
    rows = []
    for r in shown:
        color = STATUS_COLOR[r["status"]]
        detail = ""
        if r["status"] == "一部未確認":
            detail = "未確認: " + "、".join(r["missing"])
        elif r["status"] == "未レビュー":
            detail = "review.json なし"
        name = html.escape(r["name"])
        link = f'<a href="/{name}/report.html">{name}</a>' if r["status"] != "生成候補" else name
        rows.append(
            f"<tr><td><input type='checkbox' class='pick' value='{name}'></td>"
            f"<td><span class='tag' style='background:{color}'>{r['status']}</span></td>"
            f"<td>{link}<div class='mute small'>{html.escape(r['concept'])}</div></td>"
            f"<td class='small'>{html.escape(detail)}</td>"
            f"<td class='num'>{len(r['conditions'])}</td><td class='num'>{r['n_images']}</td><td class='num'>{pct(r['pass_rate'])}</td>"
            f"<td class='num'>{pct(r['human_ok'])}</td><td class='num'>{r['flags']}</td></tr>"
        )
    body = "\n".join(rows) or "<tr><td colspan='9' class='mute'>この区分の run はありません</td></tr>"
    tabs = "".join(
        f'<a class="tab{" active" if k == tab else ""}" href="/?tab={k}">{label}<span class="cnt">{count[k]}</span></a>'
        for k, label in TABS
        if k != "unscored" or count[k] or tab == k
    )
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>runs 一覧</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; background:#0d1117; color:#e6edf3; font:14px/1.6 -apple-system,BlinkMacSystemFont,"Hiragino Sans",sans-serif; }}
  main {{ max-width:1100px; margin:0 auto; padding:24px 20px 80px; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  a {{ color:#79c0ff; text-decoration:none; }} a:hover {{ text-decoration:underline; }}
  .mute {{ color:#8b949e; }} .small {{ font-size:12px; }}
  .tabs {{ display:flex; gap:4px; margin-top:16px; border-bottom:1px solid #30363d; }}
  .tab {{ color:#8b949e; padding:6px 16px; border:1px solid transparent; border-bottom:none; border-radius:6px 6px 0 0; margin-bottom:-1px; }}
  .tab:hover {{ background:#21262d; text-decoration:none; }}
  .tab.active {{ color:#e6edf3; background:#0d1117; border-color:#30363d; border-bottom:1px solid #0d1117; font-weight:600; }}
  .tab .cnt {{ margin-left:8px; font-size:12px; background:#21262d; border-radius:10px; padding:0 8px; }}
  table {{ border-collapse:collapse; width:100%; margin-top:4px; }}
  th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid #30363d; vertical-align:top; }}
  th {{ color:#8b949e; font-weight:500; }} .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .tag {{ display:inline-block; color:#000; font-weight:700; font-size:12px; padding:1px 8px; border-radius:4px; white-space:nowrap; }}
  .tools {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:12px 0 4px; }}
  button {{ background:#21262d; color:#e6edf3; border:1px solid #30363d; border-radius:6px; padding:4px 10px; cursor:pointer; font:inherit; }}
  button:hover {{ background:#30363d; }} button.danger {{ border-color:#f85149; color:#ffa198; }}
  td:first-child, th:first-child {{ width:28px; padding-right:0; }}
</style></head><body><main>
<h1>runs 一覧</h1>
<div class="mute small">未レビュー = review.json なし。一部未確認 = 「最後まで見た」のチェックが足りない条件がある。このページは開くたびに読み直す。</div>
<div class="tabs">{tabs}</div>
<div class="tools">
  <button id="pick-all">表示中を全選択</button>
  <button id="pick-none">選択を外す</button>
  <button id="delete" class="danger">選択した run を削除</button>
  <span id="delete-status" class="mute small"></span>
</div>
<table>
<tr><th></th><th>状態</th><th>run</th><th>詳細</th><th class="num">条件</th><th class="num">枚数</th><th class="num">機械 通過率</th><th class="num">人間 OK 率</th><th class="num">印</th></tr>
{body}
</table></main>
<script>
const picks = () => [...document.querySelectorAll(".pick")];
const statusEl = document.querySelector("#delete-status");
const count = () => {{ statusEl.textContent = `${{picks().filter(x => x.checked).length}} 件を選択`; }};
document.querySelector("#pick-all").addEventListener("click", () => {{ picks().forEach(x => x.checked = true); count(); }});
document.querySelector("#pick-none").addEventListener("click", () => {{ picks().forEach(x => x.checked = false); statusEl.textContent = ""; }});
picks().forEach(x => x.addEventListener("change", count));
document.querySelector("#delete").addEventListener("click", async () => {{
  const runs = picks().filter(x => x.checked).map(x => x.value);
  if (!runs.length) {{ statusEl.textContent = "run が選ばれていません"; return; }}
  if (!confirm(`${{runs.length}} 件を完全に削除します。元に戻せません。続けますか？\\n\\n` + runs.slice(0, 12).join("\\n") + (runs.length > 12 ? "\\n…" : ""))) return;
  const res = await fetch("/_delete", {{ method: "POST", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify({{ runs }}) }});
  const data = await res.json();
  if (data.skipped.length) alert("削除しなかった run:\\n" + data.skipped.map(x => `${{x.run}}: ${{x.reason}}`).join("\\n"));
  location.reload();
}});
</script></body></html>
"""


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RUNS_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_body(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        path = unquote(url.path)
        if path in ("/", "/index.html"):
            tab = (parse_qs(url.query).get("tab") or ["todo"])[0]
            self.send_body(200, index_html(tab).encode("utf-8"), "text/html; charset=utf-8")
            return
        m = re.fullmatch(r"/([^/]+)/report\.html", path)
        if m and RUN_NAME.match(m.group(1)):
            run_dir = RUNS_DIR / m.group(1)
            if (run_dir / "scores.json").exists() and not (run_dir / "report.html").exists():
                subprocess.run([sys.executable, str(REPO_ROOT / "tools" / "make_report.py"), str(run_dir)], check=False)
        super().do_GET()

    def do_POST(self):
        if unquote(urlsplit(self.path).path) != "/_delete":
            self.send_body(404, b'{"ok":false}\n', "application/json")
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            self.send_body(413, b'{"ok":false}\n', "application/json")
            return
        try:
            names = json.loads(self.rfile.read(length))["runs"]
            if not isinstance(names, list) or not all(isinstance(x, str) for x in names):
                raise ValueError
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            self.send_body(400, b'{"ok":false}\n', "application/json")
            return
        deleted, skipped = [], []
        for name in dict.fromkeys(names):
            target = RUNS_DIR / name
            if not RUN_NAME.match(name) or not (target / "spec.json").exists():
                skipped.append({"run": name, "reason": "run が見つかりません"})
                continue
            tracked = subprocess.run(["git", "ls-files", "--error-unmatch", f"runs/{name}"], cwd=REPO_ROOT, capture_output=True)
            if tracked.returncode == 0:
                skipped.append({"run": name, "reason": "Git 管理下の見本 run です"})
                continue
            shutil.rmtree(target)
            deleted.append(name)
        body = json.dumps({"ok": True, "deleted": deleted, "skipped": skipped}, ensure_ascii=False).encode("utf-8")
        self.send_body(200, body, "application/json; charset=utf-8")

    def do_PUT(self):
        m = re.fullmatch(r"/([^/]+)/review\.json", unquote(urlsplit(self.path).path))
        if not m or not RUN_NAME.match(m.group(1)) or not (RUNS_DIR / m.group(1) / "spec.json").exists():
            self.send_body(404, b'{"ok":false}\n', "application/json")
            return
        run = m.group(1)
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            self.send_body(413, b'{"ok":false}\n', "application/json")
            return
        try:
            data = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self.send_body(400, b'{"ok":false}\n', "application/json")
            return
        if not isinstance(data, dict) or not isinstance(data.get("flags"), list) or data.get("run_id") != run:
            self.send_body(400, b'{"ok":false}\n', "application/json")
            return
        (RUNS_DIR / run / "review.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.send_body(200, b'{"ok":true}\n', "application/json")


def free_port(start: int) -> int:
    for port in range(start, start + 20):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    return 0


def serve(open_path: str = "/", port: int = 0, open_browser: bool = True) -> int:
    chosen = port or free_port(8765)
    if not chosen:
        print("127.0.0.1:8765 から 20 個のポートが埋まっています", file=sys.stderr)
        return 1
    server = ThreadingHTTPServer(("127.0.0.1", chosen), Handler)
    url = f"http://127.0.0.1:{chosen}{open_path}"
    print(f"→ {url}")
    print(f"保存ボタンは runs/<run>/review.json に書き込みます。止めるときは Ctrl+C")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=0, help="0 なら 8765 以降の空きを使う")
    ap.add_argument("--no-open", action="store_true", help="ブラウザを開かない")
    args = ap.parse_args()
    return serve("/", args.port, not args.no_open)


if __name__ == "__main__":
    sys.exit(main())
