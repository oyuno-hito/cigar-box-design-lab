# ComfyUI には公式の Docker イメージがないため、自前でビルドする。
# 手順は ComfyUI 公式の手動インストール（リリースタグを clone → PyTorch → requirements.txt）に沿う。
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

# 更新するときは --build-arg で上書きする（README 参照）
ARG COMFYUI_VERSION=v0.46.2
# NVIDIA 20 シリーズ以降は CUDA 13.0 以降の PyTorch が必要。
# 古いドライバーなら cu126 などに差し替える（README 参照）
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu130

RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${COMFYUI_VERSION}" \
      https://github.com/Comfy-Org/ComfyUI.git /opt/ComfyUI

WORKDIR /opt/ComfyUI

# PyTorch の wheel は CUDA ライブラリを同梱するため、CUDA のベースイメージは不要。
# GPU のドライバーは、実行時に NVIDIA Container Toolkit / Docker Desktop が渡す。
RUN pip install --no-cache-dir torch torchvision torchaudio \
      --extra-index-url "${PYTORCH_INDEX_URL}" \
 && pip install --no-cache-dir -r requirements.txt

EXPOSE 8188

# コンテナ内では 0.0.0.0 で待ち受ける。外部への公開範囲は compose.yaml のポート指定で絞る。
CMD ["python", "main.py", \
     "--listen", "0.0.0.0", \
     "--port", "8188", \
     "--extra-model-paths-config", "/opt/extra_model_paths.yaml"]
