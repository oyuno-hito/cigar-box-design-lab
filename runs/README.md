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

レポート上で、機械の判定（枠の色）に**同意しない画像だけ**クリックして印を付ける。通過なのに NG のものと、不通過なのに OK のものの両方。最後まで見たら「最後まで見た」にチェックして `review.json` を書き出し、run のディレクトリに置く。印のない画像は「同意」として数え、条件ごとの一致率と「人間 OK 率」をレポートに出す。

## Git での扱い

run は実験的な記録で、コミットするかは未定。`runs/<run>/` は `.git/info/exclude`（ローカル専用）で除外している。

- 同じ spec と seed でも、実行環境（MPS・CUDA・ComfyUI のバージョンなど）が違うと同じ画像にはならない。`review.json` は「その環境で生成した画像を見た結果」であり、別のマシンで再生成した画像には当てはまらない。

## 注意

- 分類器は LLM 側の生成画像で学習している。別のモデルで作った画像は分布がずれるので、通過率の絶対値より、同じ run 内の条件間の比較を見る。
- 1 条件 24 枚程度では、通過率の差が偶然のことがある。
