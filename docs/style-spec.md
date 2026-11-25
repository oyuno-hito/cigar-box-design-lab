# スタイル仕様書（生成プロンプトの設計）

好みを、生成プロンプトに反映できる形で記録する文書。`/tune-prompts`（`.cursor/skills/tune-prompts/`）が、実験の結果をもとに更新する。

## 使いどころ（重要）

- **探索（発散）には渡さない。** 題材やアイデアを広げる段階（`docs/exploration-sets.md` のセット作りなど）では読まない・渡さない。
- 渡すのは、**題材が決まったあとに「生成プロンプトへ変換する段階」だけ。** コンセプト（曲・題材）は変えず、描き方だけをここに従って調整する。
- 好みの「様式名」（例: 浮世絵風、ヴィンテージ風）は書かない。様式名は題材側に属する。ここに書くのは、題材を取り除いても意味が通る**抽象的な性質**（軸）だけ。

## プロンプトの構造

```text
[concept]    題材・文脈。変えない。（例: Future Bass の曲、都市・建築）
[rendering]  描き方。下の軸で指定する。肯定形の短い句で書く。
[guard]      避けたい性質を、反対側の性質を肯定する句に言い換えたもの。
[negative]   補助。モデルと設定によっては、ほとんど効かない（下の「モデルのメモ」）。
```

最終プロンプトは `prompt_prefix` + 各項目の `text` + `prompt_suffix` で組み立てる（`runs/README.md`）。`[rendering]` と `[guard]` は prefix か suffix に入れる。

## 軸の語彙

記録するときは、次の軸のどれかで書く。軸に収まらない発見があれば、軸を足す（足した run を `履歴` に書く）。

| 軸 | 選び方の例（対になる性質） |
| --- | --- |
| 構図の中心性 | 中央に主役を置く / 全面に分散させる |
| 対称性 | 左右対称 / 非対称 |
| スケールの対比 | 大小の差が大きい / 均一 |
| 密度・余白 | 密 / 疎、余白の大きさ |
| 線・点の細かさ | 太い形が少数 / 細線・小さな光点・放射線が画面全体にある |
| 反復 | 規則的な反復 / 不規則、反復なし |
| 輪郭・線 | 手描きの揺らぎ / 機械的に滑らか / 発光した縁 |
| 面の処理 | ベタ塗り / グラデーション / 紙やインクの質感 / ぼかした発光 |
| 色 | 色数、彩度、地と図の明度差 |
| 色の階層 | 主色・補助色・アクセントの役割がある / 複数の高彩度色が同じ強さで並ぶ |
| 具象度 | 題材をそのまま描く / 記号化 / 抽象化 |
| 奥行き | 平面 / パースや立体感 |
| 文字状の模様 | 文字・ロゴのような形の混入 |
| 汎用 AI 画らしさ | 雰囲気だけの背景、過剰な発光、典型的な中央の紋章 など（slop） |

## 好みの記録

状態の意味:

- **観察**: 1 つの run で見えた。まだ再現を見ていない。
- **仮説**: 理由を考えた。プロンプトを変えて確かめる予定。
- **確認済み**: **2 つ以上の別の題材**で、同じ方向の変更が人間の打率を上げ、類似度（下記）が大きく悪化しなかった。1 プロンプト 1 枚の評価（`/eval-prompts`）では、「句の戦績」の表で、2 題材以上で「その句あり = OK かつ同じ題材の `base` = NG」が成り立ち、「その句あり = NG かつ `base` = OK」が 0 件のとき。
- **却下**: 試したが効かなかった、または悪化した。

まだ何も確認済みではない。最初の観察は次のとおり。

