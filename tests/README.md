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
| 選択 | 個別の方向は、選んだカードだけが対象。選んでいないカードは、方向が入っていても捨てる |
| 計画 | 派生は 3 件。派生に全体の方針を使わない。regen では AI に新しいアイデアを頼まない（add のときだけ） |
| AI の返答の検査 | 重みなし / 元に近すぎ / 元から離れすぎ / 派生どうしが似すぎ を差し戻す。理由を添えて 1 回だけ頼み直す |
| 1 ラウンド | 残したカードは「残した案」のまま。派生は足切りなしで 3 件、元のカードの中に隠れ、件数に数えない。予備が尽きても、選んだカードは残り、足りない件数が出る |
| API / サーバー | 状態に「説明」の理由が入る（派生は、理由がなければ元の方針と方向から作る）。プロンプトは配らない。古い画面の選択は拒否する |

## 結果の記録（`tests/results/`）

- `unit-<日付>.txt`: 自動テストの出力。
- `ui-*.png`: 画面の確認（合成画像の session）。初期表示 / 方向を書くと選ばれ「派生作成」が付く・選択を外すと方向ごと捨てられる / 「説明」/ 派生 / 再生成のあと。
- `e2e-regen-state.json`、`e2e-compose-logs/`: 実 ComfyUI + 実際の分類器の足切り + 偽の AI で、ページのボタンから再生成まで通した結果と、AI への依頼・返答の記録（最初の返答を不正にして、差し戻しと再依頼が働くことも見ている）。

確認していないこと: 実際の AI コマンド（`CIGAR_COMPOSER_CMD`）の呼び出し、スマホ・Tailscale 経由の表示。
