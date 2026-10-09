#!/bin/bash
# v4 man-at-arms on the Spark: v3's models + walk, plus an ATTACK and a DEATH clip from two more
# Veo side-view videos (video_to_clip.py oneshot mode), everything re-rendered into one manifest
# (idle 6, walk 12, attack 10, death 12 frames x 8 directions x 2 teams). Same camera, lighting,
# contrast, footprint and framing conventions as v3; the shared scale is pinned to v3's
# 14.34 px/unit so idle/walk sprites stay pixel-identical in size (bake_sprites.py reports the
# tightest cell margin per clip). Everything niced; vLLM shares the box. Run from the mirror:
#   cd ~/medieval && bash art/pipeline/run_v4.sh 2>&1 | tee run_v4.log
#   STAGES=extract,rig bash art/pipeline/run_v4.sh      # iterate on the clips (diag filmstrips)
# Prerequisites: as run_v3.sh (~/mp venv + pose_landmarker_heavy.task, medieval-blender image) and
# v3's models in art/models/man_at_arms_v3 (copied, nothing is re-generated or recoloured).
#
# Direction labelling (read off the renders, do not trust the v2 table): d1 shows the sword side
# so he faces RIGHT on screen, d5 shows the shield side (faces LEFT), d7 faces the camera, d3
# faces away; the even directions are the diagonals between them.
set -e
M=$HOME/medieval; cd $M
MP=$HOME/mp/bin/python
V3=art/models/man_at_arms_v3; V4=art/models/man_at_arms_v4; OUT=art/out/man_at_arms_v4
VID=art/source/man_at_arms/video
B="docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v $M:/work medieval-blender nice -n 10 blender --background"
LIGHT="--sun-elev 52 --sun-energy 5.0 --sun-color 1.0,0.9,0.78 --sun-angle 9 --world-strength 0.55 --world-color 0.6,0.72,0.95 --shadow-pass --shadow-samples 32 --shadow-opacity 0.4"
STAGES=${STAGES:-extract,rig,bake,previews}
DRY=${DRY:-}            # DRY=--dry-run: bake reports scale/margins only
has() { [[ ",$STAGES," == *",$1,"* ]]; }
mkdir -p $V4/_cache $OUT/previews $OUT/motion
cp -n $V3/_cache/*.glb $V4/_cache/ 2>/dev/null || true
cp -n $V3/man_at_arms_blue.glb $V3/man_at_arms_red.glb $V3/shield_blue.glb $V3/shield_red.glb $V4/ 2>/dev/null || true

if has extract; then
echo "== 1. clips from the Veo videos"; T0=$(date +%s)
# walk: as v3 (re-extracted here so v4 is self-contained)
nice -n 10 $MP art/pipeline/video_to_clip.py extract --video $VID/veo_walk_side.mp4 \
    --start 1.5 --end 8.0 --facing right --model $HOME/mp/models/pose_landmarker_heavy.task \
    --out $OUT/motion/walk_clip.json --previews $OUT/previews/motion_walk \
    --gain hip=1.2,knee=1.2,arm=1.2,foot=0.7,bob=1.0,torso=1.0 --shield-arm L --shield-arm-gain 0.3 \
    2>&1 | grep -v -E "^(W0|I0|INFO|WARNING)"
# attack: guard (0.95 s) -> sword raised (1.1) -> wind-up top (2.05, held in the video) -> swing
# starts (2.30) -> impact (2.54, arm extended forward-down) -> follow-through (3.0) -> synthesized
# recovery to the guard. 1.0 s cycle = the unit's attack cooldown; impact at phase 0.5 = frame 5
# of 10. Legs: both as tracked (a lunge), crouch eased to 0.75 so the stance stays near the idle
# height; feet planted by the foot lock. Sword arm: absolute planar angles, wrist pitch synthesized
# (blade back over the shoulder at the top, leading forward-down at impact), arm swung outward
# during the wind-up for the front/back views; torso twist synthesized; shield arm raised in front.
nice -n 10 $MP art/pipeline/video_to_clip.py oneshot --video $VID/veo_attack_side.mp4 \
    --start 0.85 --end 3.05 --facing right --model $HOME/mp/models/pose_landmarker_heavy.task \
    --keys 0.95=0,1.1=0.14,2.05=0.30,2.30=0.36,2.54=0.50,3.0=0.64 --loop --cycle 1.0 --impact-phase 0.5 \
    --synth "0.82:upperarm_R=15,elbow_R=110" \
    --gain arm=1.0,crouch=0.75,stance=0.8,foot=0.7,torso=1.0 \
    --phase-curve "wrist_R=0:40,0.14:20,0.25:85,0.30:95,0.36:80,0.5:5,0.64:10,0.82:35,1:40" \
    --phase-curve "arm_yaw_R=0:0,0.2:12,0.30:18,0.40:10,0.5:15,0.64:10,1:0" \
    --phase-curve "chest_yaw=0:0,0.30:-14,0.36:-14,0.5:8,0.64:5,1:0" \
    --phase-curve "pelvis_yaw=0:0,0.30:-5,0.36:-5,0.5:3,0.64:2,1:0" \
    --phase-curve "upperarm_L=0:35,0.30:45,0.5:35,0.64:30,1:35" --phase-curve "elbow_L=0:15,1:15" \
    --arm-mode absolute --shield-mode offset --foot-lock --head-counter 0.6 \
    --out $OUT/motion/attack_clip.json --previews $OUT/previews/motion_attack \
    2>&1 | grep -v -E "^(W0|I0|INFO|WARNING)"
# death: the hit reaction (1.25-1.95 s, doubles over in profile) is tracked; everything after it
# in the video is a turn to camera, so the collapse is synthesized: the knees buckle into a deep
# squat (0.50), he sits back and falls (0.66) and lands supine, head behind, feet forward (0.82),
# the pose the video ends in (6-8 s). The sword stays in the hand, lifted clear of the ground by
# a wrist curve during the stagger and lying along the ground at the end. Non-looping, 1.3 s +
# 0.2 s hold of the final frame.
nice -n 10 $MP art/pipeline/video_to_clip.py oneshot --video $VID/veo_death_side.mp4 \
    --start 1.2 --end 2.0 --facing right --model $HOME/mp/models/pose_landmarker_heavy.task \
    --keys 1.25=0,1.95=0.32 --cycle 1.3 --hold-s 0.2 \
    --synth "0.50:thigh_R=65,knee_R=115,foot_R=10,thigh_L=70,knee_L=120,foot_L=10,torso=30,upperarm_R=-20,elbow_R=80" \
    --synth "0.66:thigh_R=85,knee_R=70,foot_R=30,thigh_L=88,knee_L=75,foot_L=30,torso=-40,upperarm_R=20,elbow_R=20" \
    --synth "0.82:thigh_R=88,knee_R=6,foot_R=70,thigh_L=90,knee_L=8,foot_L=70,torso=-86,upperarm_R=95,elbow_R=10" \
    --synth "1.0:thigh_R=hold" \
    --gain arm=1.0,crouch=1.0,foot=0.7,torso=1.0 \
    --phase-curve "wrist_R=0:-50,0.32:-50,0.5:30,0.66:50,0.82:0,1:0" \
    --phase-curve "upperarm_L=0:20,0.32:25,0.5:30,0.66:45,0.82:80,1:80" \
    --phase-curve "elbow_L=0:60,0.32:60,0.5:50,0.66:45,0.82:45,1:45" \
    --phase-curve "root_fwd=0:0,0.32:0,0.5:-0.1,0.66:-0.2,0.82:-0.25,1:-0.25" \
    --arm-mode absolute --shield-mode absolute --foot-lock --foot-lock-until 0.32 --head-counter 0.0 \
    --out $OUT/motion/death_clip.json --previews $OUT/previews/motion_death \
    2>&1 | grep -v -E "^(W0|I0|INFO|WARNING)"
echo "   extract: $(( $(date +%s) - T0 ))s"
fi

if has rig; then
echo "== 2. rig (idle .dae first: the props are placed at its frame 1)"; T0=$(date +%s)
$B --python art/pipeline/rig_body.py -- \
    --body $V4/man_at_arms_blue.glb --alt red=$V4/man_at_arms_red.glb \
    --shield $V4/shield_blue.glb --shield-alt red=$V4/shield_red.glb \
    --clip idle=art/source/zeroad_clips/biped/infantry/swordsman/idle_relax_shield_01.dae \
    --clip walk=$OUT/motion/walk_clip.json --clip attack=$OUT/motion/attack_clip.json \
    --clip death=$OUT/motion/death_clip.json \
    --sword-length 2.0 --sword-blade-w 0.11 --sword-guard-w 0.40 --sword-dir 0,0.15,-1 \
    --out $V4/man_at_arms_rig.blend --diag $OUT/previews/rig_diag --strip-frames 12 \
    2>&1 | grep -E "^==|^   (rest|ground|frame|props|strip|   frame)|Traceback|Error"
echo "   rig: $(( $(date +%s) - T0 ))s"
fi

if has bake; then
echo "== 3. bake"; T0=$(date +%s)
rm -rf $OUT/sprites $OUT/sprites@2x $OUT/_tiles
$B $V4/man_at_arms_rig.blend --python art/pipeline/bake_sprites.py -- \
    --name man_at_arms --teams blue,red --clip idle=6 --clip walk=12 --clip attack=10:88 --clip death=12:88 \
    --size 72 --supersample 2 --out $OUT --px-per-unit 14.34 $DRY \
    $LIGHT --contrast 0.35 2>&1 | grep -E "^==|span|clip |sword tip|wrote|Traceback|Error"
echo "   bake: $(( $(date +%s) - T0 ))s"
fi

if has previews; then
echo "== 4. previews"; T0=$(date +%s)
cp -n art/out/man_at_arms_v3/previews/body_textured.png $OUT/previews/ 2>/dev/null || \
$B --python art/pipeline/preview_models.py -- --out $OUT/previews/body_textured.png --size 512 --samples 48 \
    --views "front,3/4,side,back" --mesh "blue team=$V4/man_at_arms_blue.glb" --mesh "red team=$V4/man_at_arms_red.glb" 2>&1 | tail -1
python3 art/pipeline/contact_sheet.py --name man_at_arms --out $OUT/previews/contact_sheet.png \
    --turnaround $OUT/previews/body_textured.png --rows "blue team,red team" --sprites $OUT/sprites
python3 art/pipeline/clip_contact.py --name man_at_arms --sprites $OUT/sprites --clip attack \
    --out $OUT/previews/attack_contact.png
python3 art/pipeline/clip_contact.py --name man_at_arms --sprites $OUT/sprites --clip death \
    --out $OUT/previews/death_contact.png
python3 art/pipeline/compare_sprites.py --name man_at_arms --a "v3=art/out/man_at_arms_v3/sprites" --b "v4=$OUT/sprites" \
    --walk-dirs 0,1,7 --out $OUT/previews/compare_v3_v4.png
for team in blue red; do
    for clip in walk attack death; do
        python3 art/pipeline/walk_gif.py --sprites $OUT/sprites --name man_at_arms --team $team --clip $clip \
            --dirs 1,0,7 --zoom 3 --out $OUT/previews/${clip}_$team.gif
    done
done
echo "   previews: $(( $(date +%s) - T0 ))s"
fi
echo "DONE run_v4"
