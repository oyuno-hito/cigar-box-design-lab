# style-spec を直すループ（2026-11-25）

流れ: 結果を見る → `docs/style-spec.md` を直す → コミット → 新しい brief を一から書いて 3 session × 6 枚を生成 → 色の集計（`tools/palette_stats.py`）と目視（自己評価・暫定）→ 次の修正へ。足切りなし。モデルは DreamShaper XL Turbo-Lightning。

画像の一覧（`*.webp`）は、実際の生成物なので Git 管理外。brief と集計は、`style-spec-loop-20261125/` にある。

## 出発点（直前の 6 session、48 枚）

`style-spec-trial-20261125.md` の t1〜t6。色の集計（`style-spec-trial-20261125/palette-t1-t6.txt`）:

- 赤紫が主な色の画像 96%、青緑が 94%。この 2 色の組み合わせが 79%。
- 原因は、参考画像（衣装）の色を、私が全アイデアにそのまま入れたこと。style-spec の `color` の句の案に、turquoise / magenta が例として入っていたことも、影響した可能性がある。

## 第 1 回の修正（色の偏り）

- 軸の語彙に「色の多様性（1 session の中）」を追加。
- 好みの記録に、参考画像の色は「色の枠」として使い、アイデアごとに地と主色・差し色の組を変える、を追加（観察）。
- `color` の句の案の色名を `<color A>` `<color B>` に変更。色名は例で、既定の配色ではないと明記。
- `design-workflow` の SKILL に、色の組を変えることと、`palette_stats.py` での確認を追加。
