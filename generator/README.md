# generator

画像生成環境の置き場です。Docker で ComfyUI を動かす予定です。

```text
generator/
  README.md
  workflows/     ComfyUI のワークフロー JSON
  models/        モデル本体（Git 管理外）。使ったモデルは MODELS.md に記録
```

## 方針

- モデル本体はコミットしない。`.gitkeep` と `MODELS.md` だけ管理する。
- Docker の設定、起動手順、ワークフローはこれから追加する。
- 実行環境（OS、GPU）によって動かない設定や結果の違いがある。再現に必要な情報（ワークフロー JSON、使ったノードとバージョン、seed）を残す。
