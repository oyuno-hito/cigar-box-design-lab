#!/bin/sh
set -eu

# ComfyUI 本体は Git 管理外に clone し、依存環境だけを uv で管理する。
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
GENERATOR="$ROOT/generator"
COMFYUI_VERSION="${COMFYUI_VERSION:-v0.46.3}"
COMFYUI="$GENERATOR/ComfyUI"
VENV="$GENERATOR/.venv"
UV="${UV:-uv}"

if ! command -v "$UV" >/dev/null 2>&1; then
  echo "uv が見つかりません。先に https://docs.astral.sh/uv/ の手順でインストールしてください。" >&2
  exit 1
fi

if [ ! -d "$COMFYUI/.git" ]; then
  echo "ComfyUI $COMFYUI_VERSION を clone します..."
  git clone --depth 1 --branch "$COMFYUI_VERSION" \
    https://github.com/Comfy-Org/ComfyUI.git "$COMFYUI"
else
  current=$(
    git -C "$COMFYUI" describe --tags --exact-match 2>/dev/null || true
  )
  if [ "$current" != "$COMFYUI_VERSION" ]; then
    echo "ComfyUI を $COMFYUI_VERSION に切り替えます..."
    git -C "$COMFYUI" fetch --depth 1 origin "refs/tags/$COMFYUI_VERSION"
    git -C "$COMFYUI" checkout --detach "$COMFYUI_VERSION"
  fi
fi

if [ ! -x "$VENV/bin/python" ]; then
  "$UV" venv --python 3.12 "$VENV"
fi

# requirements.lock.txt は ComfyUI v0.46.3 用に解決済み。
# torch も同じロックに含めるため、Mac (MPS) と Linux (CUDA) で版がぶれない。
"$UV" pip sync --python "$VENV/bin/python" "$GENERATOR/requirements.lock.txt"

mkdir -p "$GENERATOR/input" "$GENERATOR/output" "$GENERATOR/user"
echo "準備完了。次のコマンドで起動できます:"
echo "  $GENERATOR/start_comfy.sh"
