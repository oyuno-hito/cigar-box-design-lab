# site

GitHub Pages 用の HTML / JS の置き場です。依存するものはなく、ビルドは Python の標準ライブラリだけで動きます。

- 公開するのは `artifacts/` の画像だけ。プロンプト、スコア、好みの評価は載せない。
- `index.html` / `style.css` / `app.js` が本体。`artifacts/manifest.json` を読んで作る。
- 上部のテーマ名を選ぶと、そのテーマの画像だけが並ぶ（未選択はなし。初期値は manifest の先頭）。テーマが増えたら、並びが横にスクロールする。
- 各画像には題名（spec.json の `direction`）が付く。題名はそのプロンプトの狙いで、出力と合わないことがある。選定のときに確かめる。
- 画像をタップすると拡大表示（`<dialog>`）。題名とテーマ名が出る。左右のボタン・キー・スワイプで前後に動ける。URL は `#<テーマ>/<番号>` になり、スマホの戻る操作で閉じる。
- 拡大表示は、画像を箱に貼ったイメージで見せる。見せ方は 3 つ（初期値は「一箱」。選んだ側はブラウザに保存する）。一覧のカードは平面のまま。
  - 一箱: 1 つの箱を、面の中で時計回りに 90 度ずつ回した 4 枚（角度の表記はなし）。
  - 縦に並べる: 横長の箱を、長辺（180mm）どうしをくっつけて上に 3 つ積む。「全部同じ向き」と「真ん中の一つを 180 度逆に」の 2 つを左右に並べる。
  - 横に並べる: 横長の箱を、短辺（120mm）どうしをくっつけて横に 3 つ並べる。2 つの中身は上と同じ。
- 箱は、右の側面と上面が見える向きで描く（cigar-box-design-simulator の立体と同じ向き）。カメラから見える側面はいつも右と上で、箱を回すと、そこに見える面が入れ替わる（横長のとき右は左右の側面、縦長のとき右は上下の側面）。画像は、箱と一緒に回る。
- 箱の見た目は `artifacts/manifest.json` の `box` で決める。きぞはこ（180×120×60mm）。
  - `sideColorLR`: 左右の側面の色 / `sideColorTB`: 上下の側面の色 / `frame`: 枠線の有無（`true` / `false`）/ `frameColor`: 枠線の色。色は CSS の色（`#000000`、`white` など）。左右・上下は、箱を横長に置いたときの向き。
  - 全体の `box` を、テーマの `box`、画像の `box` の順に上書きする（書いたキーだけ変わる）。たとえば画像 1 枚だけ枠線なしにするなら、その画像の項目に `"box": { "frame": false }` を書く。
  - 枠線ありのときは、画像を内側に縮めて、余白を枠線の色にする。画像は切れない（箱の面と画像はどちらも 3:2）。
  - 色は、実際に手に入る素材の範囲で選ぶ。左右の側面（短辺）は d-c-fix ベロア（レッド / ダークレッド / ネイビー / グリーン / ブラック / グレー）、上下の側面（長辺）と枠線はアサヒペン パワーテープ 48mm（白 / 黒 / シルバー / 蛍光色など）を想定している。画面の色は近似で、実物とは違う。
  - 書かなかったキーと、読めない色は、`app.js` の `DEFAULT_BOX`（左右 黒 / 上下 白 / 枠線あり / 枠線 白）になる。
- プロンプトやモデルは載せない（閲覧者に価値が薄く、公開しない方針でもある）。

## 確認

```bash
python3 tools/build_site.py --serve     # _site/ を作って http://127.0.0.1:8000/ で開く
```

`_site/` は Git 管理外。`site/` を直したら、もう一度ビルドする。

アクセスログはターミナルではなく `/tmp/cigar-site.log` に追記する（ターミナルが閉じてもサーバーが応答を返し続けるように）。ポートが使用中で起動できないときは、古いサーバーを止めてから起動しなおす。

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN -t | xargs -r kill
```

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
