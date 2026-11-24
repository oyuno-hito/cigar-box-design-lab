#!/bin/sh
# 1 つの run を、生成 → 採点 → レポート → コンタクトシートまで流す。
#
#   sh tools/eval_pipeline.sh runs/<run-id>
#
# ComfyUI が起動していること。.venv があること。途中で失敗したら、そこで止まる。
set -e
cd "$(dirname "$0")/.."
RUN="$1"
python3 tools/run_generate.py "$RUN"
.venv/bin/python tools/score_run.py "$RUN"
python3 tools/make_report.py "$RUN"
.venv/bin/python tools/montage.py "$RUN" --sort id
echo "PIPELINE_DONE $RUN"
