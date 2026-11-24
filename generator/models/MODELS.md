# 使用モデルの備忘録

モデル本体は Git 管理外です。再取得できるように、情報だけを残します。

| 用途 | 名前 | ファイル名 | SHA-256 | 入手元 URL | ライセンス | 取得日 | メモ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 分類器の画像埋め込み（scorers/） | openai/clip-vit-base-patch32 | Hugging Face キャッシュ（transformers が自動取得） | （revision: 3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268） | https://huggingface.co/openai/clip-vit-base-patch32 | MIT | 2026-11-24 | `tools/train_scorer.py` が取得。モデル本体は `~/.cache/huggingface` にあり、リポジトリには置かない |
