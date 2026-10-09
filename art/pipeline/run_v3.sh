#!/bin/bash
# v3 man-at-arms on the Spark: Veo side-view walk -> MediaPipe planar clip -> rig (recoloured blue
# body from recolor_glb.py in art/models/man_at_arms_v3) -> 8-direction sprites (12 walk frames)
# -> previews. Everything niced; vLLM shares the box. Run from the repo mirror:
#   cd ~/medieval && bash art/pipeline/run_v3.sh 2>&1 | tee run_v3.log
# Prerequisites: ~/mp venv (mediapipe, opencv-python-headless, scipy, matplotlib, pillow) with
# ~/mp/models/pose_landmarker_heavy.task; the medieval-blender image; v2's models and
# _cache (assimp-converted clips) in art/models/man_at_arms_v2.
set -e
M=$HOME/medieval; cd $M
MP=$HOME/mp/bin/python
V2=art/models/man_at_arms_v2; V3=art/models/man_at_arms_v3; OUT=art/out/man_at_arms_v3
B="docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v $M:/work medieval-blender nice -n 10 blender --background"
LIGHT="--sun-elev 52 --sun-energy 5.0 --sun-color 1.0,0.9,0.78 --sun-angle 9 --world-strength 0.55 --world-color 0.6,0.72,0.95 --shadow-pass --shadow-samples 32 --shadow-opacity 0.4"
mkdir -p $V3/_cache $OUT/previews art/out/man_at_arms_v2/motion
cp -n $V2/_cache/*.glb $V3/_cache/ || true
cp $V2/man_at_arms_red.glb $V2/shield_blue.glb $V2/shield_red.glb $V3/

echo "== 1. walk clip from the Veo video"; T0=$(date +%s)
nice -n 10 $MP art/pipeline/video_to_clip.py extract --video art/source/man_at_arms/video/veo_walk_side.mp4 \
    --start 1.5 --end 8.0 --facing right --model $HOME/mp/models/pose_landmarker_heavy.task \
    --out art/out/man_at_arms_v2/motion/walk_clip.json --previews art/out/man_at_arms_v2/previews/motion \
    --gain hip=1.2,knee=1.2,arm=1.2,foot=0.7,bob=1.0,torso=1.0 --shield-arm L --shield-arm-gain 0.3 \
    2>&1 | grep -v -E "^(W0|I0|INFO|WARNING)"
echo "   extract: $(( $(date +%s) - T0 ))s"

echo "== 2. blue body recolour"; T0=$(date +%s)
nice -n 10 $MP art/pipeline/recolor_glb.py --in $V2/man_at_arms_blue.glb --out $V3/man_at_arms_blue.glb \
    --preview $OUT/previews/blue_texture_recolor.png
echo "   recolour: $(( $(date +%s) - T0 ))s"

echo "== 3. rig"; T0=$(date +%s)
$B --python art/pipeline/rig_body.py -- \
    --body $V3/man_at_arms_blue.glb --alt red=$V3/man_at_arms_red.glb \
    --shield $V3/shield_blue.glb --shield-alt red=$V3/shield_red.glb \
    --clip idle=art/source/zeroad_clips/biped/infantry/swordsman/idle_relax_shield_01.dae \
    --clip walk=art/out/man_at_arms_v2/motion/walk_clip.json \
    --sword-length 2.0 --sword-blade-w 0.11 --sword-guard-w 0.40 --sword-dir 0,0.15,-1 \
    --out $V3/man_at_arms_rig.blend --diag $OUT/previews/rig_diag 2>&1 | grep -E "^==|^   (rest|ground|frame)|Traceback|Error"
echo "   rig: $(( $(date +%s) - T0 ))s"

echo "== 4. bake"; T0=$(date +%s)
rm -rf $OUT/sprites $OUT/sprites@2x $OUT/_tiles
$B $V3/man_at_arms_rig.blend --python art/pipeline/bake_sprites.py -- \
    --name man_at_arms --teams blue,red --clip idle=6 --clip walk=12 --size 72 --supersample 2 --out $OUT \
    $LIGHT --contrast 0.35 2>&1 | grep -E "^==|span|wrote|Traceback|Error"
echo "   bake: $(( $(date +%s) - T0 ))s"

echo "== 5. previews"; T0=$(date +%s)
$B --python art/pipeline/preview_models.py -- --out $OUT/previews/body_textured.png --size 512 --samples 48 \
    --views "front,3/4,side,back" --mesh "blue team=$V3/man_at_arms_blue.glb" --mesh "red team=$V3/man_at_arms_red.glb" 2>&1 | tail -1
python3 art/pipeline/contact_sheet.py --name man_at_arms --out $OUT/previews/contact_sheet.png \
    --turnaround $OUT/previews/body_textured.png --rows "blue team,red team" --sprites $OUT/sprites
python3 art/pipeline/compare_sprites.py --name man_at_arms --a "v2=art/out/man_at_arms_v2/sprites" --b "v3=$OUT/sprites" \
    --walk-dirs 0,1,7 --out $OUT/previews/compare_v2_v3.png
for team in blue red; do
    python3 art/pipeline/walk_gif.py --sprites $OUT/sprites --name man_at_arms --team $team --dirs 0,1,7 --zoom 3 \
        --out $OUT/previews/walk_$team.gif
done
echo "   previews: $(( $(date +%s) - T0 ))s"
echo "DONE run_v3"
