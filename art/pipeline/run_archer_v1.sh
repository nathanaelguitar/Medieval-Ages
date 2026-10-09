#!/bin/bash
# Archer v1 on the Spark: TRELLIS.2 body (trellis_units_v1.sh, run first) + three Veo side-view
# clips (walk, shoot, death) through video_to_clip.py, a 0 A.D. idle, a procedural longbow in the
# left hand, baked with the man-at-arms v4 camera / lighting / contrast / scale (14.34 px/unit).
#   cd ~/medieval && bash art/pipeline/run_archer_v1.sh 2>&1 | tee art/out/archer_v1/run_archer_v1.log
#   STAGES=extract,rig bash art/pipeline/run_archer_v1.sh      # iterate on the clips (diag filmstrips)
# Direction labelling as v4: d1 faces RIGHT on screen (the bow-arm side away from the camera...
# read off the renders), d5 faces left, d7 toward the camera, d3 away.
set -e
M=$HOME/medieval; cd $M
MP=$HOME/mp/bin/python
V=art/models/archer_v1; OUT=art/out/archer_v1
VID=art/source/archer/video
B="docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v $M:/work medieval-blender nice -n 10 blender --background"
LIGHT="--sun-elev 52 --sun-energy 5.0 --sun-color 1.0,0.9,0.78 --sun-angle 9 --world-strength 0.55 --world-color 0.6,0.72,0.95 --shadow-pass --shadow-samples 32 --shadow-opacity 0.4"
STAGES=${STAGES:-extract,skin,rig,bake,previews}
DRY=${DRY:-}
HEIGHT=${HEIGHT:-4.2}     # bbox height in rig units; raised above 4.2 if arrow fletching tops the bbox
has() { [[ ",$STAGES," == *",$1,"* ]]; }
mkdir -p $V/_cache $OUT/previews $OUT/motion
cp -n art/models/man_at_arms_v4/_cache/biped.glb $V/_cache/ 2>/dev/null || true

if has extract; then
echo "== 1. clips from the Veo videos"; T0=$(date +%s)
# walk: bow in the left hand (reduced swing, like the shield arm)
nice -n 10 $MP art/pipeline/video_to_clip.py extract --video $VID/veo_archer_walk.mp4 \
    --start 1.5 --end 8.0 --facing right --model $HOME/mp/models/pose_landmarker_heavy.task \
    --out $OUT/motion/walk_clip.json --previews $OUT/previews/motion_walk \
    --gain hip=1.2,knee=1.2,arm=1.2,foot=0.7,bob=1.0,torso=1.0 --shield-arm L --shield-arm-gain 0.3 \
    2>&1 | grep -v -E "^(W0|I0|INFO|WARNING)"
# shoot: ready (0.33 s, bow at the side) -> bow up, hand to the string (0.67-0.83) -> draw -> full
# draw (1.33, held in the video until 4.15) -> release at 4.29 s (impact) -> arm back (4.42) ->
# follow-through (4.75) -> bow lowered (5.0) -> synthesized return to ready. 1.5 s cycle = the
# archer's cooldown, release at phase 0.5 = frame 6 of 12. Draw arm (R, near) tracked absolute;
# bow arm (L, far) synthesized: raised to horizontal for the shot; wrist_L counter-rotates the hand
# so the bow stays vertical; the chest twists bow-shoulder forward for the front/back views.
nice -n 10 $MP art/pipeline/video_to_clip.py oneshot --video $VID/veo_archer_shoot.mp4 \
    --start 0.25 --end 5.1 --facing right --model $HOME/mp/models/pose_landmarker_heavy.task \
    --keys 0.33=0,0.67=0.14,0.83=0.22,1.33=0.38,4.15=0.46,4.29=0.50,4.42=0.56,4.75=0.68,5.0=0.78 \
    --loop --cycle 1.5 --impact-phase 0.5 \
    --gain arm=1.0,crouch=0.8,stance=1.0,foot=0.7,torso=1.0 \
    --phase-curve "upperarm_L=0:15,0.14:70,0.22:88,0.68:88,0.78:70,1:15" \
    --phase-curve "elbow_L=0:10,0.14:12,0.22:5,0.68:5,0.78:10,1:10" \
    --phase-curve "wrist_L=0:-25,0.14:-82,0.22:-93,0.68:-93,0.78:-80,1:-25" \
    --phase-curve "arm_yaw_R=0:0,0.22:10,0.38:25,0.5:25,0.56:12,0.78:4,1:0" \
    --phase-curve "chest_yaw=0:0,0.22:-14,0.5:-18,0.68:-10,1:0" \
    --phase-curve "pelvis_yaw=0:0,0.22:-4,0.5:-5,0.68:-3,1:0" \
    --arm-mode absolute --shield-mode absolute --foot-lock --head-counter 0.6 \
    --out $OUT/motion/attack_clip.json --previews $OUT/previews/motion_attack \
    2>&1 | grep -v -E "^(W0|I0|INFO|WARNING)"
