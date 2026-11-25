# tests

実使用の flow（`tools/session.py` / `tools/serve_session.py` / `tools/session_page.html`）の動作確認。毎回、手でページを触って確かめなくて済むようにするためのもの。

```bash
uv run python -m unittest discover -s tests -v          # 自動テスト（数秒。ComfyUI・分類器・外部の AI は使わない）
uv run python tests/make_fixture_session.py /tmp/cigar-ui   # 画面確認用の session（合成画像だけ）を作る
CIGAR_SESSIONS_DIR=/tmp/cigar-ui uv run tools/serve_session.py --port 8767   # そのページを配信する
```

`CIGAR_SESSIONS_DIR` は、`sessions/` の代わりの出力先（テスト用）。`CIGAR_COMPOSER_CMD` は、AI を偽のコマンドに差し替える（テスト用。`tests/fixtures.py` の `FAKE_AI`）。実際の `sessions/` には触れない。

## 自動テストが確かめていること

| 項目 | 内容 |
| --- | --- |
| JSON の補正 | 末尾のカンマ・コメント・コードフェンス・閉じ忘れ・カンマ抜けを直す。直せないときは行を示す |
| 選択 | 個別の方向は、選んだカードだけが対象。選んでいないカードは、方向が入っていても、カードから外す |
| 計画 | 派生は 3 件。派生に全体の方針を使わない。regen では AI に新しいアイデアを頼まない（add のときだけ） |
| AI の返答の検査 | 重みなし / 元に近すぎ / 元から離れすぎ / 派生どうしが似すぎ を差し戻す。理由を添えて 1 回だけ頼み直す |
| 最初の生成 | 先頭 `size` 件を足切りなしですべてカードにする。残りは予備 |
| 1 ラウンド | 残したカードは「残した案」のまま。派生は 3 件、元のカードの中に隠れ、件数に数えない。空き枠は、予備を同じ数だけ使う。予備が尽きても、選んだカードは残り、足りない件数が出る。外したカードの画像は残る |
| API / サーバー | 状態に「説明」の理由が入る（派生は、理由がなければ元の方針と方向から作る）。プロンプトは配らない。古い画面の選択は拒否する |

## 結果の記録（`tests/results/`）

- `unit-<日付>.txt`: 自動テストの出力。
- `ui-*.png`: 画面の確認（合成画像の session）。初期表示 / 方向を書くと選ばれ「派生作成」が付く・選択を外すと方向ごとカードから外れる / 「説明」/ 派生 / 再生成のあと。
- `e2e-run-20261125.txt`、`e2e-regen-state.json`、`e2e-compose-result.json`、`e2e-compose-logs/`、`e2e-all-images.webp`: 実 ComfyUI + 偽の AI で、足切りなしの最初の生成（先頭 8 件がすべてカードになる）から、3 件を残す再生成（派生 3 件 + 予備 2 件、外したカードの画像も `images/` に残る）まで CLI で通した結果。画像は p-01〜p-13 のすべてが残っている。AI への依頼・返答の記録（`e2e-compose-logs/`）も同じ run のもの。

確認していないこと: 実際の AI コマンド（`CIGAR_COMPOSER_CMD`）の呼び出し、スマホ・Tailscale 経由の表示。
- `style-spec-trial-20261125.md`、`style-spec-trial-20261125/`: style-spec を見て、実際の依頼から session を 4 回（+ 語だけ変えた 2 回）作った結果。brief、自己評価（暫定）、分かったこと。一覧画像は実際の生成物なので、Git 管理外。
