#!/bin/bash
# TRELLIS.2 bodies for the archer and the two villagers on the Spark (GPU half of run_archer_v1.sh /
# run_villagers_v1.sh). Same recipe as the man-at-arms v2 build (docker/trellis2/run_v2.sh): BiRefNet
# cut-outs of the four A-pose views per team, one shape from the blue front, one texture pass per
# view through the generation path, normal-weighted merge per team onto the shared UV mesh.
#   bash art/pipeline/trellis_units_v1.sh archer villager_m villager_f 2>&1 | tee ~/trellis2/units_v1.log
# The back views are NOT mirrored: unlike the man-at-arms generations, these back views already show
# the asymmetric details (archer quiver + tabard half, villager pouch/knife) on the physically
# correct side (checked against the front views). Props (bow, tools, basket) are procedural in
# rig_body.py, so no prop images go through TRELLIS.
set -e
T=~/trellis2; M=~/medieval; HY=~/hunyuan3d/.venv/bin/python
SRC_OF() { case $1 in archer) echo $M/art/source/archer/gen;; villager_*) echo $M/art/source/villager/gen;; esac; }
PFX_OF() { case $1 in archer) echo "";; villager_m) echo "male_";; villager_f) echo "female_";; esac; }
for U in "$@"; do
    SRC=$(SRC_OF $U); PFX=$(PFX_OF $U); W=/trellis2/work/$U; P=$W/prep
    mkdir -p $T/work/$U/prep $M/art/models/${U}_v1
    echo "== $U: cut-outs"; T0=$(date +%s)
    names=""
    for team in blue red; do for v in front back left right; do names="$names ${PFX}${team}_apose_$v"; done; done
    nice -n 10 $HY $T/prep_views.py --in $SRC --out $T/work/$U/prep $names
    echo "   prep: $(( $(date +%s) - T0 ))s"
    echo "== $U: shape from the blue front"; T0=$(date +%s)
    $T/run.sh python /trellis2/trellis_body.py shape --image $P/${PFX}blue_apose_front.png --out $W/shape --faces 40000
    echo "   shape: $(( $(date +%s) - T0 ))s"
    for team in blue red; do
        echo "== $U: texture passes, $team"; T0=$(date +%s)
        $T/run.sh python /trellis2/trellis_body.py texture --mesh $W/shape/uvmesh.pt --gen-slat $W/shape/shape_slat.pt \
            --raw $W/shape/raw.pt --out $W/tex_$team \
            --view front=$P/${PFX}${team}_apose_front.png --view back=$P/${PFX}${team}_apose_back.png \
            --view left=$P/${PFX}${team}_apose_left.png --view right=$P/${PFX}${team}_apose_right.png
        $T/run.sh python /trellis2/trellis_body.py merge --mesh $W/shape/uvmesh.pt --tex $W/tex_$team --raw $W/shape/raw.pt \
            --out $W/${U}_$team.glb --view front=0 --view back=180 --view left=90 --view right=270 --front-axis=-y \
            --saturation 1.3 --value 1.1
        cp $T/work/$U/${U}_$team.glb $M/art/models/${U}_v1/
        echo "   texture+merge $team: $(( $(date +%s) - T0 ))s"
    done
done
echo "DONE trellis_units_v1"