# death: the hit (1.0 s, arrow in the chest, right arm thrown up) and the stagger forward (to
# 1.85 s) are tracked; the video then wanders forward and recovers upright before falling back,
# so the collapse is synthesized as in v4: knees buckle (0.50), sits back (0.66), supine (0.82).
# The bow stays in the left hand, along the arm; wrist_L lifts its forward tip during the fall so
# it does not pass through the ground, and it lies along the ground at the end.
nice -n 10 $MP art/pipeline/video_to_clip.py oneshot --video $VID/veo_archer_death.mp4 \
    --start 0.95 --end 1.9 --facing right --model $HOME/mp/models/pose_landmarker_heavy.task \
    --keys 1.0=0,1.5=0.2,1.85=0.32 --cycle 1.3 --hold-s 0.2 \
    --synth "0.50:thigh_R=65,knee_R=115,foot_R=10,thigh_L=70,knee_L=120,foot_L=10,torso=30,upperarm_R=-20,elbow_R=80" \
    --synth "0.66:thigh_R=85,knee_R=70,foot_R=30,thigh_L=88,knee_L=75,foot_L=30,torso=-40,upperarm_R=20,elbow_R=20" \
    --synth "0.82:thigh_R=88,knee_R=6,foot_R=70,thigh_L=90,knee_L=8,foot_L=70,torso=-86,upperarm_R=95,elbow_R=10" \
    --synth "1.0:thigh_R=hold" \
    --gain arm=1.0,crouch=1.0,foot=0.7,torso=1.0 \
    --phase-curve "upperarm_L=0:20,0.32:30,0.5:35,0.66:45,0.82:80,1:80" \
    --phase-curve "elbow_L=0:10,0.32:15,0.5:15,0.66:10,0.82:5,1:5" \
    --phase-curve "wrist_L=0:0,0.32:0,0.5:30,0.66:60,0.82:25,1:25" \
    --phase-curve "root_fwd=0:0,0.32:0,0.5:-0.1,0.66:-0.2,0.82:-0.25,1:-0.25" \
    --arm-mode absolute --shield-mode absolute --foot-lock --foot-lock-until 0.32 --head-counter 0.0 \
    --out $OUT/motion/death_clip.json --previews $OUT/previews/motion_death \
    2>&1 | grep -v -E "^(W0|I0|INFO|WARNING)"
echo "   extract: $(( $(date +%s) - T0 ))s"
fi

