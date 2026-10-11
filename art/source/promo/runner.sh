#!/bin/bash
# Durable FastH3 render queue. Reads ~/fasth3_promo/queue.txt line by line (take names);
# renders each take whose "DONE"/"FAIL" line is not yet in status.txt. Appending to queue.txt
# while running is fine. Exits when queue is drained and ~/fasth3_promo/stop exists.
export PATH=$HOME/repos/FastVideo/.venv/bin:$PATH HF_HOME=$HOME/Downloads/hf_home
export FASTVIDEO_VSA_SM100A=0 FASTVIDEO_FA4=0 FASTVIDEO_ATTENTION_BACKEND=VIDEO_SPARSE_ATTN_H3 FASTVIDEO_STAGE_LOGGING=1
D=$HOME/fasth3_promo
cd $HOME/repos/FastVideo
touch $D/status.txt
while true; do
  next=""
  while read -r name; do
    [ -z "$name" ] && continue
    grep -q "^\(DONE\|FAIL\) $name " $D/status.txt && continue
    next=$name; break
  done < $D/queue.txt
  if [ -z "$next" ]; then
    [ -f $D/stop ] && { echo "queue drained, stopping" >> $D/status.txt; exit 0; }
    sleep 20; continue
  fi
  echo "START $next $(date +%s)" >> $D/status.txt
  t0=$(date +%s)
  mkdir -p $D/out/$next
  nice -n 10 fastvideo generate --config $D/$next.yaml > $D/logs/$next.log 2>&1
  rc=$?
  t1=$(date +%s)
  if [ $rc -eq 0 ] && ls $D/out/$next/*.mp4 >/dev/null 2>&1; then
    mv "$(ls $D/out/$next/*.mp4 | head -1)" $D/out/$next/$next.mp4
    echo "DONE $next $((t1-t0))s" >> $D/status.txt
  else
    echo "FAIL $next rc=$rc $((t1-t0))s" >> $D/status.txt
  fi
done
