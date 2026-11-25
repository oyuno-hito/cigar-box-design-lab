# runs

「コンセプト → 生成プロンプト → 画像 → 機械の採点 → 人間のレビュー」を 1 回流した記録です。条件（ガードの有無など）を並べて比べるための単位です。

```text
runs/<日時>-<名前>/
  spec.json         コンセプト、モデル・サンプラー、条件ごとのプロンプトと seed             [Git 管理]
  images/*.json     生成画像と同名のメタデータ（プロンプト・seed・生成元）                    [Git 管理]
  images/*.png      生成画像（再生成できる）                                                  [管理外]
  scores.json       分類器の採点結果                                                          [Git 管理]
  review.json       人間レビューの結果                                                        [Git 管理]
  contact.webp      全画像の一覧（機械の判定・印つき。約 70〜450KB）                          [Git 管理]
  report.html       比較レポート（毎回作り直せる）                                            [管理外]
```

## 流し方

ComfyUI を起動した状態で実行する（既定は `http://127.0.0.1:8188`。起動は `generator/start_comfy.sh`）。ツールはすべて `uv run` で動かす（README の「開発環境」）。

```bash
uv run tools/run_generate.py runs/<run-id>             # 生成（途中から再開できる。--limit 3 で動作確認）
uv run tools/score_run.py runs/<run-id>                # scorers/ の分類器で採点
uv run tools/make_report.py runs/<run-id>              # report.html を作る
uv run tools/montage.py runs/<run-id> --contact        # contact.webp を作る（コミットする一覧画像。レビュー後に作り直す）
uv run tools/serve_runs.py                             # runs/ の一覧を開く。未検査の run が上に出る。保存は各 run の review.json
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
uv run tools/summarize_runs.py                 # 全 run の条件ごとの一覧（機械の通過率、人間 OK 率（打率）、類似度）
uv run tools/compare_review.py runs/<run-id>   # 1 つの run で、スコアの並びが人間の判定と合うか（AUC、閾値、上位 N 枚の適合率）
uv run tools/montage.py runs/<run-id>          # 条件ごとのコンタクトシート（generator/temp/montage/。Git 管理外の作業用）
```

- 類似度は、条件内の画像どうしの CLIP 類似度の平均。高いほど似た絵が並んでいる。
- プロンプトの調整サイクルは `/tune-prompts`（`.cursor/skills/tune-prompts/`）。結果は `docs/style-spec.md` に残す。

## Git での扱い

方針は「**テキストと一覧画像だけコミットし、画像本体（PNG）はコミットしない**」。目的は、複数の環境や時間が経ったあとでも、「どの題材に、どんなプロンプトで、何枚作り、どう判定・評価したか」を時系列で追えるようにすること。PNG は 1 run で 20〜40MB あり、足し続けるとリポジトリが膨らむため残さない。

| 置くもの | Git |
| --- | --- |
| `spec.json` / `scores.json` / `review.json` / `self_review.json` / `comparison.json` / `images/*.json` | 管理する（run 全体で数十〜数百 KB） |
| `contact.webp`（run ごとに 1 枚、全画像の一覧） | 管理する（約 70〜450KB。全 run で約 4.5MB） |
| `images/*.png`、`report.html` | 管理しない（`.gitignore`）。再生成できる |

- 別の環境で画像が要るときは、ComfyUI を起動して `uv run tools/run_generate.py runs/<run-id>`（PNG が無いものだけ作る）→ 必要なら `uv run tools/make_report.py runs/<run-id>`。1 枚あたり約 20 秒。
- 再現性: 同じ spec・seed・チェックポイント・サンプラーで、この Mac（Apple Silicon・MPS）では PNG のバイト列まで同じになることを確認している。**別のハードウェア（NVIDIA / CUDA など）や、torch・ComfyUI のバージョンが違う環境では同じにならないことがある**。`review.json` は「その環境で生成した画像を見た結果」であり、再生成した画像には厳密には当てはまらない。画像そのものの記録は `contact.webp` を見る。
- 新しい run を作ったら、レビューまで終えたあとに `uv run tools/montage.py runs/<run-id> --contact` で `contact.webp` を作り直す（印・好みの枠が入る）。
- 画像を置いてよいのは `generated/` `artifacts/` `site/` と `runs/*/contact.webp` だけ。それ以外の場所の画像（`runs/*/images/*.png` を `git add -f` した場合など）や、1MB を超えるファイルをコミットしようとすると、pre-commit（`tools/check_staged.py`）が止める。意図して入れるときだけ `ALLOW_STAGED=1 git commit`。
- 圧縮した画像でも残したいものは、`generated/`（ラベル付け）か `artifacts/`（公開用）に移す。`generated/` の PNG は、`scorers/` のマニフェストにハッシュで参照されていて、画像を変換すると分類器の入力が変わるため、WebP には変換しない。

### チュートリアル用の例外

手順の見本として、次の 2 件だけは**画像も含めて丸ごとコミット**している（上の方針の例外。今後増やさない）。spec・生成画像（容量のため 768x512 に縮小）・採点・人間のレビュー・レポートが入っている。run の作り方と読み方は、まず 1 件目を見る。

- [20261124-204000-gap-09-scifi/](20261124-204000-gap-09-scifi/README.md): 1 つの題材を、LLM 側の画像と同じ指定で作って、品質ギャップを測った run。
- [20261124-234236-eval-prompts-idol-structured/](20261124-234236-eval-prompts-idol-structured/README.md): 曲の核を分解し、1 プロンプト 1 枚で 15 方向を試した `/eval-prompts` の run。`好み` と `一致` の評価（`review.json` の `ratings`）が入っている。

この 2 件の `images/` と `report.html` は追跡済みなので、`.gitignore` の対象外のまま更新できる。`tools/check_staged.py` も、この 2 件の `images/` だけは止めない。

## 注意

- 分類器は LLM 側の生成画像で学習している。別のモデルで作った画像は分布がずれるので、通過率の絶対値より、同じ run 内の条件間の比較を見る。
- 1 条件 24 枚程度では、通過率の差が偶然のことがある。
