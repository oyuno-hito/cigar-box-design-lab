#!/bin/sh
# generator/temp/queue.txt に書かれた run を、1 つずつ順に流す（eval_pipeline.sh）。
# 完了した行は generator/temp/queue.done に記録する。queue.txt に追記すれば、動いたまま拾う。
# 「STOP」という行を書くと終わる。
#
#   sh tools/eval_queue.sh
cd "$(dirname "$0")/.."
Q=generator/temp/queue.txt
D=generator/temp/queue.done
touch "$Q" "$D"
while true; do
  next=""
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    if [ "$line" = "STOP" ]; then echo "QUEUE_STOP"; exit 0; fi
    if ! grep -qxF "$line" "$D"; then next="$line"; break; fi
  done < "$Q"
  if [ -z "$next" ]; then sleep 15; continue; fi
  # 手動で動かしている生成が終わるのを待つ
  while pgrep -f "[r]un_generate.py" >/dev/null; do sleep 5; done
  if sh tools/eval_pipeline.sh "$next"; then
    echo "$next" >> "$D"
  else
    echo "QUEUE_FAILED $next"
    echo "$next" >> "$D"
  fi
done
