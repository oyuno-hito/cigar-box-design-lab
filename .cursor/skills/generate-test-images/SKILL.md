---
name: generate-test-images
description: ラベリング用のデザイン画像を、LLM の画像生成で 4列x6行のシートにまとめて作り、3:2 の 24 枚に切り出して generated/99_inbox に保存する。ラベリング用の画像を出力してほしい、inbox に画像を追加してほしい、テスト画像を作ってほしい、と頼まれたときに使う。
disable-model-invocation: true
---

# テスト画像生成（シート方式）

人間が `like` / `dislike` / `maybe` を付けるための画像を、`generated/99_inbox/` に大量に出す。
ComfyUI は使わず、LLM 側の画像生成（`GenerateImage`）で 1 回に 24 枚ぶんのシートを作り、`tools/split_grid.py` で切り出す。

## 守ること

- 発散のための生成なので、`docs/style-spec.md` は**読まない・渡さない**。使うのは、毎回作る「組み合わせ表」だけ。
- 抽象語（「おしゃれ」「モダン」）は使わず、具体的な色・形・様式・素材感で書く。
- 24 マスは互いに違う組み合わせにする（配色・形・様式・密度・線の太さをばらす）。
- 画像は 3:2。シートは `aspect_ratio: "1:1"` で、4 列 x 6 行にすると各マスがちょうど 3:2 になる。
- 画像を複製しない。出力先は `generated/99_inbox/` だけ。

## 手順

```text
- [ ] 1. 重複を避ける（既存の cell_description を確認）
- [ ] 2. 組み合わせ表（24 マス）を作る
- [ ] 3. シートを生成する
- [ ] 4. シートとメタデータを generated/999_sheet/ に置く
- [ ] 5. 切り出す
- [ ] 6. 確認する
```

### 1. 重複を避ける

`generated/*/*.json` の `cell_description` を軽く見て、すでに出した組み合わせと被らないようにする（完全一致を避ける程度でよい）。

### 2. 組み合わせ表を作る

1 マスを `配色 + 形・様式` の 1 行で書く。例:

```text
ultramarine blue + coral-red interlocking arcs
moss green + cream asanoha hemp-leaf geometric star pattern
black + red and white Bauhaus circles, squares and triangles
```

様式の幅を出す（和柄、Art Deco、Memphis、Bauhaus、William Morris、ミッドセンチュリー、ストライプ、水玉、市松、手描き風 など）。ユーザーが方向性を指定したときだけ、それを表に反映する。

#### 色と柄を切り分けるシート（比較用）

配色の好みが柄の評価に混ざる（交絡する）のを避けたいときは、1 シートを「柄 6 種 × 配色 4 種」にする。各行が同じ柄で、列ごとに配色を変える（行 = 柄、列 = 配色）。

- 配色 4 種は、落ち着いた配色 / 明るい配色 / 暗い配色 / 高コントラスト（強い補色）のように性格を変える。
- 柄は、既存の `0_like` から構造を選ぶ。あるいは `1_dislike` のうち、色以外（形・密度・線・反復）が理由のものを狙って選ぶ。
- 同じ柄が行内で同じ構造・密度になるよう、各マスの説明に構造の記述を共通で入れる。
- `cell_description` には「柄の名前 + 配色」を書き、行・列の対応が後から分かるようにする。

色以外の `dislike` を集めたいときは、色を絞った（例: 白黒＋1 色）シートで、形・密度・線の太さ・反復量を振る。

### 3. シートを生成する

`GenerateImage` を `aspect_ratio: "1:1"` で呼ぶ。説明文の骨子:

```text
A contact sheet with exactly 4 columns and 6 rows, 24 cells in total.
Every cell is a horizontal landscape rectangle with a 3:2 aspect ratio.
Cells are separated by thick pure white gutters of equal width, with a white outer margin.
No captions, no numbers, no text anywhere.
Each cell contains an independent flat graphic pattern filling the cell edge to edge,
screen-print look with solid colors, no mockup, no perspective.
Row 1: <マス1>; <マス2>; <マス3>; <マス4>. Row 2: ... Row 6: ...
```

- **白い溝が必須**。切り出しは溝の検出に頼る。
- 失敗（`Aborted` など）したら、説明文を短くして再試行する。1 枚だけ生成する方式には切り替えない。
- 出力は `~/.cursor/projects/.../assets/` に jpg で保存される。そのパスをそのまま使う。

### 4. 置く

```bash
mkdir -p generated/999_sheet
cp "<生成された jpg のパス>" generated/999_sheet/cigar-box-sheet-NN.jpg
```

`NN` は既存の `generated/999_sheet/` の連番に続ける。同じ場所に `cigar-box-sheet-NN.meta.json` を作る（`cells` は行優先で 24 個）:

```json
{
  "source": "cursor-generateimage（LLM 側の画像生成。モデル名は不明）",
  "prompt": "シート全体のプロンプト（組み合わせ表以外の共通部分）",
  "cells": ["r1c1 の説明", "r1c2 の説明", "..."]
}
```

`generated/999_sheet/` は元シートの置き場で、Git 管理外。分類の対象ではなく、学習にも使わない（`tools/check_generated.py` も検査しない）。

### 5. 切り出す

```bash
.venv/bin/python tools/split_grid.py generated/999_sheet/cigar-box-sheet-NN.jpg \
  --meta generated/999_sheet/cigar-box-sheet-NN.meta.json
```

- `.venv` がなければ作る: `python3 -m venv .venv && .venv/bin/pip install pillow numpy`
- 先に `--dry-run` を付けると、溝の検出結果だけ確認できる。
- 「溝の自動検出 = 失敗」と出たら等分で切られている。結果の画像にずれがないか確認し、ずれていれば `--white` や `--gutter-ratio` を調整するか、シートを作り直す。

### 6. 確認する

- `generated/99_inbox/` に PNG と JSON が各 24 個増えたか。
- 数枚を開いて、隣のマスの端が混ざっていないか、文字が入っていないか。
- 出力は `YYYYMMDD-HHMMSS-rXcY.png` と、同名の `.json`（`source` / `prompt` / `cell_description` のみ）。日時・サイズ・ラベルは JSON に書かない。

ユーザーへの報告は、枚数、出力先、組み合わせ表の方向性（どんな様式を入れたか）を短く書く。