| 軸 | 好む方向 | 避ける方向 | 状態 | 根拠（run） |
| --- | --- | --- | --- | --- |
| 面の処理 | ベタ塗りの面。形は平面の記号 | 金属の反射、立体を出す陰影、リアルな質感 | 観察 | `gap-10-city` の `xl-10-city-19`（歯車）。形の繰り返し自体には可能性を感じるが、陰影と金属の質感がマイナス。`gap-09-scifi` の 07・19・23 も、プロンプトは flat graphic なのに写実的な質感になった |
| 奥行き | 1 枚の面に乗る | 室内や風景としてのパース、奥行きのある空間 | 観察 | `xl-09-scifi-19`（宇宙船の内部を奥行きのある部屋として描いた）。「flat graphic」と書いてあっても、具体的な名詞（capsule, interior）が勝った |
| 具象度 | 題材をシルエットや少数の面に落とす | 人物・手・顔・建物を、それと分かる写実で描く | 観察 | `xl-09-scifi-23`（手袋と球体）、`xl-09-scifi-07`（宇宙飛行士）。プロンプトに no person / silhouette / no face と書いてあったが、モデルは写実的な人物と手を描いた |
| 色の階層 | 主色 1 色、補助色 1〜2 色、アクセント 1 色。大きな静かな色面があり、最も鮮やかな色は一部だけ | 複数の高彩度色（紫・青・水色・ピンク・橙・黄・緑）が、同じ強さで画面全体に並ぶ。見ているとチカチカする | 観察（1 枚） | `gap-09-scifi` の `xl-09-scifi-05`（円盤が浮かぶ夕景）。背景・機体・光線・地面のすべてが高彩度で発光し、色に役割がない |
| 線・点の細かさ | 太い形を少数。細線や光点は一部に限る | 細い放射線、星、発光した輪郭線を画面全体に重ねる | 観察（1 枚。色の階層と同じ画像で、切り分けていない） | `xl-09-scifi-05`。色の階層と合わさって、チカチカする印象を作っている可能性が高い。どちらが効いているかは、条件を分けて試すまで分からない |
| 文字状の模様 | 文字の混入がない | 崩れた文字が入る | 観察（モデルの挙動。好みではなく、混入そのもの） | `future-bass-baseline`: XL Turbo-Lightning（cfg 2）では negative の `text` が効かず、`FUTURE BASS` 風の崩れた文字が複数枚に出た。ただし文字入りの画像でも、人間が「欲しい」と判断したものがある（`base-05`）ので、嫌いとは言えない |

#### 追加観察（2026-11-25、人間レビュー: 14 題材・210 枚）

14 題材の構造化発散（各 15 枚。`runs/*-structured`）を、人間が `好み`（残す / 保留 / 外す）と `一致`（強い / 部分 / 弱い）で採点した。残す 67（32%）、保留 33（16%）、外す 107（51%）。以下は、プロンプトの句の有無による件数と、コンタクトシートの目視から読んだもの。**句だけを変えた比較実験ではない**ので、すべて観察とする。題材が違っても同じ向きに出ているものだけを書く。

| 軸 | 好む方向 | 避ける方向 | 状態 | 根拠 |
| --- | --- | --- | --- | --- |
| 反復 | 少数の大きな単位、方向のある流れ、縦縞（幅が不揃い） | 同じ小さな単位を均等に敷き詰める（格子・市松・タイル・織り・編み・点の列）。「regular」「repeating」を句に入れる | 観察（11 題材で外す） | 規則反復の句 23 件のうち残す 1 件、外す 20 件で、11 題材すべてに外すがある。織り・編み・タイル・市松・格子の句 13 件はすべて外す（`koi`・`gurenge`・`highway-night`・`autumn-dusk`・`before-rain` ほか）。縦縞の句は 4 件すべて残す（`winter-morning` 14、`hakujitsu` 11、`shinjidai` 12、`gurenge` 10） |
| 密度・余白 | 画面を使う。中〜大の形が複数ある | 広い空白に、小さな点・線・形が 1 つだけ。画面を二分割する | 観察（12 題材中 11 題材で外す） | 「一つだけ」を主役にした句 24 件のうち残す 3 件、外す 18 件（`koi-structured` 15、`autumn-dusk-structured` 15、`gurenge-structured` 15、`highway-night-structured` 15 ほか）。分割・斜め分割の句は 8 件のうち残す 0 件・外す 5 件 |
| 具象度 | 輪郭のはっきりした花・葉・ハート・花びらなど、記号になった小〜中サイズのモチーフ | 風景（畑・地平線・空・山）として読める写実寄りの絵、石や苔などの質感 | 観察 | 花・葉・ハート・花びら（星を除く）は 23 件のうち残す 14 件・外す 6 件。星を含めると残す 49%・外す 33%。「flat graphic」と書いても、地平線・畑・空・夕景の語があると写真のような風景が出る（`lilac-structured` 03・10・15、`autumn-dusk-structured` 12、`shinjidai-structured` 11、`winter-morning-structured` 01）。この 6 枚はすべて外す |
| 線・形の流れ | 流れる線・彗星・炎・リボン・波・筆の線。画面を横切る方向がある | 方向のない点・粒の散布、輪や額縁のように中心に穴をつくる形 | 観察 | 流れる線・彗星・炎・リボン・波の句は 33 件のうち残す 19 件・外す 9 件（`highway-night`・`gurenge`・`shinjidai` で顕著）。円環や額縁が主役の画（`gurenge-structured` 11、`festival-end-structured` 06・08、`koi-structured` 12 ほか）は外すことが多い |
| 色 | 彩度のある 2〜3 色。暗地に暖色の光、または白地に強い黒・赤 | くすんだ灰・灰緑・淡色だけで、明暗差も小さい | 観察（2 題材で顕著） | `before-rain-structured`（残す 2 / 15）と `winter-morning-structured`（残す 4 / 15）は、題材の色味どおり低彩度・低コントラストで、外すが多い。`gurenge`・`hakujitsu`（ともに残す 8 / 15）は強い明暗差がある |
| 面の処理 | 平面の塗りと、筆・にじみの縁 | 陰影つきの切り紙や、立体のエンボスに見える円盤・リング・タイル | 観察 | 「切り紙」の句は 10 件のうち残す 2 件・外す 8 件。コンタクトシートで、影つきの立体として出たものが外れている。墨・筆・にじみは 42 件のうち残す 18 件・外す 15 件で、決め手にならない |
| 気持ち悪さと好み | （別の軸として扱う） | — | 観察 | 自己レビューで気持ち悪いと見なした絵にも、残すがある（`idol-structured` 06・12、`before-rain-structured` 05、`hakujitsu-structured` 12、`gurenge-structured` 08・09）。粒・水滴・金粉・密な花は、好みが分かれる。気持ち悪さは `self_review.json` の別のフラグとして残し、好みの根拠にしない |

