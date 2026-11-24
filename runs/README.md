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
open runs/<run-id>/report.html
```

## spec.json

- `conditions[].prompt_prefix / prompt_suffix / negative_prompt` が条件ごとの差。好み・ガードの文はここに入れる。
- `items[]` は条件をまたいで同じ `id` と `seed` にそろえる。条件間の差が、プロンプトの差だけになる。
- 最終プロンプトは `prefix, text, suffix` をカンマでつないだもの。
- 発散（`text` を考える段階）では `docs/style-spec.md` を渡さない。好み・ガードの反映は生成プロンプトに変換する段階で行う。

## 人間レビュー

レポート上で、機械の判定（枠の色）に**同意しない画像だけ**クリックして印を付ける。通過なのに NG のものと、不通過なのに OK のものの両方。明確なものだけでよい。

- 条件（モデルや型）が複数ある run は、画面の下に条件ごとのブロックが続く。**条件ごとの「この条件を最後まで見た」にチェック**する。チェックした条件だけが、人間 OK 率の集計に入る（見ていない条件を「全部同意」と数えないため）。
- 見終わったら `review.json` を書き出し、run のディレクトリに置く。印のない画像は、確認済みの条件の中でだけ「機械に同意」として数える。
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

run は実験的な記録で、コミットするかは未定。`runs/<run>/` は `.git/info/exclude`（ローカル専用）で除外している。

- 同じ spec と seed でも、実行環境（MPS・CUDA・ComfyUI のバージョンなど）が違うと同じ画像にはならない。`review.json` は「その環境で生成した画像を見た結果」であり、別のマシンで再生成した画像には当てはまらない。

## 注意

- 分類器は LLM 側の生成画像で学習している。別のモデルで作った画像は分布がずれるので、通過率の絶対値より、同じ run 内の条件間の比較を見る。
- 1 条件 24 枚程度では、通過率の差が偶然のことがある。
