# artifacts

最終的に採用したデザインのコレクションです。GitHub Pages で公開する対象は、このディレクトリだけです。

- 公開するものだけを置く。
- `manifest.json`: テーマ名と、画像の並び・題名。サイトはこれだけを読む。`box` に、拡大表示で見せる箱の色・枠線の設定がある（書き方は [../site/README.md](../site/README.md)）。`tools/export_artifacts.py` は `box` を書き換えない。
- `<テーマID>/<番号>.webp` と `<番号>.thumb.webp`: 画像（768px）と一覧用（384px）。
- `<テーマID>/provenance.json`: 元の run と画像 ID。公開用の `_site/` にはコピーされない。プロンプトは書かない。

`tools/export_artifacts.py` で作る。手順は [../site/README.md](../site/README.md)。