句の語感について。**「calm」「quiet」を含む句は、50 件のうち残す 14 件（28%）・外す 29 件（58%）**で、全体（残す 32% / 外す 51%）より悪い。ただし静かな題材（`before-rain`・`winter-morning`・`festival-end`）に偏っているので、句のせいか題材のせいかは分かれていない。

#### 好み・一致・機械の関係（2026-11-25）

- `好み` と `一致` は、ほぼ連動する。一致が強い 48 件のうち残す 37 件（77%）、部分 57 件のうち 17 件（30%）、弱い 93 件のうち 12 件（13%）。外す 107 件のうち、一致が弱いものが 70 件。**好みを上げる近道は、題材の核が見える方向を選ぶこと**だと読める。
- 好み高・一致低は 12 件（`kickback-structured` 02、`idol-structured` 06 ほか）。題材から外れた発見として、別のお題の素材に回せる。好み低・一致高は 4 件しかなく、「核は合っているが好みではない」案は少ない。
- 分類器（足切り p ≥ 0.2517）は、残す 67 件のうち 55 件（82%）を通し、外す 107 件のうち 60 件（56%）を通している。残す と 外す を分ける AUC は 0.72。外す の半分以上を通すので、足切りだけでは足りない。機械の判定は、人間の好みの粗い目安として読む。
- 各題材の最初の案（基準案 `01`）は、14 題材のうち残す 5・外す 7 で、ほかの方向案より良いわけではない。

### 試す句の案（未検証）

観察から作った、肯定形の句の案。効くかどうかは、`/tune-prompts` で条件を分けて試すまで分からない。1 つの句で 1 つの軸だけを動かす。

| ID | 軸 | 句の案 |
| --- | --- | --- |
| `color` | 色の階層 | `restrained three-color palette, one dominant dark ground color, one main turquoise shape, magenta used only as a small accent, large quiet color fields, clear foreground and background hierarchy` |
| `fine` | 線・点の細かさ | `thick bold shapes, broad empty areas, only a few fine lines or light points, calm visual rhythm` |
| `flat` | 面の処理 | `flat solid color fills only, no highlights, no cast shadows, no metallic shine` |
| `depth` | 奥行き | `everything sits on one flat plane, no perspective, no interior space` |
| `abstract` | 具象度 | `subject reduced to a bold silhouette and a few flat shapes, no body, hands or face` |
| `off-center` | 構図の中心性 | `asymmetrical off-center composition, no dominant central emblem, uninterrupted field around the main marks` |
| `texture-guard` | 面の処理 | `clean graphic surfaces with no photographic microtexture, no clustered small objects, simple readable edges` |
| `motif` | 具象度・密度 | `a few bold, clearly drawn motifs at medium to large scale, flat shapes with confident edges, filling the frame` |
| `flow` | 線・形の流れ | `bold flowing lines or ribbons crossing the frame in one clear direction, flat color` |
| `vstripe` | 反復 | `wide vertical stripes of uneven widths in two or three saturated colors` |
| `no-grid` | 反復（避ける） | `no grid, no checker, no tile, no woven or knitted texture, no evenly repeated small units` |
| `strong-contrast` | 色 | `two or three saturated colors with strong light and dark contrast, no gray or muted tones` |

