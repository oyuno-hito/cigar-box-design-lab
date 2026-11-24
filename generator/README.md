# generator

画像生成環境です。Docker で ComfyUI を動かす構成を置いています。

Docker は NVIDIA GPU のある PC 向けです。macOS など Docker で GPU が使えない環境では、Comfy Desktop などで各自 ComfyUI を用意してください。`tools/run_generate.py` は起動中の ComfyUI の HTTP API（既定は `http://127.0.0.1:8188`）だけを使うので、どの方法で起動していても動きます。モデルの置き場所や名前は環境ごとに合わせてください。

```text
generator/
  Dockerfile               ComfyUI（リリースタグ固定）+ PyTorch
  compose.yaml             ポート、ボリューム、GPU の指定
  extra_model_paths.yaml   models/ 以下を ComfyUI のモデル置き場にする設定
  workflows/               ComfyUI のワークフロー JSON（Git 管理）
  models/                  モデル本体（Git 管理外）。使ったモデルは MODELS.md に記録
  output/                  生成結果の出力先（Git 管理外）
  input/                   入力画像（Git 管理外）
```

## 前提

NVIDIA GPU のある PC で動かす想定です。

- Docker Desktop（Windows は WSL2 バックエンド）または Docker Engine + Compose v2
- NVIDIA ドライバー。CUDA Toolkit は不要
  - 既定の PyTorch は CUDA 13.0 版で、**新しめのドライバー（目安: R580 以降）が必要**
  - ドライバーが古い場合は、下の「古いドライバーの場合」を使う
- Linux の場合は NVIDIA Container Toolkit

コンテナから GPU が見えるかは、次で確認できます。

```bash
docker run --rm --gpus all ubuntu nvidia-smi
```

## 使い方

```bash
cd generator
docker compose up --build
```

初回はイメージのビルドに時間がかかります。PyTorch と CUDA ライブラリの取得で、数 GB のダウンロードとディスク容量が必要です。起動したら <http://127.0.0.1:8188> を開きます。

止めるときは `Ctrl+C`、またはバックグラウンドで起動した場合は `docker compose down` です。

GPU が使われているかは、次で確認できます。

```bash
docker compose run --rm comfyui python -c "import torch; print(torch.cuda.is_available())"
```

`True` なら GPU を使えています。

## モデルを置く

`generator/models/` 以下に、種類ごとのサブディレクトリを作って置きます。

```text
models/
  checkpoints/        SDXL などの checkpoint
  diffusion_models/   Flux などの diffusion model 単体
  text_encoders/
  vae/
  loras/
  ...
```

使い分けは [models/MODELS.md](models/MODELS.md) の表に、入手元・SHA-256・ライセンスなどを残します。モデル本体はコミットしません。

## 更新・オプション

ComfyUI のバージョンを変えるとき（現在の既定は `Dockerfile` の `COMFYUI_VERSION`）:

```bash
docker compose build --build-arg COMFYUI_VERSION=v0.xx.x
```

### 古いドライバーの場合

CUDA 13.0 の PyTorch が動かないときは、CUDA 12.6 版でビルドします。

```bash
docker compose build --build-arg PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu126
```

### 再現性について

ComfyUI はタグで固定していますが、PyTorch は固定していません。環境を完全に再現したいときは、ビルド後に次を保存して固定してください。

```bash
docker compose run --rm comfyui pip freeze > requirements.lock.txt
```

実行環境（OS、GPU）によって動かない設定や結果の違いがあります。再現に必要な情報（ワークフロー JSON、使ったノードとバージョン、seed）を残してください。

## 未対応

- カスタムノードの導入と永続化（必要になった時点で `custom_nodes/` のマウントを足す）
- コンテナ内は root で動くため、Linux では `output/` が root 所有になる
