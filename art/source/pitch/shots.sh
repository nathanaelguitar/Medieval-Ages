#!/bin/bash
# On the Spark: the six screenshot stills as lossless PNG (frame times match make_screens.py PICKS).
cd ~/ma_pitch && mkdir -p shots
./run.sh village -- --at 7.5 --png; ./run.sh battle -- --at 3.0 --png; ./run.sh mill -- --at 6.6 --png
./run.sh banners -- --at 3.5 --png; ./run.sh place -- --at 2.9 --png --css "#__fing{display:none!important}"; ./run.sh title -- --at 0.1 --png
for s in village battle mill banners place title; do rm -rf shots/frames_$s; cp -r clips/frames_$s shots/; done
echo SHOTSDONE
