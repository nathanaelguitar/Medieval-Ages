#!/bin/bash
# Villagers v1 (male + female) on the Spark: TRELLIS.2 bodies (trellis_units_v1.sh, run first),
# one walk per villager from their own Veo video, and work clips shared by both (chop, mine, hoe,
# berries from Veo; build derived from chop; death = the man-at-arms v4 death retargeted), with
# procedural tools shown only in their clip. Same camera / lighting / contrast / scale as v4.
#   cd ~/medieval && bash art/pipeline/run_villagers_v1.sh 2>&1 | tee art/out/villager_male_v1/run_villagers_v1.log
#   STAGES=extract bash ...; UNITS=villager_m STAGES=rig,bake ...
set -e
M=$HOME/medieval; cd $M
MP=$HOME/mp/bin/python
VID=art/source/villager/video
SH=art/out/villager_shared/motion            # work clips shared by both villagers
B="docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v $M:/work medieval-blender nice -n 10 blender --background"
LIGHT="--sun-elev 52 --sun-energy 5.0 --sun-color 1.0,0.9,0.78 --sun-angle 9 --world-strength 0.55 --world-color 0.6,0.72,0.95 --shadow-pass --shadow-samples 32 --shadow-opacity 0.4"
STAGES=${STAGES:-extract,rig,bake,previews}
UNITS=${UNITS:-villager_m,villager_f}
DRY=${DRY:-}
has() { [[ ",$STAGES," == *",$1,"* ]]; }
hasu() { [[ ",$UNITS," == *",$1,"* ]]; }
MPX() { nice -n 10 $MP art/pipeline/video_to_clip.py "$@" 2>&1 | grep -v -E "^(W0|I0|INFO|WARNING)"; }
MODEL=$HOME/mp/models/pose_landmarker_heavy.task
mkdir -p $SH art/out/villager_shared/previews