if has skin; then
# TRELLIS paints the bare hands and face a saturated orange (the gloved man-at-arms never showed
# skin); pull the skin hue band's saturation down on both team textures. The merge outputs stay in
# $V/alt/ (archer_<team>_merge.glb); the recoloured GLBs are what the rig uses.
echo "== 1b. skin tone"; T0=$(date +%s)
mkdir -p $V/alt
for team in blue red; do
    [ -f $V/alt/archer_${team}_merge.glb ] || cp $V/archer_$team.glb $V/alt/archer_${team}_merge.glb
    nice -n 10 $MP art/pipeline/recolor_glb.py --in $V/alt/archer_${team}_merge.glb --out $V/archer_$team.glb \
        --hue 12,28 --feather 4 --target-hue 20 --sat-mul ${SKIN_SAT:-0.62} --sat-min 0 --val-mul 1.0 --val-max 1.0 \
        --mask-sat 0.42,0.58 --mask-sat-max 0.70,0.82 \
        --preview $OUT/previews/skin_recolor_$team.png
done
echo "   skin: $(( $(date +%s) - T0 ))s"
fi

if has rig; then
echo "== 2. rig (idle .dae first: the bow is placed at its frame 1)"; T0=$(date +%s)
$B --python art/pipeline/rig_body.py -- \
    --body $V/archer_blue.glb --alt red=$V/archer_red.glb --sword none --height $HEIGHT \
    --clip idle=art/source/zeroad_clips/biped/citizen/idle_relax_f.dae \
    --clip walk=$OUT/motion/walk_clip.json --clip attack=$OUT/motion/attack_clip.json \
    --clip death=$OUT/motion/death_clip.json \
    --prop "name=bow;bone=Biped_hand_L;pos=${BOW_POS:-0,-0.05,-0.1};dir=${BOW_DIR:-0,-0.22,1};edge=0,-1,0;size=4.0" \
    --out $V/archer_rig.blend --diag $OUT/previews/rig_diag --strip-frames 12 \
    2>&1 | grep -E "^==|^   (rest|ground|frame|props|prop|strip|clip|   frame)|Traceback|Error"
echo "   rig: $(( $(date +%s) - T0 ))s"
fi

if has bake; then
echo "== 3. bake"; T0=$(date +%s)
rm -rf $OUT/sprites $OUT/sprites@2x $OUT/_tiles
$B $V/archer_rig.blend --python art/pipeline/bake_sprites.py -- \
    --name archer --teams blue,red --clip idle=6:${CELL_IDLE:-72} --clip walk=12:${CELL_WALK:-72} \
    --clip attack=12:${CELL_ATTACK:-96} --clip death=12:${CELL_DEATH:-88} \
    --size 72 --supersample 2 --out $OUT --px-per-unit 14.34 $DRY \
    $LIGHT --contrast 0.35 2>&1 | grep -E "^==|span|clip |prop|wrote|Traceback|Error"
echo "   bake: $(( $(date +%s) - T0 ))s"
fi

if has previews; then
echo "== 4. previews"; T0=$(date +%s)
[ -f $OUT/previews/body_textured.png ] || \
$B --python art/pipeline/preview_models.py -- --out $OUT/previews/body_textured.png --size 512 --samples 48 \
    --views "front,3/4,side,back" --mesh "blue team=$V/archer_blue.glb" --mesh "red team=$V/archer_red.glb" 2>&1 | tail -1
python3 art/pipeline/contact_sheet.py --name archer --out $OUT/previews/contact_sheet.png \
    --turnaround $OUT/previews/body_textured.png --rows "blue team,red team" --sprites $OUT/sprites
for clip in attack death; do
    python3 art/pipeline/clip_contact.py --name archer --sprites $OUT/sprites --clip $clip --out $OUT/previews/${clip}_contact.png
done
for team in blue red; do
    for clip in idle walk attack death; do
        python3 art/pipeline/walk_gif.py --sprites $OUT/sprites --name archer --team $team --clip $clip \
            --dirs 1,0,7 --zoom 3 --out $OUT/previews/${clip}_$team.gif
    done
done
python3 art/pipeline/lineup.py --out $OUT/previews/lineup.png \
    --unit "man_at_arms=art/out/man_at_arms_v4/sprites@2x" --unit "archer=$OUT/sprites@2x" || true
echo "   previews: $(( $(date +%s) - T0 ))s"
fi
echo "DONE run_archer_v1"
