#!/bin/bash
# Render every gameplay scene to ~/ma_promo/clips/<scene>.mp4 on the Spark (CPU only, niced).
cd ~/ma_promo
for s in ${@:-village mill gather build march battle tower command}; do
  rm -rf clips/frames_$s
  nice python3 capture.py $s clips > clips/log_$s.txt 2>&1 && echo "OK $s" || echo "FAIL $s"
done
echo ALLDONE
