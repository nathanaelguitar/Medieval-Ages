#!/bin/bash
# End-to-end v2 man-at-arms build on the Spark: reference views -> TRELLIS.2 bodies + shields ->
# rig -> sprites -> contact sheet. ~15 min. Assumes ~/trellis2 (image built, model dir, scripts
# trellis_body.py / prep_views.py / prep_images.py copied there) and the repo subset in ~/medieval.
#   cp art/pipeline/trellis_body.py art/pipeline/prep_views.py art/pipeline/prep_images.py ~/trellis2/
#   bash ~/trellis2/run_v2.sh 2>&1 | tee ~/trellis2/run_v2.log
set -e
T=~/trellis2; W=/trellis2/work/man_at_arms; P=$W/prep; M=~/medieval; MV=$M/art/models/man_at_arms_v2
HY=~/hunyuan3d/.venv/bin/python
mkdir -p $MV $M/art/out/man_at_arms_v2/previews
cd $T

# 1. reference views -> RGBA cut-outs (BiRefNet, MIT). Back views mirrored; shield crops upscaled.
nice -n 10 $HY prep_views.py --in ~/hunyuan3d/inputs/man_at_arms/gen --out $T/work/man_at_arms/prep \
    blue_apose_front_hr blue_apose_back_hr:mirror blue_apose_left blue_apose_right \
    red_apose_front_hr red_apose_back_hr:mirror
nice -n 10 $HY prep_views.py --upscale --in ~/hunyuan3d/inputs/man_at_arms --out $T/work/man_at_arms/prep \
    blue_shield red_shield

# 2. shield: TRELLIS.2 shape from the blue crop, both crops projected onto that one mesh
./run.sh python /trellis2/trellis_body.py shape --image $P/blue_shield.png --out $W/shield_blue --faces 6000 --texture 1024
./run.sh python /trellis2/trellis_body.py project --glb $W/shield_blue/body_gen.glb --image $P/blue_shield.png \
    --out $W/shield_blue.glb --saturation 1.4 --value 1.1
./run.sh python /trellis2/trellis_body.py project --glb $W/shield_blue/body_gen.glb --image $P/red_shield.png \
    --out $W/shield_red.glb --saturation 1.4 --value 1.1

# 3. body: one shape from the blue front; per-view texture passes; normal-weighted merge per team
./run.sh python /trellis2/trellis_body.py shape --image $P/blue_apose_front_hr.png --out $W/shape2 --faces 40000
./run.sh python /trellis2/trellis_body.py texture --mesh $W/shape2/uvmesh.pt --gen-slat $W/shape2/shape_slat.pt \
    --raw $W/shape2/raw.pt --out $W/tex2_blue --view front=$P/blue_apose_front_hr.png --view back=$P/blue_apose_back_hr.png \
    --view left=$P/blue_apose_left.png --view right=$P/blue_apose_right.png
./run.sh python /trellis2/trellis_body.py texture --mesh $W/shape2/uvmesh.pt --gen-slat $W/shape2/shape_slat.pt \
    --raw $W/shape2/raw.pt --out $W/tex2_red --view front=$P/red_apose_front_hr.png --view back=$P/red_apose_back_hr.png
./run.sh python /trellis2/trellis_body.py merge --mesh $W/shape2/uvmesh.pt --tex $W/tex2_blue --raw $W/shape2/raw.pt \
    --out $W/man_at_arms_blue.glb --view front=0 --view back=180 --view left=90 --view right=270 --front-axis=-y \
    --saturation 1.6 --value 1.15
./run.sh python /trellis2/trellis_body.py merge --mesh $W/shape2/uvmesh.pt --tex $W/tex2_red --raw $W/shape2/raw.pt \
    --out $W/man_at_arms_red.glb --view front=0 --view back=180 --front-axis=-y --saturation 1.6 --value 1.15
cp $T/work/man_at_arms/{man_at_arms_blue,man_at_arms_red,shield_blue,shield_red}.glb $MV/

# 4. rig (0 A.D. clips, placeholder) and bake
cd $M
B="docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v $M:/work medieval-blender nice -n 10 blender --background"
$B --python art/pipeline/rig_body.py -- \
    --body art/models/man_at_arms_v2/man_at_arms_blue.glb --alt red=art/models/man_at_arms_v2/man_at_arms_red.glb \
    --shield art/models/man_at_arms_v2/shield_blue.glb --shield-alt red=art/models/man_at_arms_v2/shield_red.glb \
    --clip idle=art/source/zeroad_clips/biped/infantry/swordsman/idle_relax_shield_01.dae \
    --clip walk=art/source/zeroad_clips/biped/infantry/swordsman/walk_relax_shield.dae \
    --sword-length 2.0 --sword-blade-w 0.11 --sword-guard-w 0.40 --sword-dir 0,0.15,-1 \
    --out art/models/man_at_arms_v2/man_at_arms_rig.blend --diag art/out/man_at_arms_v2/previews/rig_diag 2>&1 | grep -E "^==|Traceback"
rm -rf art/out/man_at_arms_v2/sprites art/out/man_at_arms_v2/sprites@2x art/out/man_at_arms_v2/_tiles
$B art/models/man_at_arms_v2/man_at_arms_rig.blend --python art/pipeline/bake_sprites.py -- \
    --name man_at_arms --teams blue,red --clip idle=6 --clip walk=8 --size 72 --supersample 2 --out art/out/man_at_arms_v2 \
    --sun-elev 52 --sun-energy 5.0 --sun-color 1.0,0.9,0.78 --sun-angle 9 --world-strength 0.55 --world-color 0.6,0.72,0.95 \
    --shadow-pass --shadow-samples 32 --shadow-opacity 0.4 2>&1 | grep -E "^==|wrote|Traceback"

# 5. previews
$B --python art/pipeline/preview_models.py -- --out art/out/man_at_arms_v2/previews/body_textured.png --size 512 --samples 48 \
    --views "front,3/4,side,back" --mesh "blue team=art/models/man_at_arms_v2/man_at_arms_blue.glb" \
    --mesh "red team=art/models/man_at_arms_v2/man_at_arms_red.glb" 2>&1 | tail -1
$B --python art/pipeline/preview_models.py -- --out art/out/man_at_arms_v2/previews/shield_projected.png --size 400 --samples 32 \
    --views "front,3/4,side,back" --mesh "blue=art/models/man_at_arms_v2/shield_blue.glb" \
    --mesh "red=art/models/man_at_arms_v2/shield_red.glb" 2>&1 | tail -1
python3 art/pipeline/contact_sheet.py --name man_at_arms --out art/out/man_at_arms_v2/previews/contact_sheet.png \
    --turnaround art/out/man_at_arms_v2/previews/body_textured.png --rows "blue team,red team" --sprites art/out/man_at_arms_v2/sprites
echo "DONE run_v2"
