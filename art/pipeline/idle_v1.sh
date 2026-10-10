#!/bin/bash
# Keyed standing idle shared by every biped unit (replaces the 0 A.D. idle_relax clips in the bake).
#   bash art/pipeline/idle_v1.sh <unit walk_clip.json> <out idle_clip.json>
# The unit's own walk clip is the base only for its retarget block (relative arms, so the sword,
# shield, bow or empty hands keep the carriage they were placed with); every curve is replaced.
# 3.6 s loop: weight on the right leg with the left knee eased (0-0.3), shift onto the left leg
# (0.3-0.45), held (to 0.8), back (0.8-0.95); the pelvis turns a little with the shift and the
# chest counters it; two breaths (chest pitch and a slight lift of the arms); one glance to the
# side and back (head_yaw, 0.5-0.85). The eased leg's thigh comes forward as its knee bends so its
# ankle stays put; feet planted (foot lock), ground clamp as every clip.
set -e
PY=${PY:-python3}
$PY art/pipeline/derive_clip.py --base "$1" --out "$2" --hold-phase 0 --cycle ${IDLE_CYCLE:-3.6} --loop \
    --curve "thigh_R=0:4,0.3:4,0.45:7.5,0.8:7.5,0.95:4,1:4" \
    --curve "knee_R=0:0,0.3:0,0.45:7,0.8:7,0.95:0,1:0" \
    --curve "foot_R=0:0,0.3:0,0.45:-4,0.8:-4,0.95:0,1:0" \
    --curve "thigh_L=0:-1,0.3:-1,0.45:-4.5,0.8:-4.5,0.95:-1,1:-1" \
    --curve "knee_L=0:7,0.3:7,0.45:0,0.8:0,0.95:7,1:7" \
    --curve "foot_L=0:-4,0.3:-4,0.45:0,0.8:0,0.95:-4,1:-4" \
    --curve "torso=0:0,0.25:1.5,0.5:0,0.75:1.5,1:0" \
    --curve "pelvis_yaw=0:2,0.3:2,0.45:-2,0.8:-2,0.95:2,1:2" \
    --curve "chest_yaw=0:-1,0.3:-1,0.45:1.5,0.8:1.5,0.95:-1,1:-1" \
    --curve "head_yaw=0:0,0.5:0,0.6:${IDLE_GLANCE:-16},0.75:${IDLE_GLANCE:-16},0.85:0,1:0" \
    --curve "upperarm_R=0:0,0.25:2,0.5:0,0.75:2,1:0" --curve "elbow_R=0:0,0.25:4,0.5:0,0.75:4,1:0" \
    --curve "upperarm_L=0:0,0.25:2,0.5:0,0.75:2,1:0" --curve "elbow_L=0:0,0.25:4,0.5:0,0.75:4,1:0" \
    --set retarget.foot_lock=true
