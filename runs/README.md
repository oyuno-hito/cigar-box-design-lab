# runs

「コンセプト → 生成プロンプト → 画像 → 機械の採点 → 人間のレビュー」を 1 回流した記録です。条件（ガードの有無など）を並べて比べるための単位です。

```text
runs/<日時>-<名前>/
  spec.json      コンセプト、モデル・サンプラー、条件ごとのプロンプトと seed
  images/        生成画像と同名の .json
  scores.json    分類器の採点結果
  report.html    比較レポート（毎回作り直せる）
  review.json    人間レビューの結果
```

## 流し方

ComfyUI を起動した状態で実行する（既定は `http://127.0.0.1:8188`。起動方法は問わない）。分類器の採点は `.venv`（`tools/requirements.txt`）を有効化して実行する。

```bash
python3 tools/run_generate.py runs/<run-id>             # 生成（途中から再開できる。--limit 3 で動作確認）
python3 tools/score_run.py runs/<run-id>                # scorers/ の分類器で採点
python3 tools/make_report.py runs/<run-id>              # report.html を作る
python3 tools/serve_runs.py                             # runs/ の一覧を開く。未検査の run が上に出る。保存は各 run の review.json
```

## spec.json

- `brief_type`（`music` または `mood`）と `brief` は、プロンプト生成の入力になった曲名・世界観・ムード。`context_sources` は曲のPV・タイアップ・ジャンル・ダンスなど、方向性の根拠にした情報。`concept` は、入力ブリーフから変換した英語の核となる視覚コンセプト文。
- `conditions[].prompt_prefix / prompt_suffix / negative_prompt` が条件ごとの差。好み・ガードの文はここに入れる。
- `items[]` は条件をまたいで同じ `id` と `seed` にそろえる。条件間の差が、プロンプトの差だけになる。
- `items[]` には任意で `label`（そのプロンプトの狙い）と `direction`（主な視覚方向）を付けられる。`label` はレポートのカードに表示される。1 プロンプト 1 枚の評価では、条件を 1 つにして、項目ごとに `text` を全文のプロンプトにする（`/eval-prompts`）。
- 最終プロンプトは `prefix, text, suffix` をカンマでつないだもの。
- 発散（`text` を考える段階）では `docs/style-spec.md` を渡さない。好み・ガードの反映は生成プロンプトに変換する段階で行う。

## 人間レビュー

レポート上で、機械の判定（枠の色）に**同意しない画像だけ**クリックして印を付ける。通過なのに NG のものと、不通過なのに OK のものの両方。明確なものだけでよい。

- 条件（モデルや型）が複数ある run は、条件ごとの比較表の下にタブが並ぶ（タブには ✔ / 未、枚数、印の数が出る）。最初は、最初の未確認の条件が開く。**条件ごとの「この条件を最後まで見た」にチェック**する。チェックした条件だけが、人間 OK 率の集計に入る（見ていない条件を「全部同意」と数えないため）。
- 見終わったら「review.json に保存」を押す。`serve_runs.py` で開いたページなら、`report.html` と同じディレクトリに書き込まれる。一覧ページは、「未検査」（`review.json` がない = 未レビュー、条件の「最後まで見た」が足りない = 一部未確認）と「検査済み」のタブに分かれる。印のない画像は、確認済みの条件の中でだけ「機械に同意」として数える。
- 各カードの `好み`（残す / 保留 / 外す）と `一致`（強い / 部分 / 弱い）は、プルダウンではなくワンクリックのボタンで記録する。もう一度押すと未評価に戻る。`好み` はデザイン候補として残したいか、`一致` は共通の核とそのカードの `direction` が見えるかを表す。好み高・一致低は視覚的には面白いが題材から外れた発見、好み低・一致高は核は合っているが好みではない案として扱う。どちらも `review.json` の `ratings` に保存される。
- `好み` は複数のお題に共通する傾向を `docs/style-spec.md` に反映するために使う。`一致` は、その run のコンセプト文・方向分け・プロンプトのどこを直すか判断するために使う。どちらも発散中に画像を落とす足切りにはしない。
- 旧形式（`reviewed: true` だけ）の `review.json` は、条件が 1 つの run のときだけ有効。複数条件の run は、レポートを開き直して条件ごとにチェックし直す。

## 集計と補助ツール

```bash
python3 tools/summarize_runs.py                 # 全 run の条件ごとの一覧（機械の通過率、人間 OK 率（打率）、類似度）
python3 tools/compare_review.py runs/<run-id>   # 1 つの run で、スコアの並びが人間の判定と合うか（AUC、閾値、上位 N 枚の適合率）
.venv/bin/python tools/montage.py runs/<run-id> # 条件ごとのコンタクトシート（generator/temp/montage/）
```

- 類似度は、条件内の画像どうしの CLIP 類似度の平均。高いほど似た絵が並んでいる。
- プロンプトの調整サイクルは `/tune-prompts`（`.cursor/skills/tune-prompts/`）。結果は `docs/style-spec.md` に残す。

## Git での扱い

- `runs/<run>/` は、画像が大きく（1 run で 20〜40MB）、環境が違えば再現しないので、**通常は Git 管理外**（`.gitignore`）。
- ただし「どう作業したか」は残す価値があるので、**見本を 2 件だけ丸ごとコミット**している。spec・生成画像（容量のため 768x512 に縮小）・採点・人間のレビュー・レポートが入っている。
  - [20261124-204000-gap-09-scifi/](20261124-204000-gap-09-scifi/README.md): 1 つの題材を、LLM 側の画像と同じ指定で作って、品質ギャップを測った run。run の作り方と読み方は、まずこれを見る。
  - [20261124-234236-eval-prompts-idol-structured/](20261124-234236-eval-prompts-idol-structured/README.md): 曲の核を分解し、1 プロンプト 1 枚で 15 方向を試した `/eval-prompts` の run。`好み` と `一致` の評価（`review.json` の `ratings`）が入っている。
- 見本を差し替える・増やすときは、`.gitignore` の `!runs/…/` を足す。画像は 768x512 に縮小して入れる（`Image.resize((768, 512))`）。
- 同じ spec と seed でも、実行環境（MPS・CUDA・ComfyUI のバージョンなど）が違うと同じ画像にはならない。`review.json` は「その環境で生成した画像を見た結果」であり、別のマシンで再生成した画像には当てはまらない。

## 注意

- 分類器は LLM 側の生成画像で学習している。別のモデルで作った画像は分布がずれるので、通過率の絶対値より、同じ run 内の条件間の比較を見る。
- 1 条件 24 枚程度では、通過率の差が偶然のことがある。
