/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "OETouch.h"
#include <math.h>
#include <string.h>

static int slot(const OETouch *t, int64_t id) {
    for (int i = 0; i < 2; ++i)
        if (t->fingers[i].active && t->fingers[i].id == id) return i;
    return -1;
}
static int count(const OETouch *t) {
    return (int)t->fingers[0].active + (int)t->fingers[1].active;
}
static void push(OETouch *t, OEEventKind kind, double x, double y) {
    /* Coalesce motion, never button transitions. Overflow cancels, not clicks. */
    if (kind == OE_MOVE && t->count) {
        unsigned last = (t->head + t->count - 1) % OE_TOUCH_QUEUE_CAPACITY;
        if (t->queue[last].kind == OE_MOVE) {
            t->queue[last] = (OEEvent){kind, x, y};
            return;
        }
    }
    if (t->count == OE_TOUCH_QUEUE_CAPACITY) {
        ++t->overflow_count;
        OETouch_Cancel(t);
        return;
    }
    unsigned next = (t->head + t->count++) % OE_TOUCH_QUEUE_CAPACITY;
    t->queue[next] = (OEEvent){kind, x, y};
}
void OETouch_Init(OETouch *t) { memset(t, 0, sizeof(*t)); }
void OETouch_Cancel(OETouch *t) {
    OEMode mode = t->mode;
    unsigned overflows = t->overflow_count;
    double x = t->x, y = t->y;
    memset(t, 0, sizeof(*t));
    t->mode = mode;
    t->overflow_count = overflows;
    t->x = x; t->y = y;
    t->queue[0] = (OEEvent){OE_CANCEL, x, y};
    t->count = 1;
}
void OETouch_SetMode(OETouch *t, OEMode mode) {
    OETouch_Cancel(t);
    t->mode = mode;
}
void OETouch_Begin(OETouch *t, int64_t id, double x, double y, double time) {
    if (!isfinite(x) || !isfinite(y) || !isfinite(time) || slot(t, id) >= 0) return;
    int n = count(t);
    if (n == 2) return;
    int i = t->fingers[0].active ? 1 : 0;
    t->fingers[i] = (OEFinger){true, id, x, y, x, y, time};
    if (n == 0) {
        t->multiple = false;
        t->dragging = false;
        push(t, OE_MOVE, x, y);
    } else {
        /* A second finger cancels a selection without manufacturing mouse-up. */
        t->multiple = true;
        t->dragging = false;
        t->head = t->count = 0;
        push(t, OE_CANCEL, x, y);
    }
}
void OETouch_Move(OETouch *t, int64_t id, double x, double y) {
    int i = slot(t, id);
    if (i < 0 || !isfinite(x) || !isfinite(y)) return;
    OEFinger *f = &t->fingers[i];
    double dx = x - f->x, dy = y - f->y;
    f->x = x; f->y = y;
    if (t->multiple) {
        if (count(t) == 2) { t->pan_x += dx / 2.0; t->pan_y += dy / 2.0; }
        return;
    }
    if (t->mode == OE_PAN) { t->pan_x += dx; t->pan_y += dy; return; }
    dx = x - f->start_x; dy = y - f->start_y;
    if (t->mode == OE_SELECT && !t->dragging && dx * dx + dy * dy >= 64.0) {
        t->dragging = true;
        push(t, OE_LEFT_DOWN, f->start_x, f->start_y);
    }
    push(t, OE_MOVE, x, y);
}
void OETouch_End(OETouch *t, int64_t id, double x, double y, double time) {
    int i = slot(t, id);
    if (i < 0) return;
    if (!isfinite(x) || !isfinite(y) || !isfinite(time)) { OETouch_Cancel(t); return; }
    OETouch_Move(t, id, x, y);
    OEFinger f = t->fingers[i];
    if (!t->multiple && t->mode != OE_PAN) {
        if (t->dragging) push(t, OE_LEFT_UP, x, y);
        else if (t->mode == OE_COMMAND || time - f.began >= 0.45) {
            push(t, OE_RIGHT_DOWN, x, y);
            push(t, OE_RIGHT_UP, x, y);
        } else {
            push(t, OE_LEFT_DOWN, x, y);
            push(t, OE_LEFT_UP, x, y);
        }
    }
    t->fingers[i].active = false;
    if (count(t) == 0) { t->multiple = false; t->dragging = false; }
}
OETouchSample OETouch_Next(OETouch *t) {
    bool old_l = t->left, old_r = t->right, cancel = false;
    if (t->count) {
        OEEvent e = t->queue[t->head];
        t->head = (t->head + 1) % OE_TOUCH_QUEUE_CAPACITY;
        --t->count;
        t->x = e.x; t->y = e.y;
        switch (e.kind) {
            case OE_LEFT_DOWN: t->left = true; break;
            case OE_LEFT_UP: t->left = false; break;
            case OE_RIGHT_DOWN: t->right = true; break;
            case OE_RIGHT_UP: t->right = false; break;
            case OE_CANCEL: t->left = t->right = false; cancel = true; break;
            case OE_MOVE: break;
        }
    }
    OETouchSample out = { t->x, t->y, t->left, t->right,
        !cancel && !old_l && t->left, !cancel && old_l && !t->left,
        !cancel && !old_r && t->right, !cancel && old_r && !t->right, cancel };
    return out;
}
void OETouch_TakePan(OETouch *t, double *x, double *y) {
    *x = t->pan_x; *y = t->pan_y;
    t->pan_x = t->pan_y = 0;
}
