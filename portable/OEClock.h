/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef OE_CLOCK_H
#define OE_CLOCK_H
#include <stdbool.h>
typedef struct { double last, remainder; bool initialized; } OEClock;
void OEClock_Reset(OEClock *clock);
/* Original 15 ms simulation step, independent of 60/120 Hz screen refresh. */
unsigned OEClock_Advance(OEClock *clock, double now);
#endif
