# 使用モデルの備忘録

モデル本体は Git 管理外です。再取得できるように、情報だけを残します。

| 用途 | 名前 | ファイル名 | SHA-256 | 入手元 URL | ライセンス | 取得日 | メモ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 画像生成（ComfyUI、SDXL）。調整サイクルの既定 | DreamShaper XL Turbo-Lightning（SDXL 系） | `DreamShaperXL_Turbo-Lightning.safetensors`（約 6.9 GB、`generator/models/checkpoints/`） | `fdbe56354b8f876b736f24d3ad867ecd4140c019f57642ec8ddd878088d44f64` | 未記録（作者 Lykon の DreamShaper XL。入手元は要確認） | OpenRAIL++（Hugging Face の `Lykon/dreamshaper-xl-lightning` のモデルカードの表記。このファイルと同一かは未確認） | 2026-11-24 | 1152x768、dpmpp_sde、6 steps、cfg 2。negative はほとんど効かない |
| 画像生成（ComfyUI、SD 1.5）。比較用 | DreamShaper 8（SD 1.5 系） | `DreamShaper8_pruned.safetensors`（約 2.1 GB、`generator/models/checkpoints/`） | `879db523c30d3b9017143d56705015e15a2cb5628762c11d086fed9538abd7fd` | 未記録（作者 Lykon の DreamShaper 8。入手元は要確認） | CreativeML OpenRAIL-M（Hugging Face の `Lykon/dreamshaper-8` のモデルカードの表記。このファイルと同一かは未確認） | 2026-11-24 | 768x512、dpmpp_2m、25 steps、cfg 6.5。XL より劣るため比較用。既定にはしない |
| 分類器の画像埋め込み（scorers/） | openai/clip-vit-base-patch32 | Hugging Face キャッシュ（transformers が自動取得） | （revision: 3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268） | https://huggingface.co/openai/clip-vit-base-patch32 | MIT | 2026-11-24 | `tools/train_scorer.py` が取得。モデル本体は `~/.cache/huggingface` にあり、リポジトリには置かない |
