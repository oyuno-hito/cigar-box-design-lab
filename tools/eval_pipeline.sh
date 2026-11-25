#!/bin/sh
# 1 つの run を、生成 → 採点 → レポート → コンタクトシートまで流す。
#
#   sh tools/eval_pipeline.sh runs/<run-id>
#
# ComfyUI が起動していること。uv が使えること（README の「開発環境」）。途中で失敗したら、そこで止まる。
set -e
cd "$(dirname "$0")/.."
RUN="$1"
uv run tools/run_generate.py "$RUN"
uv run tools/score_run.py "$RUN"
uv run tools/make_report.py "$RUN"
uv run tools/montage.py "$RUN" --sort id
echo "PIPELINE_DONE $RUN"
