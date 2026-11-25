# 見本: `20261124-204000-gap-09-scifi`

1 回の実験で何をしたか、人間がどこに関わったかを、そのまま残した見本です。ほかの `runs/` は Git 管理外ですが、この 1 件だけ丸ごとコミットしています（理由と運用は [../README.md](../README.md)）。

## 目的

LLM 側（Cursor の `GenerateImage`）で作った探索セット「宇宙・SF・レトロフューチャー」と**同じセル指定**を、ComfyUI（DreamShaperXL Turbo-Lightning）で生成して、品質ギャップを見る。LLM 側の仕分けでは、このセットは 24 枚中 like 6 / dislike 12 / maybe 6（like 25%）。

## 流れ

| 段階 | 誰が | 何を | コマンド・成果物 |
| --- | --- | --- | --- |
| 1. 指定を作る | 私（エージェント）+ 人間の方針 | セットの指定文を SD 向けのタグ寄りに書き直し、セル指定の偶数番 12 件を使う。seed は 2000 + (番号 − 1) | `spec.json` |
| 2. 生成 | プログラム | ComfyUI の API で 12 枚 | `uv run tools/run_generate.py runs/20261124-204000-gap-09-scifi` → `images/` |
| 3. 機械の採点 | プログラム | 分類器（`scorers/`）で like らしさ p を付ける。足切りは p ≥ 0.2517 | `uv run tools/score_run.py …` → `scores.json` |
| 4. レポート | プログラム | スコア順のグリッド、条件別の表 | `uv run tools/make_report.py …` → `report.html` |
| 5. 人間のレビュー | **人間** | レポートを見て、機械の判定に**明確に同意できない画像だけ**クリック。最後まで見たらチェックして書き出す | `review.json` |
| 6. 突き合わせ | プログラム | 印のない画像は「同意」として人間の判定を導き、並びが合っているかを見る | `uv run tools/compare_review.py …` → `comparison.json` |
| 7. 所感と記録 | 人間 + 私 | 画像を見て気づいたことを、抽象的な軸に言い換えて `docs/style-spec.md` に残す | 下の「所感」、`docs/style-spec.md` |

## 結果

機械の通過 3 / 12、**人間 OK 1 / 12（8%）**。機械が通した 3 枚のうち 2 枚は人間が NG とした。スコアの並びは人間の判定とおおむね合っている（AUC 0.82）が、足切りを学習時の値のまま使うと通しすぎる。

| # | p | 機械 | 人間 | 印 | プロンプトの題材部分 |
| --- | --- | --- | --- | --- | --- |
| 17 | 0.814 | 通過 | NG | 印（機械に同意せず） | solar system mobile of varied planets suspended in a dark field, no labels |
| 03 | 0.801 | 通過 | NG | 印（機械に同意せず） | colorful ringed planet with sweeping orbital trails on black |
| 01 | 0.401 | 通過 | OK |  | deep navy star map with irregular thin constellation lines and tiny planets, no labels |
| 13 | 0.190 | 不通過 | NG |  | colorful planets and moons floating among soft vapor trails |
| 15 | 0.147 | 不通過 | NG |  | futuristic greenhouse dome on an alien moon with small plant silhouettes |
| 07 | 0.099 | 不通過 | NG |  | astronaut helmet silhouette filled with a star field, no face or text |
| 05 | 0.073 | 不通過 | NG |  | chrome retro-futurist flying saucer over a striped alien horizon, no text |
| 11 | 0.058 | 不通過 | NG |  | retro computer circuit board traces with glowing nodes, no letters |
| 21 | 0.043 | 不通過 | NG |  | sci-fi city skyline on another planet with neon towers and no signs |
| 09 | 0.022 | 不通過 | NG |  | cyberpunk neon tunnel made of glowing magenta and cyan light trails |
| 23 | 0.021 | 不通過 | NG |  | silver astronaut gloves holding a floating glowing orb, no person or text |
| 19 | 0.011 | 不通過 | NG |  | retro space capsule with round windows and bold panels |

## 人間の所感（レビューのあと、チャットで出たもの）

- 写実的な質感を出そうとすると微妙。**人物・手・建物**は特に違う（07 宇宙飛行士、19 宇宙船の内部、23 手袋と球体）。プロンプトには `flat graphic`、`no person`、`silhouette` と書いてあったが、モデルは写実側に倒れた。
- **影の質感**はマイナスに働くことが多い。
- 05（円盤の夕景）は、**色がごちゃごちゃしていてチカチカする**。高彩度の色が全面で同じ強さで光っている。

これらは `docs/style-spec.md` の「好みの記録」に、軸（面の処理、奥行き、具象度、色の階層、線・点の細かさ）として観察で残した。

## このディレクトリを読むときの注意

- `images/` は、容量のため **768x512 に縮小した PNG** です。生成時の原寸は 1152x768。`scores.json` は原寸の画像で採点した値で、縮小後の画像で再採点すると、わずかにずれます。
- 同じ `spec.json` と seed でも、実行環境（MPS・CUDA、ComfyUI のバージョン）が違うと、同じ画像にはなりません。再現できるのは**手順**であって、画像そのものではありません。
- `review.json` の印は「機械の判定に明確に同意しない」画像だけです。厳密な正解ラベルではないので、条件どうしの比較の目安として読みます。
