# generator

画像生成環境です。ComfyUI 本体と専用の Python 環境を、uv で管理します。

`tools/run_generate.py` は起動中の ComfyUI の HTTP API（既定は `http://127.0.0.1:8188`）だけを使うので、ComfyUI の起動方法はこのリポジトリ内のものに限定されません。ただし、再現性を優先するときは、ここで管理する v0.46.3 を使います。

```text
generator/
  setup.sh                 ComfyUI の clone と uv 環境の準備
  start_comfy.sh           ComfyUI の起動
  requirements.lock.txt    ComfyUI v0.46.3 の依存ロック
  extra_model_paths.yaml   models/ 以下を ComfyUI のモデル置き場にする設定
  ComfyUI/                 本体（Git 管理外。setup.sh が clone）
  .venv/                   専用環境（Git 管理外）
  workflows/               ComfyUI のワークフロー JSON（Git 管理）
  models/                  モデル本体（Git 管理外）。使ったモデルは MODELS.md に記録
  output/                  生成結果の出力先（Git 管理外）
  input/                   入力画像（Git 管理外）
```

## 前提

- uv
- Git
- Python 3.12（`setup.sh` が uv 経由で用意する）
- macOS は MPS 対応の Apple Silicon、Linux / Windows は利用する GPU と PyTorch wheel が対応していること

## セットアップと起動

```bash
cd generator
./setup.sh
./start_comfy.sh
```

初回は ComfyUI の clone と PyTorch などの依存取得に時間がかかります。起動したら <http://127.0.0.1:8188> を開きます。停止は `Ctrl+C` です。

ComfyUI のタグを更新するときは、次のようにします。

```bash
COMFYUI_VERSION=v0.xx.x ./setup.sh
```

PyTorch の実行デバイス確認:

```bash
./.venv/bin/python -c "import torch; print('MPS:', torch.backends.mps.is_available()); print('CUDA:', torch.cuda.is_available())"
```

## モデルとワークフロー

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

`requirements.lock.txt` は ComfyUI v0.46.3 の requirements を uv で解決したものです。ComfyUI のタグを更新したら、`ComfyUI/requirements.txt` から次で作り直します。

```bash
uv pip compile ComfyUI/requirements.txt \
  --python-version 3.12 \
  --python-platform aarch64-apple-darwin \
  -o requirements.lock.txt
```

実行環境（OS、GPU）によって動かない設定や結果の違いがあります。再現に必要な情報（ワークフロー JSON、使ったノードとバージョン、seed）を残してください。
