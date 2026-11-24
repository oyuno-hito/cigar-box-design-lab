# scorers

分類器（スコアラー）の置き場です。足切り・並べ替え用で、熱心には育てません。

```text
scorers/
  CURRENT        現在使うバージョン名（例: v002）
  v001/
    scorer.json  係数としきい値（pickle は使わない）
    manifest.json
    metrics.json
```

## ルール

- `vNNN/` は作成後に書き換えない。更新するときは新しいバージョンを作る。
- `manifest.json` には、参照した画像の ID・ハッシュ・その時点のラベル、埋め込みモデル、学習時点のコミットを書く。
- `CURRENT` は symlink ではなくテキストファイルにする（Windows で扱いやすくするため）。
