/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef OE_TOUCH_H
#define OE_TOUCH_H
#include <stdbool.h>
#include <stdint.h>

/* Platform-independent input. UIKit coordinates are converted before entry. */
typedef enum { OE_SELECT, OE_COMMAND, OE_PAN } OEMode;
typedef enum { OE_MOVE, OE_LEFT_DOWN, OE_LEFT_UP, OE_RIGHT_DOWN,
               OE_RIGHT_UP, OE_CANCEL } OEEventKind;
typedef struct { OEEventKind kind; double x, y; } OEEvent;
typedef struct {
    bool active;
    int64_t id;
    double x, y, start_x, start_y, began;
} OEFinger;
#define OE_TOUCH_QUEUE_CAPACITY 128

typedef struct {
    OEMode mode;
    OEFinger fingers[2];
    bool multiple, dragging;
    double x, y, pan_x, pan_y;
    bool left, right;
    OEEvent queue[OE_TOUCH_QUEUE_CAPACITY];
    unsigned head, count, overflow_count;
} OETouch;

typedef struct {
    double x, y;
    bool left, right, left_down, left_up, right_down, right_up, cancelled;
} OETouchSample;

void OETouch_Init(OETouch *touch);
void OETouch_Cancel(OETouch *touch);
void OETouch_SetMode(OETouch *touch, OEMode mode);
void OETouch_Begin(OETouch *touch, int64_t finger, double x, double y, double time);
void OETouch_Move(OETouch *touch, int64_t finger, double x, double y);
void OETouch_End(OETouch *touch, int64_t finger, double x, double y, double time);
/* One event per simulation step preserves quick down/up pairs. */
OETouchSample OETouch_Next(OETouch *touch);
void OETouch_TakePan(OETouch *touch, double *x, double *y);
#endif
