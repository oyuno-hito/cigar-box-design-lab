# site

GitHub Pages 用の HTML / JS の置き場です。依存するものはなく、ビルドは Python の標準ライブラリだけで動きます。

- 公開するのは `artifacts/` の画像だけ。プロンプト、スコア、好みの評価は載せない。
- `index.html` / `style.css` / `app.js` が本体。`artifacts/manifest.json` を読んで作る。
- 上部のテーマ名を選ぶと、そのテーマの画像だけが並ぶ（未選択はなし。初期値は manifest の先頭）。テーマが増えたら、並びが横にスクロールする。
- 各画像には題名（spec.json の `direction`）が付く。題名はそのプロンプトの狙いで、出力と合わないことがある。選定のときに確かめる。
- 画像をタップすると拡大表示（`<dialog>`）。題名とテーマ名が出る。左右のボタン・キー・スワイプで前後に動ける。URL は `#<テーマ>/<番号>` になり、スマホの戻る操作で閉じる。
- プロンプトやモデルは載せない（閲覧者に価値が薄く、公開しない方針でもある）。

## 確認

```bash
python3 tools/build_site.py --serve     # _site/ を作って http://127.0.0.1:8000/ で開く
```

`_site/` は Git 管理外。`site/` を直したら、もう一度ビルドする。

## 画像を増やす・選びなおす

```bash
.venv/bin/python tools/export_artifacts.py runs/<run> --id <テーマID> --title '星野源『恋』' --kind song   # 新しいテーマ（全画像）
.venv/bin/python tools/export_artifacts.py runs/<run> --id <テーマID> --pick 01,03,07                      # 選びなおす
```

- `--kind` は `song`（曲を題材にしたもの）か `mood`（ムード）。曲名は題材の出典として載せ、ページ下部に「アーティストや作品とは関係ありません」と書いてある。
- 長辺 768 と 384（一覧用）の WebP にして `artifacts/<テーマID>/` に置く。`artifacts/manifest.json` に名前と、画像の並び・題名が入る。
- `artifacts/<テーマID>/provenance.json` に元の run と画像 ID を残す。公開用の `_site/` にはコピーしない（`tools/build_site.py` は `.webp` と `manifest.json` だけコピーする）。

## 公開

`.github/workflows/pages.yml` が、`main` への push（`site/`・`artifacts/`・`tools/build_site.py` の変更）で `python3 tools/build_site.py` を実行し、できた `_site/` だけを GitHub Pages にアップロードする。手動実行（workflow_dispatch）もできる。

初回だけ、リポジトリの Settings → Pages → Build and deployment の Source を「GitHub Actions」にする。公開 URL は `https://<owner>.github.io/<repo>/`。
