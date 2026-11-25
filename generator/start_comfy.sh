#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
GENERATOR="$ROOT/generator"
COMFYUI="$GENERATOR/ComfyUI"
PYTHON="$GENERATOR/.venv/bin/python"

if [ ! -x "$PYTHON" ] || [ ! -f "$COMFYUI/main.py" ]; then
  echo "ComfyUI の環境がありません。先に generator/setup.sh を実行してください。" >&2
  exit 1
fi

cd "$GENERATOR"
exec "$PYTHON" "$COMFYUI/main.py" \
  --listen 127.0.0.1 \
  --port 8188 \
  --extra-model-paths-config "$GENERATOR/extra_model_paths.yaml" \
  --input-directory "$GENERATOR/input" \
  --output-directory "$GENERATOR/output" \
  --user-directory "$GENERATOR/user"
