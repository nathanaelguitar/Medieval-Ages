#!/bin/bash
# Game animals v1 (boar, sheep) on the Spark, replacing the 0 A.D. fauna sprites. Same recipe as the
# units: Codex reference views (art/source/animals/gen, flat magenta, keyed by prep_magenta.py on
# the Mac into art/out/animals/prep and synced to ~/trellis2/work/animals/prep), one TRELLIS.2 shape
# from the side profile, texture passes from five views merged by surface normal, then a procedural
# quadruped rig (rig_quadruped.py: walk, grazing idle, carcass) baked with the units' camera,
# lighting, contrast and scale (14.34 px/unit) into eight directions.
#   rsync -a art/pipeline/ spark:medieval/art/pipeline/
#   ssh spark 'cd ~/medieval && bash art/pipeline/run_animals_v1.sh 2>&1 | tee art/out/animals_v1/run.log'
#   STAGES=rig,bake ANIMALS=sheep bash art/pipeline/run_animals_v1.sh
# TRELLIS.2 picks its own canonical heading whatever view it is given: the boar came out head toward
# -Y (like the units), the sheep head toward +X. FA is that axis, so the face view is merge yaw 0, the
# front three-quarter 45, the right-facing profile (the left flank) 90, the rear 180 and the
# left-facing profile 270; YAW turns the head to -Y in the rig. Check a new shape's heading with
# preview_models.py before merging.
set -e
M=$HOME/medieval; cd $M
T=$HOME/trellis2; W=/trellis2/work/animals; P=$W/prep
B="docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v $M:/work medieval-blender nice -n 10 blender --background"
LIGHT="--sun-elev 52 --sun-energy 5.0 --sun-color 1.0,0.9,0.78 --sun-angle 9 --world-strength 0.55 --world-color 0.6,0.72,0.95 --shadow-pass --shadow-samples 32 --shadow-opacity 0.4"
STAGES=${STAGES:-shape,texture,merge,rig,bake}
ANIMALS=${ANIMALS:-boar,sheep}
DRY=${DRY:-}
has() { [[ ",$STAGES," == *",$1,"* ]]; }
V=art/models/animals_v1; OUT=art/out/animals_v1
mkdir -p $V $OUT/previews
for A in ${ANIMALS//,/ }; do
    case $A in
        boar)  HEIGHT=${HEIGHT_BOAR:-2.1};  WALK=${WALK_BOAR:-16};  POLL=0.47; FA=-y; YAW=0;;
        sheep) HEIGHT=${HEIGHT_SHEEP:-1.8}; WALK=${WALK_SHEEP:-20}; POLL=0.5;  FA=+x; YAW=-90;;
    esac
    if has shape; then
    echo "== $A: shape from the side profile"; T0=$(date +%s)
    (cd $T && ./run.sh python /trellis2/trellis_body.py shape --image $P/${A}_right.png --out $W/${A}_shape --faces 20000)
    echo "   shape: $(( $(date +%s) - T0 ))s"
    fi
    if has texture; then
    echo "== $A: texture passes"; T0=$(date +%s)
    (cd $T && ./run.sh python /trellis2/trellis_body.py texture --mesh $W/${A}_shape/uvmesh.pt \
        --gen-slat $W/${A}_shape/shape_slat.pt --raw $W/${A}_shape/raw.pt --out $W/${A}_tex \
        --view right=$P/${A}_right.png --view left=$P/${A}_left.png --view front=$P/${A}_front.png \
        --view back=$P/${A}_back.png --view front34=$P/${A}_front34.png)
    echo "   texture: $(( $(date +%s) - T0 ))s"
    fi
    if has merge; then
    echo "== $A: merge"; T0=$(date +%s)
    (cd $T && ./run.sh python /trellis2/trellis_body.py merge --mesh $W/${A}_shape/uvmesh.pt --tex $W/${A}_tex \
        --raw $W/${A}_shape/raw.pt --out $W/${A}.glb --front-axis=$FA \
        --view front=0 --view front34=45 --view right=90 --view back=180 --view left=270)
    cp $T/work/animals/${A}.glb $V/
    echo "   merge: $(( $(date +%s) - T0 ))s"
    fi
    if has rig; then
    echo "== $A: rig"; T0=$(date +%s)
    $B --python art/pipeline/rig_quadruped.py -- --body $V/${A}.glb --height $HEIGHT --yaw $YAW \
        --walk-frames $WALK --poll $POLL --out $V/${A}_rig.blend --diag $OUT/previews/${A} \
        2>&1 | grep -E "^==|^   |Traceback|Error"
    echo "   rig: $(( $(date +%s) - T0 ))s"
    fi
    if has bake; then
    echo "== $A: bake"; T0=$(date +%s)
    rm -rf $OUT/$A/sprites $OUT/$A/sprites@2x $OUT/$A/_tiles
    $B $V/${A}_rig.blend --python art/pipeline/bake_sprites.py -- \
        --name animal --teams $A --clip idle=12:${CELL:-88} --clip walk=12:${CELL:-88} --clip dead=1:${CELL_DEAD:-96} \
        --size 72 --supersample 2 --out $OUT/$A --px-per-unit 14.34 $DRY \
        $LIGHT --contrast 0.35 2>&1 | grep -E "^==|span|clip |wrote|Traceback|Error"
    echo "   bake: $(( $(date +%s) - T0 ))s"
    fi
done
echo "DONE run_animals_v1"