if has extract; then
echo "== 1. clips from the Veo videos"; T0=$(date +%s)
for u in villager_m:male villager_f:female; do
    unit=${u%%:*}; sex=${u##*:}
    hasu $unit || continue
    OUT=${unit/villager_m/villager_male}; OUT=art/out/${OUT/villager_f/villager_female}_v1
    mkdir -p $OUT/motion $OUT/previews
    # the woman's video swings the arms far more than the man's; her gain is halved so the
    # sprite does not march with the arms out horizontal
    armg=1.2; [ $sex = female ] && armg=${ARM_GAIN_F:-0.55}
    MPX extract --video $VID/veo_${sex}_walk.mp4 --start 1.5 --end 8.0 --facing right --model $MODEL \
        --out $OUT/motion/walk_clip.json --previews $OUT/previews/motion_walk \
        --gain hip=1.2,knee=1.2,arm=$armg,foot=0.7,bob=1.0,torso=1.0 --shield-arm none
done
# chop: the third stroke of the video (the first 2 s are the axe pick-up). Phase 0 = axe raised
# overhead (6.2 s), swing forward (6.45), impact 6.6 s (phase 0.4), follow-through low (6.9),
# lifting again (7.2), synthesized return to the raised start. Both hands on the haft: the far arm
# copies the near arm. Tracked timings read off previews/motion_chop/joint_angles.png.
MPX oneshot --video $VID/veo_chop.mp4 --start 6.0 --end 7.4 --facing right --model $MODEL \
    --keys 6.2=0,6.45=0.3,6.6=0.4,6.9=0.55,7.2=0.8 --loop --cycle 1.3 --impact-phase 0.4 \
    --gain arm=1.0,crouch=0.8,stance=1.0,foot=0.7,torso=1.0 --far-arm copy --far-arm-offset 0,0 \
    --phase-curve "wrist_R=${CHOP_WRIST:-0:35,0.3:10,0.4:0,0.55:-10,0.8:20,1:35}" \
    --arm-mode absolute --shield-mode absolute --foot-lock --head-counter 0.5 \
    --out $SH/chop_clip.json --previews art/out/villager_shared/previews/motion_chop
# mine: third strike (the spark burst at 4.5 s is avoided). Phase 0 = pick being lifted (6.0 s),
# overhead (6.5), coming down (6.9), strike low on the rock (7.1, impact at phase 0.7, the arm minimum: frame 8
# of 12), synthesized lift back to the start.
MPX oneshot --video $VID/veo_mine.mp4 --start 5.9 --end 7.3 --facing right --model $MODEL \
    --keys 6.0=0,6.5=0.3,6.9=0.55,7.1=0.7 --loop --cycle 1.3 --impact-phase 0.7 \
    --gain arm=1.0,crouch=0.8,stance=1.0,foot=0.7,torso=1.0 --far-arm copy --far-arm-offset 0,0 \
    --phase-curve "wrist_R=${MINE_WRIST:-0:15,0.3:35,0.6:0,0.7:-10,1:15}" \
    --arm-mode absolute --shield-mode absolute --foot-lock --head-counter 0.5 \
    --out $SH/mine_clip.json --previews art/out/villager_shared/previews/motion_mine
# hoe: the big stroke at 2-4 s (the later strokes stay low and read as raking): hoe low in front
# (2.1), lifted (2.6), top (2.9), swung down (3.25), blade into the soil (3.5, impact), low (4.0).
# The hoe is pitched up 30 deg from the forearm line and wrist_R keeps its blade at ground level.
MPX oneshot --video $VID/veo_hoe.mp4 --start 2.0 --end 4.1 --facing right --model $MODEL \
    --keys 2.1=0,2.6=0.25,2.9=0.38,3.25=0.5,3.5=0.6,4.0=0.85 --loop --cycle 1.3 --impact-phase 0.6 \
    --gain arm=1.0,crouch=0.8,stance=1.0,foot=0.7,torso=1.0 --far-arm copy --far-arm-offset 0,0 \
    --phase-curve "wrist_R=${HOE_WRIST:-0:12,0.38:0,0.6:15,0.85:12,1:12}" \
    --arm-mode absolute --shield-mode absolute --foot-lock --head-counter 0.5 \
    --out $SH/hoe_clip.json --previews art/out/villager_shared/previews/motion_hoe
# berries: reach into the bush (3.5), pick (4.0, impact), hand to the basket (4.5), drop (5.0),
# still at the basket (5.4), reaching again (5.8). The basket hangs from the left forearm (synthesized).
MPX oneshot --video $VID/veo_berries.mp4 --start 3.4 --end 5.9 --facing right --model $MODEL \
    --keys 3.5=0,4.0=0.25,4.5=0.5,5.0=0.65,5.4=0.78,5.8=0.9 --loop --cycle 1.6 --impact-phase 0.25 \
    --gain arm=1.0,crouch=1.0,stance=1.0,foot=0.7,torso=1.0 \
    --phase-curve "upperarm_L=0:25,1:25" --phase-curve "elbow_L=0:85,1:85" \
    --arm-mode absolute --shield-mode absolute --foot-lock --head-counter 0.5 \
    --out $SH/berries_clip.json --previews art/out/villager_shared/previews/motion_berries
# build (hammer): no video. The chop stance held at its raised phase, right arm hand-keyed:
# hammer up by the shoulder, strike forward at chest height, 0.6 s per blow (impact at phase 0.5);
# left arm hanging.
python3 art/pipeline/derive_clip.py --base $SH/chop_clip.json --out $SH/build_clip.json \
    --cycle 0.6 --loop --impact-phase 0.5 --hold-phase 0.0 \
    --curve "upperarm_R=${BUILD_UA:-0:100,0.5:62,1:100}" --curve "elbow_R=${BUILD_EL:-0:95,0.5:35,1:95}" \
    --curve "wrist_R=${BUILD_WRIST:-0:0,1:0}" --curve "arm_yaw_R=0:0,1:0" \
    --curve "upperarm_L=0:12,1:12" --curve "elbow_L=0:20,1:20" \
    --curve "torso=${BUILD_TORSO:-0:4,0.5:10,1:4}" --set retarget.foot_lock=false
# death: the man-at-arms v4 death retargeted as-is (same skeleton), no props
cp art/out/man_at_arms_v4/motion/death_clip.json $SH/death_clip.json
echo "   extract: $(( $(date +%s) - T0 ))s"
fi

for u in villager_m:male:${HEIGHT_M:-4.05} villager_f:female:${HEIGHT_F:-3.9}; do
    IFS=: read unit sex height <<< "$u"
    hasu $unit || continue
    V=art/models/${unit}_v1
    OUT=${unit/villager_m/villager_male}; OUT=art/out/${OUT/villager_f/villager_female}_v1
    mkdir -p $V/_cache $OUT/previews
    cp -n art/models/man_at_arms_v4/_cache/biped.glb $V/_cache/ 2>/dev/null || true
    if has rig; then
    echo "== 2. rig $unit"; T0=$(date +%s)
    # carry (optional): the walk with the left arm raised (offset from the idle pose) holding a log
    python3 art/pipeline/derive_clip.py --base $OUT/motion/walk_clip.json --out $OUT/motion/carry_clip.json \
        --set retarget.shield_mode=offset --curve "upperarm_L=0:30,1:30" --curve "elbow_L=0:100,1:100"
    $B --python art/pipeline/rig_body.py -- \
        --body $V/${unit}_blue.glb --alt red=$V/${unit}_red.glb --sword none --height $height \
        --clip idle=art/source/zeroad_clips/biped/citizen/idle_relax_f.dae \
        --clip walk=$OUT/motion/walk_clip.json \
        --clip chop=$SH/chop_clip.json --clip mine=$SH/mine_clip.json --clip hoe=$SH/hoe_clip.json \
        --clip berries=$SH/berries_clip.json --clip build=$SH/build_clip.json --clip death=$SH/death_clip.json \
        --clip carry=$OUT/motion/carry_clip.json \
        --prop "name=axe;bone=Biped_hand_R;clips=chop;at=chop:0.4;dir=hand;pitch=${AXE_PITCH:-0};edge=${AXE_EDGE:-0,1,0};size=2.0" \
        --prop "name=pickaxe;bone=Biped_hand_R;clips=mine;at=mine:0.4;dir=hand;pitch=${PICK_PITCH:-0};edge=${PICK_EDGE:-0,1,0};size=2.0" \
        --prop "name=hoe;bone=Biped_hand_R;clips=hoe;at=hoe:0.25;dir=hand;pitch=${HOE_PITCH:-30};edge=${HOE_EDGE:-0,1,0};size=3.3" \
        --prop "name=hammer;bone=Biped_hand_R;clips=build;at=build:0.5;dir=${HAMMER_DIR:-0,0,1};edge=${HAMMER_EDGE:-0,-1,0};size=0.85" \
        --prop "name=log;bone=Biped_forearm_L;clips=carry;at=carry:0;along=0.5;pos=${LOG_POS:-0,0,-0.28};dir=0,-1,0.15;edge=0,0,1;size=1.6" \
        --prop "name=basket;bone=Biped_forearm_L;clips=berries;at=berries:0;along=0.55;pos=${BASKET_POS:-0,0,0.05};dir=0,0,-1;edge=1,0,0;size=0.9" \
        --out $V/${unit}_rig.blend --diag $OUT/previews/rig_diag --strip-frames 12 \
        2>&1 | grep -E "^==|^   (rest|ground|frame|props|prop|strip|clip|   frame)|Traceback|Error"
    echo "   rig: $(( $(date +%s) - T0 ))s"
    fi
    if has bake; then
    echo "== 3. bake $unit"; T0=$(date +%s)
    rm -rf $OUT/sprites $OUT/sprites@2x $OUT/_tiles
    $B $V/${unit}_rig.blend --python art/pipeline/bake_sprites.py -- \
        --name $unit --teams blue,red --clip idle=6:72 --clip walk=12:72 \
        --clip chop=12:${CELL_CHOP:-96} --clip mine=12:${CELL_MINE:-96} --clip hoe=12:${CELL_HOE:-96} \
        --clip berries=12:${CELL_BERRIES:-80} --clip build=8:${CELL_BUILD:-80} --clip death=12:${CELL_DEATH:-88} \
        --clip carry=12:${CELL_CARRY:-72} \
        --size 72 --supersample 2 --out $OUT --px-per-unit 14.34 $DRY \
        $LIGHT --contrast 0.35 2>&1 | grep -E "^==|span|clip |prop|wrote|Traceback|Error"
    echo "   bake: $(( $(date +%s) - T0 ))s"
    fi
    if has previews; then
    echo "== 4. previews $unit"; T0=$(date +%s)
    [ -f $OUT/previews/body_textured.png ] || \
    $B --python art/pipeline/preview_models.py -- --out $OUT/previews/body_textured.png --size 512 --samples 48 \
        --views "front,3/4,side,back" --mesh "blue team=$V/${unit}_blue.glb" --mesh "red team=$V/${unit}_red.glb" 2>&1 | tail -1
    python3 art/pipeline/contact_sheet.py --name $unit --out $OUT/previews/contact_sheet.png \
        --turnaround $OUT/previews/body_textured.png --rows "blue team,red team" --sprites $OUT/sprites
    for clip in chop mine hoe berries build death carry; do
        python3 art/pipeline/clip_contact.py --name $unit --sprites $OUT/sprites --clip $clip --out $OUT/previews/${clip}_contact.png
    done
    for team in blue red; do
        for clip in idle walk chop mine hoe berries build death carry; do
            python3 art/pipeline/walk_gif.py --sprites $OUT/sprites --name $unit --team $team --clip $clip \
                --dirs 1,0,7 --zoom 3 --out $OUT/previews/${clip}_$team.gif
        done
    done
    echo "   previews: $(( $(date +%s) - T0 ))s"
    fi
done
if has previews; then
python3 art/pipeline/lineup.py --out art/out/villager_male_v1/previews/lineup.png \
    --unit "man_at_arms=art/out/man_at_arms_v4/sprites@2x" --unit "archer=art/out/archer_v1/sprites@2x" \
    --unit "villager_m=art/out/villager_male_v1/sprites@2x" --unit "villager_f=art/out/villager_female_v1/sprites@2x" || true
fi
echo "DONE run_villagers_v1"