色の階層は、色を指定するだけでなく、どの色を主役にするかまで書く（題材の色味に合わせて入れ替える）。

2026-11-25 の人間レビューで、`fine`（calm visual rhythm、broad empty areas）と `color`（large quiet color fields）は、静かさや空白を強める方向で、外す側に寄るおそれが出た。試す前に書き換える。`matte-sparse` と `signal`（広い地に少数の点・暖色 1 つ）は、同じ理由で候補から外した。

### 句の戦績（題材をまたいだ積み上げ）

`/eval-prompts` の結果を、1 題材につき 1 行ずつ足す。「句あり」は、その句を単独で入れたプロンプトの結果。`base` は、同じ題材・同じ seed で句を入れなかったプロンプト。結果は、人間のレビューによる OK / NG（レビューがないときは自己評価で、末尾に「(自)」と付ける）。

| ID | 題材 | 句あり | `base` | 日付 | run |
| --- | --- | --- | --- | --- | --- |
| （まだない） | | | | | |

対照（避ける方向の句を入れたプロンプト）が NG だった場合は、その軸の「避ける方向」の根拠として、観察の行に書き足す。

### 題材レベルの傾向（抽象化前の材料）

LLM 側の画像の仕分け（`generated/`、312 枚）から。**題材の傾向であって、軸の好みではない**。`/tune-prompts` が、軸に言い換えて上の表に移す。

- like が多い: 手描きの自然物、ヴィンテージの装飾・ラベル、染織、星雲・オーロラ、Future Bass / Techno の光の形
- dislike が多い: 都市・建築・工業、ポップ、House、Electro Swing

## 打率の基準（ベースライン）

人間の打率は、レビュー済みの条件のみ。LLM 側の like 率は、同じセル指定で LLM 側が作った 24 枚中の like の割合。`uv run tools/summarize_runs.py` で最新を見る。

| 題材 | LLM 側 like 率 | ComfyUI（XL）の人間 OK 率 | 備考 |
| --- | --- | --- | --- |
| 抽象 | 33% | 50% | LLM 側より高い |
| ヴィンテージ | 33% | 17% | ギャップが大きい |
| SF | 25% | 8% | ギャップが大きい |
| 都市 | 0% | 0% | 元から like がない |
| ポップ | 0% | 8% | 元から like がほぼない |
| House | 12% | 25% | |
| Electro Swing | 4% | 17% | |
| 自然・染織・Techno | 58% / 17% / 25% | 未確認 | レビュー待ち（SD1.5 と並べて見る） |

日付: 2026-11-24。XL = DreamShaperXL Turbo-Lightning。1 条件 12 枚、「明確なものだけ印を付けた」判定なので、条件どうしの比較の目安として読む。

## モデルのメモ

| モデル | 設定 | わかっていること |
| --- | --- | --- |
| DreamShaperXL Turbo-Lightning | 1152x768、dpmpp_sde、6 steps、cfg 2 | 以後の調整はこれを既定にする。cfg が低く、negative はほとんど効かない（肯定形の言い換えが必要）。具体的な名詞（astronaut, capsule, gears）を渡すと、「flat graphic」より写実側に倒れる |
| DreamShaper8（SD1.5） | 768x512、dpmpp_2m、25 steps、cfg 6.5 | 人間の所感では XL より明確に劣る。染織・Techno では機械の通過率も XL より低い。比較用に残し、調整サイクルの既定にはしない |

## 履歴

| 日付 | run | 内容 |
| --- | --- | --- |
| 2026-11-24 | `gap-*`（10 題材）、`future-bass-baseline` | 品質ギャップの検証。ベースラインを記録 |
| 2026-11-24 | `gap-09-scifi`, `gap-10-city` | 所感を観察として記録。写実的な質感・パース・人物がマイナス。XL を既定モデルにする |
| 2026-11-24 | `gap-09-scifi` | 色の階層と、線・点の細かさを観察として追加。色がごちゃつくとチカチカして NG。軸の語彙に 2 軸を足し、試す句の案を載せた |
| 2026-11-25 | `*-structured`（14 題材・人間レビュー） | 自己レビューの仮説（広い余白＋少数の点、大きな色面、切り紙）は人間レビューで逆または不明に。規則反復・織り・格子、一つだけの小さな形、分割を避ける方向に、花・葉・流れる線・縦縞を好む方向に追加。好みと一致の連動、分類器との関係を記録。句の案を入れ替えた。比較実験ではないので、すべて観察扱い |
