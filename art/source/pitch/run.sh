#!/bin/bash
# On the Spark: serve ~/ma_pitch/WebGame (the committed game) on 127.0.0.1:8771 if it is not up, then
# capture the named scenes to ~/ma_pitch/clips (CPU only, niced). Extra args after "--" go to capture.py.
cd ~/ma_pitch
if ! curl -s -o /dev/null http://127.0.0.1:8771/index.html; then
  (cd WebGame && setsid nohup nice python3 -m http.server 8771 --bind 127.0.0.1 > ../server.log 2>&1 < /dev/null & echo $! > ../server.pid)
  sleep 1
fi
scenes=(); extra=()
while [ $# -gt 0 ]; do [ "$1" = "--" ] && { shift; extra=("$@"); break; }; scenes+=("$1"); shift; done
for s in "${scenes[@]}"; do
  nice -n 10 python3 capture.py "$s" clips "${extra[@]}" > clips/log_$s.txt 2>&1 && echo "OK $s" || echo "FAIL $s"
done
echo ALLDONE
