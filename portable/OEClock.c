/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "OEClock.h"
#include <math.h>
#include <string.h>
void OEClock_Reset(OEClock *c) { memset(c, 0, sizeof(*c)); }
unsigned OEClock_Advance(OEClock *c, double now) {
    if (!isfinite(now)) return 0;
    if (!c->initialized || now < c->last) {
        c->last = now; c->remainder = 0; c->initialized = true;
        return 0;
    }
    double elapsed = now - c->last;
    c->last = now;
    if (elapsed > 0.12) elapsed = 0.12;
    c->remainder += elapsed;
    unsigned steps = (unsigned)floor((c->remainder + 1e-9) / 0.015);
    if (steps > 8) steps = 8;
    c->remainder -= steps * 0.015;
    if (c->remainder < 0) c->remainder = 0;
    return steps;
}
